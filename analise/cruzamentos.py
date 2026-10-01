"""Cruzamentos: (1) o gap dentro do mesmo grupo (ocupação x município x instrução x idade) e placebo homem x homem;
(2) maternidade: pseudo-painel por geração 2023-2025 e interação com a fecundidade do município (Censo 2022);
(3) indicadores do IBGE/PNUD por município (IDHM 2010, PIB per capita 2021, Censo 2022) em interação com o sexo.
Uso: python analise/cruzamentos.py. Saída: resultados/cruzamentos.json."""
import json, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
C = GEO / "censo"
OUT = RESULTADOS / "cruzamentos.json"
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
AMOSTRA = 20
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)
pct = lambda b: round(100 * (np.exp(b) - 1), 2)

# ---------- indicadores municipais ----------
def sidra(nome, filtro=None):
    d = json.load(open(C / f"{nome}.json"))
    df = pd.DataFrame(d[1:])
    df["V"] = pd.to_numeric(df.V, errors="coerce")
    return df if filtro is None else df.query(filtro)
fec = sidra("fecund").pivot_table(index="D1C", columns="D2C", values="V")
ind = pd.DataFrame(index=fec.index)
ind["filhos_por_mulher"] = fec["13316"] / fec["13315"]
ind["nascimentos_12m_por_mil"] = 1000 * fec["13317"] / fec["13315"]
fs = sidra("forca_sexo").pivot_table(index="D1C", columns=["D4C", "D5C"], values="V")
ind["participacao_feminina"] = 100 * fs[("5", "32386")] / fs[("5", "32385")]
ind["participacao_masculina"] = 100 * fs[("4", "32386")] / fs[("4", "32385")]
rs = sidra("renda_sexo").pivot_table(index="D1C", columns="D4C", values="V")
ind["renda_censo_m_sobre_h"] = 100 * rs["5"] / rs["4"]
ind["alfabetizacao"] = sidra("alfab").set_index("D1C").V
pib = sidra("pib").set_index("D1C").V * 1000; pop = sidra("pop").set_index("D1C").V
ind["pib_per_capita"] = pib / pop
ind["populacao"] = pop
idh = pd.DataFrame(json.load(open(C / "idhm.json"))["value"])
idh = idh[idh.VALDATA.str.startswith("2010")].set_index("TERCODIGO").VALVALOR
ind["idhm_2010"] = idh
ind.index = ind.index.str[:6]
log("indicadores", ind.shape, ind.isna().sum().to_dict())

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.register("ind", ind.reset_index().rename(columns={"D1C": "mun"}))

def vw(ano):
    con.execute(f"""create or replace view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico
      from '{DADOS}/{ano}/rais_*.parquet' where {FILTRO}""")

# ---------- 1. mesmo grupo e placebo ----------
vw("2025")
cel = con.execute("""
with b as (select cbo, mun, escolaridade, idade//10 fx, sexo, ln(rem) lw,
             (hash(cbo||mun||idade||rem||tempo||horas) % 2) metade from v),
s as (select cbo, mun, escolaridade, fx,
        count(*) filter (where sexo=1) nh, count(*) filter (where sexo=2) nm,
        avg(lw) filter (where sexo=1) lh, avg(lw) filter (where sexo=2) lm,
        count(*) filter (where sexo=1 and metade=0) nh0, count(*) filter (where sexo=1 and metade=1) nh1,
        avg(lw) filter (where sexo=1 and metade=0) lh0, avg(lw) filter (where sexo=1 and metade=1) lh1,
        count(*) filter (where sexo=2 and metade=0) nm0, count(*) filter (where sexo=2 and metade=1) nm1,
        avg(lw) filter (where sexo=2 and metade=0) lm0, avg(lw) filter (where sexo=2 and metade=1) lm1
      from b group by all)
select * from s where nh >= 10 and nm >= 10""").df()
w = np.minimum(cel.nh, cel.nm)
d = cel.lm - cel.lh
grupo = {"celulas": int(len(cel)), "vinculos": int((cel.nh + cel.nm).sum()),
         "gap_medio": pct(float(np.average(d, weights=w))), "gap_mediano": pct(float(d.median())),
         "pct_celulas_mulher_menos": round(100 * float(np.average(d < -0.02, weights=w)), 1),
         "pct_celulas_empate": round(100 * float(np.average(d.abs() <= 0.02, weights=w)), 1),
         "pct_celulas_mulher_mais": round(100 * float(np.average(d > 0.02, weights=w)), 1)}
ph = cel[(cel.nh0 >= 5) & (cel.nh1 >= 5)]; dh = ph.lh1 - ph.lh0; wh = np.minimum(ph.nh0, ph.nh1)
pm = cel[(cel.nm0 >= 5) & (cel.nm1 >= 5)]; dm = pm.lm1 - pm.lm0; wm = np.minimum(pm.nm0, pm.nm1)
grupo["placebo_homens"] = {"gap_medio": pct(float(np.average(dh, weights=wh))), "celulas": int(len(ph)),
                           "pct_celulas_diferenca_maior_que_8": round(100 * float(np.average(dh.abs() > 0.08, weights=wh)), 1)}
grupo["placebo_mulheres"] = {"gap_medio": pct(float(np.average(dm, weights=wm))), "celulas": int(len(pm))}
grupo["pct_celulas_homem_mulher_diferenca_maior_que_8"] = round(100 * float(np.average(d.abs() > 0.08, weights=w)), 1)
hist = pd.cut((100 * (np.exp(d) - 1)).clip(-39.9, 39.9), list(range(-40, 45, 5)))
grupo["hist"] = [{"de": int(i.left), "ate": int(i.right), "peso": round(float(v), 4)} for i, v in (w.groupby(hist, observed=False).sum() / w.sum()).items()]
hp = pd.cut((100 * (np.exp(dh) - 1)).clip(-39.9, 39.9), list(range(-40, 45, 5)))
grupo["hist_placebo"] = [{"de": int(i.left), "ate": int(i.right), "peso": round(float(v), 4)} for i, v in (wh.groupby(hp, observed=False).sum() / wh.sum()).items()]
log("grupo", {k: v for k, v in grupo.items() if not k.startswith("hist")})

# ---------- amostras com indicadores ----------
def amostra(ano):
    vw(ano)
    df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, v.mun, substr(v.mun,1,2) uf, div, publico,
      ln(rem) lw, {int(ano)} - idade coorte, i.* exclude (mun)
      from v left join ind i on i.mun = v.mun where hash(cbo||v.mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
    df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100
    df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)
    return df

def design(d, cont, cats):
    X = [d[cont].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def ols(d, cont, cats, fe="cbo", alvo=("f",), cluster="mun"):
    X = design(d, cont, cats); y = d.lw
    g = d[fe]; X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv)
    S = pd.DataFrame(Xv * u[:, None]).groupby(d[cluster].values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / (G - 1)
    return {a: (float(b[X.columns.get_loc(a)]), float(np.sqrt(V[X.columns.get_loc(a), X.columns.get_loc(a)]))) for a in alvo}

HC = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]
EMP = ["escolaridade", "tam", "uf", "div"]

# ---------- 2a. pseudo-painel por geração ----------
coortes = [(1955, 1964, "1955-64"), (1965, 1974, "1965-74"), (1975, 1984, "1975-84"), (1985, 1989, "1985-89"),
           (1990, 1994, "1990-94"), (1995, 1999, "1995-99"), (2000, 2007, "2000-07")]
painel = {c[2]: {} for c in coortes}
amostras = {}
for ano in ("2023", "2024", "2025"):
    df = amostra(ano); amostras[ano] = df
    for lo, hi, nome in coortes:
        dd = df[df.coorte.between(lo, hi)]
        c, se = ols(dd, ["f", "lh", "ten", "ten2", "publico"], EMP, cluster="cbo")["f"]
        painel[nome][ano] = {"gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)],
                             "idade_media": round(float(dd.idade.mean()), 1), "n": int(len(dd))}
    log("painel", ano)
for nome in painel:
    painel[nome]["variacao"] = round(painel[nome]["2025"]["gap"] - painel[nome]["2023"]["gap"], 2)
log("painel", {k: (v["2023"]["gap"], v["2025"]["gap"], v["variacao"]) for k, v in painel.items()})

# ---------- 2b e 3. interação do gap com indicadores do município (2025) ----------
df = amostras["2025"]
VARS = {"filhos_por_mulher": "Filhos por mulher (Censo 2022)", "nascimentos_12m_por_mil": "Nascimentos nos últimos 12 meses por mil mulheres (Censo 2022)",
        "idhm_2010": "IDHM (PNUD, 2010)", "pib_per_capita": "PIB per capita (IBGE, 2021)", "alfabetizacao": "Taxa de alfabetização (Censo 2022)",
        "participacao_feminina": "Participação feminina na força de trabalho (Censo 2022)",
        "renda_censo_m_sobre_h": "Renda das mulheres ÷ homens, inclui informais (Censo 2022)", "populacao": "População (Censo 2022)"}
df["pib_per_capita"] = np.log(df.pib_per_capita); df["populacao"] = np.log(df.populacao)
dfi = df.dropna(subset=list(VARS)).copy()
for v in VARS:
    dfi[v + "_z"] = (dfi[v] - dfi[v].mean()) / dfi[v].std()
inter = []
for v, nome in VARS.items():
    dfi["fx"] = dfi.f * dfi[v + "_z"]
    r = ols(dfi, HC + ["fx", v + "_z"], ["escolaridade", "tam", "div"], alvo=("f", "fx"))
    inter.append({"var": v, "nome": nome, "gap_na_media": pct(r["f"][0]), "efeito_pp_por_dp": round(100 * r["fx"][0], 2),
                  "ep_pp": round(100 * r["fx"][1], 2), "dp": round(float(df[v].std()), 3), "media": round(float(df[v].mean()), 3)})
    log(" inter", v, inter[-1]["efeito_pp_por_dp"], inter[-1]["ep_pp"])
# modelo conjunto (todas as interações juntas)
cols = []
for v in VARS:
    dfi[f"fx_{v}"] = dfi.f * dfi[v + "_z"]; cols += [f"fx_{v}", v + "_z"]
rj = ols(dfi, HC + cols, ["escolaridade", "tam", "div"], alvo=tuple(f"fx_{v}" for v in VARS))
conjunto = [{"var": v, "nome": VARS[v], "efeito_pp_por_dp": round(100 * rj[f"fx_{v}"][0], 2), "ep_pp": round(100 * rj[f"fx_{v}"][1], 2)} for v in VARS]
log("conjunto", [(c["var"], c["efeito_pp_por_dp"], c["ep_pp"]) for c in conjunto])

# gap por quartil de fecundidade (direto, fácil de ler)
dfi["q_fec"] = pd.qcut(dfi.filhos_por_mulher, 4, labels=["1º quartil (menos filhos)", "2º", "3º", "4º quartil (mais filhos)"])
quart = []
for q, dd in dfi.groupby("q_fec", observed=True):
    c, se = ols(dd, HC, ["escolaridade", "tam", "uf", "div"])["f"]
    quart.append({"quartil": str(q), "filhos": round(float(dd.filhos_por_mulher.mean()), 2), "gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]})
dfi["q_idh"] = pd.qcut(dfi.idhm_2010, 4, labels=["1º quartil (menor IDHM)", "2º", "3º", "4º quartil (maior IDHM)"])
quart_idh = []
for q, dd in dfi.groupby("q_idh", observed=True):
    c, se = ols(dd, HC, ["escolaridade", "tam", "uf", "div"])["f"]
    quart_idh.append({"quartil": str(q), "idhm": round(float(dd.idhm_2010.mean()), 3), "gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]})
log("quartis", quart, quart_idh)

# ---------- 2c. licença-maternidade (2023): gap com e sem quem teve filho no ano ----------
con.execute(f"""create or replace view v23 as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico,
  (50 in (ca1,ca2,ca3))::int lic from '{DADOS}/2023/rais_*.parquet' where {FILTRO}""")
lic = con.execute("""select avg(lic) filter (where sexo=2 and idade between 20 and 39)*100 pct_lic_20_39,
  count(*) filter (where lic=1 and sexo=2) n_lic from v23""").df().iloc[0]
OUT.write_text(json.dumps({"grupo": grupo, "painel": painel, "interacoes": inter, "conjunto": conjunto, "quartis_fecundidade": quart,
                           "quartis_idhm": quart_idh, "licenca": {"pct_mulheres_20_39_com_licenca_2023": round(float(lic.pct_lic_20_39), 2), "n": int(lic.n_lic)},
                           "amostra_2025": int(len(df)), "amostra_com_indicadores": int(len(dfi))},
                          ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", OUT)
