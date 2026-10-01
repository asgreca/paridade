"""Decomposição única do gap: tempo de trabalho (horas, tempo de casa, experiência) e condições do posto
(periculosidade, insalubridade, confinamento, turno, risco medido), mais instrução e empregador.
Oaxaca-Blinder pooled com indicador de sexo (Fortin 2008); EP por bootstrap de ocupações.
Uso: python analise/combinado.py ANO. Saída: resultados/combinado_ANO.json."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
AMOSTRA = 20
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)
lk = lambda ps: "(" + " or ".join(f"cbo like '{p}%'" for p in ps) + ")"
PROD = "substr(cbo,1,1) in ('6','7','8','9')"
PERIC = ["7321", "9511", "7156", "521135", "519110", "519115", "5173", "5172", "711120"]
INSAL = ["8485", "5142", "7222", "7223", "821", "822", "7232", "7243", "7244", "723315", "632605", "622110"]
CONF = ["7111", "7112", "7113", "3412", "3413", "7827", "3163", "862110"]
TURNO = ["5171", "3222", "2235", "7824", "7825", "8110", "8621", "8622"]
ANOS_ESTUDO = {1: 0, 2: 3, 3: 5, 4: 7, 5: 9, 6: 10, 7: 12, 8: 14, 9: 16, 10: 18, 11: 21}

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}")
cel = con.execute(f"""select cbo ccbo, substr(cnae,1,5) cl, avg((10 in (ca1,ca2,ca3) or 30 in (ca1,ca2,ca3))::int)*100 taxa_cel
  from '{DADOS}/2023/rais_*.parquet' where {FILTRO} group by 1,2 having count(*) >= 50""").df()
con.register("cel", cel)
df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, div, publico, ln(rem) lw,
  {lk(PERIC)}::int peric,
  ({lk(INSAL)} or (substr(cnae,1,4) in ('1011','1012','1013') and {PROD}) or (substr(cnae,1,3) in ('381','382') and {PROD})
     or (cbo='514320' and substr(cnae,1,2)='86'))::int insal,
  ({lk(CONF)} or (div in ('05','06','07','08','09') and {PROD}))::int conf,
  {lk(TURNO)}::int turno, coalesce(c.taxa_cel, 0) taxa_cel
  from v left join cel c on c.ccbo = v.cbo and c.cl = substr(v.cnae,1,5)
  where hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float)
df["exp"] = (df.idade - df.escolaridade.map(ANOS_ESTUDO) - 6).clip(lower=0); df["exp2"] = df.exp ** 2 / 100
df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)
log("amostra", len(df))

GRUPOS = {
    "Horas contratadas": ["lh"], "Tempo no emprego atual": ["ten", "ten2"], "Experiência na carreira": ["exp", "exp2"],
    "Periculosidade": ["peric"], "Insalubridade": ["insal"], "Confinamento": ["conf"], "Turno irregular": ["turno"],
    "Risco de acidente do posto": ["taxa_cel"],
}
CATS = ["escolaridade", "tam", "uf", "div"]
def design(d):
    X = [d[["f"] + sum(GRUPOS.values(), []) + ["publico"]].astype(float)]
    for c in CATS:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def decompor(d, fe):
    X = design(d); y = d.lw
    if fe:
        g = d.cbo; Xd = X - X.groupby(g).transform("mean"); yd = y - y.groupby(g).transform("mean")
    else:
        Xd = X.assign(const=1.0); yd = y
    b = pd.Series(np.linalg.lstsq(Xd.values, yd.values, rcond=None)[0], index=Xd.columns)
    m, w = d.f == 0, d.f == 1
    dif = lambda cols: float(((X.loc[w, cols].mean() - X.loc[m, cols].mean()) * b[cols]).sum())
    out = {k: dif(c) for k, c in GRUPOS.items()}
    out["Instrução"] = dif([c for c in X.columns if c.startswith("escolaridade_")])
    out["Empregador (setor, porte, estado, público)"] = dif([c for c in X.columns if c.startswith(("tam_", "uf_", "div_"))] + ["publico"])
    if fe:
        resid = y - X.drop(columns="f").values @ b.drop("f").values - b["f"] * d.f
        th = resid.groupby(d.cbo).transform("mean")
        out["Ocupação (demais diferenças)"] = float(th[w].mean() - th[m].mean())
    out["Não explicado"] = float(b["f"])
    return float(y[w].mean() - y[m].mean()), out, b

res = {}
for nome, fe in (("sem_ocupacao", False), ("com_ocupacao", True)):
    bruto, out, b = decompor(df, fe)
    # bootstrap por ocupação (30 réplicas) para EP das contribuições
    cbos = df.cbo.unique(); rng = np.random.default_rng(7); reps = []
    grp = df.groupby("cbo").indices
    for i in range(30):
        pick = rng.choice(cbos, len(cbos))
        idx = np.concatenate([grp[c] for c in pick])
        d = df.iloc[idx].copy()
        if fe:  # ocupações repetidas viram grupos distintos
            d["cbo"] = np.repeat(np.arange(len(pick)), [len(grp[c]) for c in pick]).astype(str)
        reps.append(decompor(d, fe)[1])
        if i % 5 == 0: log(" rep", nome, i)
    ep = {k: float(np.std([r[k] for r in reps])) for k in out}
    res[nome] = {"bruto_pp": round(100 * bruto, 2),
                 "fatores": [{"fator": k, "pp": round(100 * v, 2), "ep": round(100 * ep[k], 2)} for k, v in out.items()]}
    log(nome, res[nome])

medias = df.groupby("f").agg(horas=("h", "mean"), tempo_meses=("ten", "mean"), exp=("exp", "mean"), peric=("peric", "mean"),
                             insal=("insal", "mean"), conf=("conf", "mean"), turno=("turno", "mean"), risco=("taxa_cel", "mean"))
res["medias"] = {k: {"h": round(float(medias.loc[0, k]) * (100 if k in ("peric", "insal", "conf", "turno") else 1), 2),
                     "m": round(float(medias.loc[1, k]) * (100 if k in ("peric", "insal", "conf", "turno") else 1), 2)} for k in medias.columns}
res["ano"] = int(ANO); res["amostra"] = int(len(df))
Path(RESULTADOS / f"combinado_{ANO}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("medias", res["medias"])
