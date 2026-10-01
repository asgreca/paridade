"""Gap por mesorregião e por estado, bruto e ajustado (mesma ocupação), com teste de homogeneidade.
Uso: python analise/mapa.py ANO. Saída: resultados/mapa_ANO.json. Malhas: geo/*.json (API de malhas e localidades do IBGE)."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
OUT = RESULTADOS / f"mapa_{ANO}.json"
AMOSTRA = 5
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)
pct = lambda b: round(100 * (np.exp(b) - 1), 2)

muns = json.loads((GEO / "municipios.json").read_text(encoding="utf-8"))
m2meso, meso_nome, meso_uf = {}, {}, {}
for m in muns:
    mic = m.get("microrregiao") or {}
    ms = mic.get("mesorregiao") or {}
    if not ms:
        continue
    m2meso[str(m["id"])[:6]] = str(ms["id"])
    meso_nome[str(ms["id"])] = ms["nome"]; meso_uf[str(ms["id"])] = ms["UF"]["sigla"]
REG = {"1": "Norte", "2": "Nordeste", "3": "Sudeste", "4": "Sul", "5": "Centro-Oeste"}

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.register("mm", pd.DataFrame({"mun": list(m2meso), "meso": list(m2meso.values())}))
con.execute(f"""create view v as select p.*, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico, mm.meso
  from '{DADOS}/{ANO}/rais_*.parquet' p join mm on mm.mun = p.mun where {FILTRO}""")
bruto = con.execute("""select meso, count(*) n, avg((sexo=2)::int)*100 pm, avg(rem) filter (where sexo=2) m, avg(rem) filter (where sexo=1) h
  from v group by 1""").df().set_index("meso")
df = con.execute(f"""select meso, substr(mun,1,2) uf, sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, div, publico, ln(rem) lw
  from v where hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100; df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)
log("amostra", len(df))

def ajuste(d):
    X = [d[["f", "lh", "idade", "age2", "ten", "ten2", "publico"]].astype(float)]
    for c in ("escolaridade", "tam", "div"):
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    X = pd.concat(X, axis=1); g = d.cbo
    X = X - X.groupby(g).transform("mean"); y = d.lw - d.lw.groupby(g).transform("mean")
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv)
    S = pd.DataFrame(Xv * u[:, None]).groupby(g.values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / max(G - 1, 1)
    return float(b[0]), float(np.sqrt(V[0, 0]))

def homogeneidade(est):
    """Q de Cochran, I² e desvio-padrão entre regiões (tau, DerSimonian-Laird) sobre os gaps em log."""
    b = np.array([e[0] for e in est]); se = np.array([e[1] for e in est]); w = 1 / se ** 2
    mu = (w * b).sum() / w.sum(); Q = float((w * (b - mu) ** 2).sum()); k = len(b)
    tau2 = max(0.0, (Q - (k - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    return {"k": k, "Q": round(Q, 1), "gl": k - 1, "I2": round(100 * max(0.0, (Q - (k - 1)) / Q), 1),
            "media": pct(mu), "tau_pp": round(100 * np.sqrt(tau2), 2)}

mesos, est = [], []
for meso, d in df.groupby("meso"):
    if d.f.sum() < 300 or (1 - d.f).sum() < 300:
        continue
    b, se = ajuste(d); est.append((b, se))
    r = bruto.loc[meso]
    mesos.append({"id": meso, "nome": meso_nome.get(meso, meso), "uf": meso_uf.get(meso, ""), "regiao": REG.get(meso[0], ""),
                  "n": int(r.n), "pct_m": round(r.pm, 1), "bruto": round(100 * (r.m / r.h - 1), 1),
                  "ajustado": pct(b), "ic": [pct(b - 1.96 * se), pct(b + 1.96 * se)]})
log("mesos", len(mesos))
ufs, est_uf = [], []
for uf, d in df.groupby("uf"):
    b, se = ajuste(d); est_uf.append((b, se))
    x = con.execute(f"select avg(rem) filter (where sexo=2)/avg(rem) filter (where sexo=1)*100-100 from v where substr(mun,1,2)='{uf}'").fetchone()[0]
    ufs.append({"cod": uf, "bruto": round(x, 1), "ajustado": pct(b), "ic": [pct(b - 1.96 * se), pct(b + 1.96 * se)]})
reg, est_reg = [], []
for rg, d in df.groupby(df.meso.str[0]):
    b, se = ajuste(d); est_reg.append((b, se)); reg.append({"regiao": REG[rg], "ajustado": pct(b), "ic": [pct(b - 1.96 * se), pct(b + 1.96 * se)]})
# quanto da variação bruta entre mesorregiões some com o ajuste
br = np.array([m["bruto"] for m in mesos]); aj = np.array([m["ajustado"] for m in mesos])
payload = {"ano": int(ANO), "mesos": mesos, "ufs": ufs, "regioes": reg,
           "homog_meso": homogeneidade(est), "homog_uf": homogeneidade(est_uf), "homog_regiao": homogeneidade(est_reg),
           "dp_bruto_meso": round(float(br.std()), 2), "dp_ajustado_meso": round(float(aj.std()), 2),
           "corr_bruto_ajustado": round(float(np.corrcoef(br, aj)[0, 1]), 2)}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", {k: v for k, v in payload.items() if k not in ("mesos", "ufs")})
