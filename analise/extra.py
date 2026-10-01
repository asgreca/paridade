"""Braçal em condição adversa (periculosidade, insalubridade, turno, risco medido) e experiência.
Uso: python analise/extra.py ANO. Saída: resultados/extra_ANO.json.
A RAIS não informa adicional pago; a condição é do posto (ocupação x atividade), com risco medido na RAIS 2023."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
OUT = RESULTADOS / f"extra_{ANO}.json"
AMOSTRA = 20
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
pct = lambda b: round(100 * (np.exp(b) - 1), 2)
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)

PERIC = ["7321", "9511", "7156", "521135", "519110", "519115", "5173", "5172", "711120"]          # NR-16
INSAL = ["8485", "5142", "7222", "7223", "821", "822", "7232", "7243", "7244", "723315", "632605", "622110"]  # NR-15 típicas
CONF = ["7111", "7112", "7113", "3412", "3413", "7827", "3163", "862110"]
TURNO = ["5171", "7824", "7825", "8110", "8621", "8622"]
lk = lambda ps: "(" + " or ".join(f"cbo like '{p}%'" for p in ps) + ")"
BRACAL = "substr(cbo,1,1) in ('6','7','8','9')"
ANOS_ESTUDO = {1: 0, 2: 3, 3: 5, 4: 7, 5: 9, 6: 10, 7: 12, 8: 14, 9: 16, 10: 18, 11: 21}

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999) publico
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
# risco medido do posto (ocupação x classe CNAE), RAIS 2023; posto de risco alto = top 20% dos vínculos braçais
cel = con.execute(f"""select cbo, substr(cnae,1,5) cl, avg((10 in (ca1,ca2,ca3) or 30 in (ca1,ca2,ca3))::int)*100 taxa, count(*) n
  from '{DADOS}/2023/rais_*.parquet' where {FILTRO} and {BRACAL} group by 1,2 having count(*) >= 50""").df()
cs = cel.sort_values("taxa"); cs["cum"] = cs.n.cumsum() / cs.n.sum()
corte = float(cs[cs.cum >= 0.8].taxa.iloc[0])
con.register("cel", cel.rename(columns={"cbo": "ccbo"}))
cond = f"""case when {lk(PERIC)} then 'Periculosidade'
  when {lk(INSAL)} or (substr(cnae,1,4) in ('1011','1012','1013') and {BRACAL}) or (substr(cnae,1,3) in ('381','382') and {BRACAL})
       or (cbo='514320' and substr(cnae,1,2)='86') then 'Insalubridade'
  when {lk(CONF)} then 'Confinamento'
  when {lk(TURNO)} then 'Turno'
  when c.taxa >= {corte} then 'Risco alto medido'
  else 'Sem condição adversa' end"""
df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, div, publico::int publico,
  ln(rem) lw, rem, {BRACAL} bracal, {cond} condicao
  from v left join cel c on c.ccbo=v.cbo and c.cl=substr(v.cnae,1,5)
  where hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100
df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)
df["adv"] = (df.condicao != "Sem condição adversa").astype(float)
log("amostra", len(df), "corte risco", round(corte, 2))

def design(d, cont, cats):
    X = [d[cont].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def ols(d, cont, cats, fe=None, alvo=("f",), cluster="cbo", y="lw"):
    X = design(d, cont, cats); yy = d[y]
    if fe:
        g = d[fe]; X = X - X.groupby(g).transform("mean"); yy = yy - yy.groupby(g).transform("mean")
    else:
        X = X.assign(const=1.0)
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, yy.values, rcond=None); u = yy.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv)
    S = pd.DataFrame(Xv * u[:, None]).groupby(d[cluster].values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / (G - 1)
    return {a: (float(b[X.columns.get_loc(a)]), float(np.sqrt(V[X.columns.get_loc(a)] [X.columns.get_loc(a)]))) for a in alvo}

def ic(c, se):
    return {"gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]}

CTRL = ["lh", "idade", "age2", "ten", "ten2", "publico"]
EMP = ["escolaridade", "tam", "uf", "div"]

# ---------- A. Braçal x condição adversa ----------
br = df[df.bracal].copy()
desc = br.groupby(["condicao", "sexo"]).agg(n=("rem", "size"), media=("rem", "mean"), mediana=("rem", "median")).reset_index()
fator = 1 / (br.shape[0] / con.execute(f"select count(*) from v where {BRACAL}").fetchone()[0])
grupos = [{"condicao": r.condicao, "sexo": int(r.sexo), "n_estimado": int(r.n * fator), "media": round(r.media), "mediana": round(r.mediana)}
          for r in desc.itertuples()]
# 4 grupos: HA, HN, MA, MN; base = mulher braçal sem condição adversa
br["HA"] = ((br.f == 0) & (br.adv == 1)).astype(float); br["HN"] = ((br.f == 0) & (br.adv == 0)).astype(float)
br["MA"] = ((br.f == 1) & (br.adv == 1)).astype(float)
bruto = {k: pct(br.lw[m].mean() - br.lw[(br.f == 1) & (br.adv == 0)].mean()) for k, m in
         (("HA", br.HA == 1), ("HN", br.HN == 1), ("MA", br.MA == 1))}
aj = ols(br, ["HA", "HN", "MA"] + CTRL, EMP, alvo=("HA", "HN", "MA"))
# mesma ocupação: gap de sexo dentro dos postos adversos e dentro dos não adversos
dentro = {k: ic(*ols(br[br.adv == a], ["f"] + CTRL, EMP, "cbo")["f"]) for k, a in (("adverso", 1), ("sem", 0))}
# prêmio da condição por tipo (vs braçal sem condição), mesmo sexo e perfil
tipos = [t for t in ["Periculosidade", "Insalubridade", "Confinamento", "Turno", "Risco alto medido"] if (br.condicao == t).sum() > 500]
for t in tipos:
    br[f"t_{t}"] = (br.condicao == t).astype(float)
pt = ols(br, ["f"] + [f"t_{t}" for t in tipos] + CTRL, EMP, alvo=tuple(f"t_{t}" for t in tipos))
bracal = {"corte_risco": round(corte, 2), "grupos": grupos, "bruto_vs_mulher_sem": bruto,
          "ajustado_vs_mulher_sem": {k: ic(*v) for k, v in aj.items()}, "gap_mesma_ocupacao": dentro,
          "premio_condicao": {t: ic(*pt[f"t_{t}"]) for t in tipos},
          "pct_mulheres_adverso": round(100 * br[br.adv == 1].f.mean(), 1), "pct_homens_adverso": round(100 * (1 - br[br.adv == 1].f.mean()), 1),
          "pct_de_homens_bracais_em_adverso": round(100 * br[br.f == 0].adv.mean(), 1),
          "pct_de_mulheres_bracais_em_adverso": round(100 * br[br.f == 1].adv.mean(), 1)}
log("bracal", bruto, {k: v["gap"] for k, v in bracal["ajustado_vs_mulher_sem"].items()}, dentro, bracal["premio_condicao"])

# ---------- B. Experiência ----------
df["anos_est"] = df.escolaridade.map(ANOS_ESTUDO)
df["exp"] = (df.idade - df.anos_est - 6).clip(lower=0)
df["ten_anos"] = df.ten / 12
fx_ten = [(-0.01, 1, "Menos de 1 ano"), (1, 2, "1 a 2 anos"), (2, 5, "2 a 5 anos"), (5, 10, "5 a 10 anos"), (10, 20, "10 a 20 anos"), (20, 99, "20 anos ou mais")]
fx_exp = [(-0.01, 5, "0 a 5 anos"), (5, 10, "5 a 10 anos"), (10, 20, "10 a 20 anos"), (20, 30, "20 a 30 anos"), (30, 99, "30 anos ou mais")]
def por_faixa(col, faixas, cont):
    out = []
    for lo, hi, nome in faixas:
        d = df[(df[col] > lo) & (df[col] <= hi)]
        out.append({"faixa": nome, "n": int(len(d)) * AMOSTRA, "pct_m": round(100 * d.f.mean(), 1),
                    "media_h": round(float(d.rem[d.f == 0].mean())), "media_m": round(float(d.rem[d.f == 1].mean())),
                    "bruto": round(100 * (d.rem[d.f == 1].mean() / d.rem[d.f == 0].mean() - 1), 1),
                    "ajustado": ic(*ols(d, ["f"] + cont, EMP, "cbo")["f"])})
    return out
tempo = por_faixa("ten_anos", fx_ten, ["lh", "idade", "age2", "publico"])
experiencia = por_faixa("exp", fx_exp, ["lh", "ten", "ten2", "publico"])
# perfil: log salário médio por ano de experiência potencial e sexo (0-40)
perfil = df[df.exp <= 40].groupby(["exp", "sexo"]).lw.mean().unstack()
perfil_exp = [{"exp": int(e), "h": round(float(np.exp(r[1]))), "m": round(float(np.exp(r[2])))} for e, r in perfil.iterrows()]
perfil_t = df.assign(t=df.ten_anos.clip(upper=30).astype(int)).groupby(["t", "sexo"]).lw.mean().unstack()
perfil_ten = [{"t": int(e), "h": round(float(np.exp(r[1]))), "m": round(float(np.exp(r[2])))} for e, r in perfil_t.iterrows()]
# retorno de cada ano de experiência, por sexo (mesma ocupação)
ret = {}
for s, k in ((0, "h"), (1, "m")):
    d = df[df.f == s].assign(e2=lambda x: x.exp ** 2 / 100)
    r = ols(d, ["exp", "e2", "ten", "ten2", "lh", "publico"], EMP, "cbo", alvo=("exp", "ten"))
    ret[k] = {"exp": round(100 * r["exp"][0], 2), "ten": round(100 * r["ten"][0] * 12, 2)}
log("tempo", [(x["faixa"], x["bruto"], x["ajustado"]["gap"]) for x in tempo])
log("exp", [(x["faixa"], x["bruto"], x["ajustado"]["gap"]) for x in experiencia], ret)

OUT.write_text(json.dumps({"ano": int(ANO), "bracal_adverso": bracal, "tempo_casa": tempo, "experiencia": experiencia,
                           "perfil_exp": perfil_exp, "perfil_tempo": perfil_ten, "retorno": ret}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", OUT)
