"""Força física conta? Trabalho operacional pesado x leve: composição por sexo, salário e gap na mesma ocupação.
Uso: python analise/forca.py ANO. Saída: resultados/forca_ANO.json."""
import json, sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
pct = lambda b: round(100 * (np.exp(b) - 1), 2)
PESADO = ["7152", "7155", "7170", "7832", "6210", "6220", "6221", "6321", "7111", "7112", "8485", "5142", "7241", "7243", "821", "822"]
LEVE = ["7842", "7841", "7631", "7632", "7633", "7311", "7312", "8484"]
PERIGO = {"Periculosidade (NR-16)": ["7321", "9511", "7156", "521135", "519110", "519115", "5173", "5172", "711120"],
          "Confinamento e subsolo": ["7111", "7112", "7113", "3412", "3413", "7827", "3163", "862110"]}
lk = lambda ps: "(" + " or ".join(f"cbo like '{p}%'" for p in ps) + ")"
CLASSE = f"case when {lk(PESADO)} then 'Esforço físico pesado' when {lk(LEVE)} then 'Operacional leve ou de precisão' when substr(cbo,1,1) in ('6','7','8','9') then 'Outro operacional' else 'Demais funções' end"

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico, {CLASSE} classe
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
desc = con.execute("""select classe, count(*) n, avg((sexo=2)::int)*100 pm,
  median(rem) filter (where sexo=1) med_h, median(rem) filter (where sexo=2) med_m,
  avg(rem) filter (where sexo=1) media_h, avg(rem) filter (where sexo=2) media_m from v group by 1""").df().set_index("classe")
tot_h = con.execute("select count(*) from v where sexo=1").fetchone()[0]; tot_m = con.execute("select count(*) from v where sexo=2").fetchone()[0]
por_sexo = con.execute("select classe, sexo, count(*) n from v group by 1,2").df().pivot(index="classe", columns="sexo", values="n")
perigo = []
for nome, ps in PERIGO.items():
    x = con.execute(f"select count(*) n, avg((sexo=1)::int)*100 ph from v where {lk(ps)}").df().iloc[0]
    perigo.append({"grupo": nome, "n": int(x.n), "pct_h": round(x.ph, 1)})
x = con.execute(f"""with t as (select cbo, avg((10 in (ca1,ca2,ca3) or 30 in (ca1,ca2,ca3))::int) taxa from '{DADOS}/2023/rais_*.parquet' where {FILTRO} group by 1)
  select count(*) n, avg((sexo=1)::int)*100 ph from v join t using(cbo) where t.taxa >= 0.02""").df().iloc[0]
perigo.append({"grupo": "Ocupações com 2% ou mais de afastamento por acidente", "n": int(x.n), "pct_h": round(x.ph, 1)})

df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, div, publico, classe, ln(rem) lw
  from v where classe <> 'Demais funções' and hash(cbo||mun||idade||rem||tempo) % 10 = 0""").df()
df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100; df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)

def ols(d, cont, cats, fe=None, alvo=("f",)):
    X = [d[cont].astype(float)] + [pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float) for c in cats]
    X = pd.concat(X, axis=1); y = d.lw
    if fe:
        g = d[fe]; X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
    else:
        X = X.assign(const=1.0)
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv); S = pd.DataFrame(Xv * u[:, None]).groupby(d.cbo.values).sum().values
    V = Ai @ (S.T @ S) @ Ai * S.shape[0] / (S.shape[0] - 1)
    return {a: (float(b[X.columns.get_loc(a)]), float(np.sqrt(V[X.columns.get_loc(a), X.columns.get_loc(a)]))) for a in alvo}

HC = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]
classes = []
for k in ["Esforço físico pesado", "Operacional leve ou de precisão", "Outro operacional"]:
    d = df[df.classe == k]; c, se = ols(d, HC, ["escolaridade", "tam", "uf", "div"], "cbo")["f"]
    r = desc.loc[k]
    classes.append({"classe": k, "n": int(r.n), "pct_m": round(r.pm, 1), "pct_dos_homens": round(100 * por_sexo.loc[k, 1] / tot_h, 1),
                    "pct_das_mulheres": round(100 * por_sexo.loc[k, 2] / tot_m, 1), "med_h": round(r.med_h), "med_m": round(r.med_m),
                    "media_h": round(r.media_h), "media_m": round(r.media_m), "bruto": round(100 * (r.media_m / r.media_h - 1), 1),
                    "gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]})
# o trabalho pesado paga mais que o leve? (mesmo sexo e perfil, sem efeito fixo de ocupação)
op = df[df.classe.isin(["Esforço físico pesado", "Operacional leve ou de precisão"])].copy()
op["pesado"] = (op.classe == "Esforço físico pesado").astype(float)
premio = {}
for sx, nome in ((1, "homens"), (2, "mulheres")):
    d = op[op.sexo == sx]; c, se = ols(d, ["pesado", "lh", "idade", "age2", "ten", "ten2", "publico"], ["escolaridade", "tam", "uf", "div"], alvo=("pesado",))["pesado"]
    premio[nome] = {"gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]}
dm = desc.loc["Demais funções"]
out = {"ano": int(ANO), "classes": classes, "premio_pesado_sobre_leve": premio, "perigo": perigo,
       "demais": {"pct_m": round(dm.pm, 1), "med_h": round(dm.med_h), "med_m": round(dm.med_m)},
       "mediana_geral": round(float(con.execute("select median(rem) from v").fetchone()[0]))}
(RESULTADOS / f"forca_{ANO}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=float))
