"""Validação: a regressão principal com TODOS os vínculos do ano (sem amostra), em lotes de ocupações.
O efeito fixo de ocupação só depende de vínculos da mesma ocupação, então processar lotes de ocupações e somar
X'X e X'y dá exatamente o mesmo resultado que rodar a base inteira de uma vez.
Uso: python analise/completa.py ANO. Saída: resultados/completa_ANO.json."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
LOTES = 24
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)
pct = lambda b: round(100 * (np.exp(b) - 1), 2)

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select sexo, idade, escolaridade, tempo, horas, tam, cbo, mun, substr(mun,1,2) uf, substr(cnae,1,2) div,
  (natjur between 1000 and 1999)::int publico, ln(rem) lw, hash(cbo) % {LOTES} lote
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
# níveis fixos das categorias (as mesmas colunas em todos os lotes)
niveis = {c: sorted(con.execute(f"select distinct {c} from v").df()[c].dropna().tolist()) for c in ("escolaridade", "tam", "uf", "div")}
CONT = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]

def design(d, cats):
    X = [d[CONT].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(pd.Categorical(d[c], categories=niveis[c]), prefix=c, drop_first=True, dtype=float).set_axis(d.index))
    return pd.concat(X, axis=1)

specs = {"mesma_ocupacao": (["escolaridade", "tam", "uf", "div"], ["cbo"]),
         "mesma_ocupacao_cidade": (["escolaridade", "tam", "div"], ["cbo", "mun"])}
acc = {k: None for k in specs}
n_total = 0
for lote in range(LOTES):
    d = con.execute(f"select * from v where lote = {lote}").df()
    d["f"] = (d.sexo == 2).astype(float); d["age2"] = d.idade.astype(float) ** 2 / 100
    d["ten"] = d.tempo; d["ten2"] = d.ten ** 2 / 100; d["lh"] = np.log(d.horas)
    n_total += len(d)
    for k, (cats, fe) in specs.items():
        X = design(d, cats); y = d.lw
        g = d[fe[0]] if len(fe) == 1 else d[fe[0]] + "_" + d[fe[1]]
        X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
        Xv = X.values; XtX = Xv.T @ Xv; Xty = Xv.T @ y.values
        if acc[k] is None:
            acc[k] = [XtX, Xty, list(X.columns)]
        else:
            acc[k][0] += XtX; acc[k][1] += Xty
    log("lote", lote, len(d))
res = {"ano": int(ANO), "vinculos": int(n_total)}
for k, (XtX, Xty, cols) in acc.items():
    b = np.linalg.lstsq(XtX, Xty, rcond=None)[0]
    res[k] = pct(b[cols.index("f")])
amostra = json.loads((RESULTADOS / f"estat_{ANO}.json").read_text(encoding="utf-8"))
esc = {e["passo"]: e for e in amostra["escada"]}
res["amostra"] = {"mesma_ocupacao": esc["Mesma ocupação"], "mesma_ocupacao_cidade": esc["Mesma ocupação, mesma cidade"], "n": amostra["amostra"]}
(RESULTADOS / f"completa_{ANO}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", res)
