"""Ocupações com maior presença feminina: gap na mesma ocupação, com o mesmo perfil, e IC 95%.
Seleção: as 20 ocupações (CBO de 6 dígitos) com maior % de mulheres entre as que têm 50 mil vínculos ou mais no ano.
Modelo igual ao das profissões de estatistica.py: base completa da ocupação, controles de jornada, idade, tempo de casa,
setor público, instrução, porte, UF e divisão CNAE; erro-padrão agrupado por município.
Uso: python analise/feminina.py ANO. Saída: resultados/feminina_ANO.json."""
import json, sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import DADOS, RESULTADOS, CBO_LABELS

ANO = sys.argv[1]
OUT = RESULTADOS / f"feminina_{ANO}.json"
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
N_MIN, TOP = 50000, 20
rot = json.loads(Path(CBO_LABELS).read_text(encoding="utf-8"))
pct = lambda b: round(100 * (np.exp(b) - 1), 1)

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
sel = con.execute(f"""select cbo, count(*) n, avg((sexo=2)::int)*100 pm from v group by 1
  having count(*) >= {N_MIN} order by pm desc, cbo limit {TOP}""").df()

def ols(d, cont, cats):
    X = [d[cont].astype(float)] + [pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float) for c in cats]
    X = pd.concat(X, axis=1).assign(const=1.0)
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, d.lw.values, rcond=None); u = d.lw.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv); S = pd.DataFrame(Xv * u[:, None]).groupby(d.mun.values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / max(G - 1, 1)
    i = X.columns.get_loc("f")
    return float(b[i]), float(np.sqrt(V[i, i]))

HC = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]
CATS = ["escolaridade", "tam", "uf", "div"]
linhas = []
for r in sel.itertuples():
    d = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, mun, substr(mun,1,2) uf, div, publico, ln(rem) lw, rem
      from v where cbo = '{r.cbo}'""").df()
    d["f"] = (d.sexo == 2).astype(float); d["age2"] = d.idade.astype(float) ** 2 / 100; d["ten2"] = d.ten ** 2 / 100; d["lh"] = np.log(d.h)
    c, se = ols(d, [x for x in HC if d[x].std() > 0], CATS)
    linhas.append({"cbo": r.cbo, "ocupacao": rot.get(r.cbo, r.cbo), "n": int(r.n), "pct_m": round(r.pm, 1),
                   "n_homens": int((d.f == 0).sum()), "media_m": round(float(d.rem[d.f == 1].mean())), "media_h": round(float(d.rem[d.f == 0].mean())),
                   "bruto": round(100 * (d.rem[d.f == 1].mean() / d.rem[d.f == 0].mean() - 1), 1),
                   "pct_publico": round(100 * d.publico.mean(), 1),
                   "ajustado": {"gap": pct(c), "ic_baixo": pct(c - 1.96 * se), "ic_alto": pct(c + 1.96 * se)}})
    print(r.cbo, linhas[-1]["ocupacao"][:40], linhas[-1]["pct_m"], linhas[-1]["bruto"], linhas[-1]["ajustado"], flush=True)

aj = np.array([l["ajustado"]["gap"] for l in linhas]); w = np.array([l["n"] for l in linhas], float)
resumo = {"ocupacoes": len(linhas), "vinculos": int(w.sum()), "pct_m_medio": round(float(np.average([l["pct_m"] for l in linhas], weights=w)), 1),
          "gap_medio_ponderado": round(float(np.average(aj, weights=w)), 1),
          "homem_ganha_mais": sum(l["ajustado"]["ic_alto"] < 0 for l in linhas),
          "empate": sum(l["ajustado"]["ic_baixo"] <= 0 <= l["ajustado"]["ic_alto"] for l in linhas),
          "mulher_ganha_mais": sum(l["ajustado"]["ic_baixo"] > 0 for l in linhas)}
OUT.write_text(json.dumps({"ano": int(ANO), "criterio": {"n_min": N_MIN, "top": TOP}, "ocupacoes": linhas, "resumo": resumo},
                          ensure_ascii=False, indent=1, default=float), encoding="utf-8")
print(resumo)
