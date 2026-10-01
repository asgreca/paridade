"""Análise estatística aprofundada do gap (uso: python analise/estatistica.py ANO). Saída: resultados/estat_ANO.json.
1. Escada com erro-padrão agrupado por ocupação e IC 95%.
2. Regressão quantílica incondicional (RIF, Firpo-Fortin-Lemieux 2009): gap em cada ponto da distribuição.
3. Risco: correlação entre ocupações (gap x taxa de acidente) com IC bootstrap; interação sexo x risco;
   exposição a risco dentro da mesma função (célula CBO x CNAE).
4. Trabalho braçal: segregação (Duncan), contrafactual de distribuição ocupacional, pedreiro.
5. Profissões selecionadas: gap bruto e ajustado com IC 95%, público e privado.
6. Robustez por subgrupo.
Taxa de acidente sempre da RAIS 2023 (registro de afastamentos incompleto a partir de 2024)."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
OUT = RESULTADOS / f"estat_{ANO}.json"
LABELS = CBO_LABELS
AMOSTRA = 20
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
rng = np.random.default_rng(42)
rotulos = json.loads(Path(LABELS).read_text(encoding="utf-8"))
rot = lambda c: rotulos.get(c, c)
pct = lambda b: round(100 * (np.exp(b) - 1), 2)
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)

con = duckdb.connect()
con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999) publico
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
con.execute(f"""create view v23 as select *, (10 in (ca1,ca2,ca3) or 30 in (ca1,ca2,ca3)) acidente
  from '{DADOS}/2023/rais_*.parquet' where {FILTRO}""")
# risco estrutural: taxa de acidente por ocupação e por ocupação x classe CNAE (5 dígitos), RAIS 2023
taxa_cbo = con.execute("select cbo, avg(acidente::int)*100 taxa, count(*) n from v23 group by 1").df().set_index("cbo")
taxa_cel = con.execute("""select cbo, substr(cnae,1,5) cl, avg(acidente::int)*100 taxa_cel, count(*) n
  from v23 group by 1,2 having count(*) >= 50""").df()

# ---------- amostra ----------
df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(cnae,1,5) cl, substr(mun,1,2) uf, mun, div,
  publico::int publico, ln(rem) lw, ln(rem/(horas*4.348)) lwh
  from v where hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float)
df["age2"] = df.idade.astype(float) ** 2 / 100
df["ten2"] = df.ten ** 2 / 100
df["lh"] = np.log(df.h)
df["cm"] = df.cbo + "_" + df.mun
df["taxa"] = df.cbo.map(taxa_cbo.taxa)
df = df.merge(taxa_cel[["cbo", "cl", "taxa_cel"]], on=["cbo", "cl"], how="left")
log("amostra", len(df))

def design(d, cont, cats):
    X = [d[cont].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def ols(d, cont, cats=(), fe=None, y="lw", cluster="cbo", alvo=("f",)):
    """MQO (com efeito fixo por demeaning) e erro-padrão agrupado (CR1). Devolve {var: (coef, ep)}."""
    X = design(d, cont, list(cats)); yy = d[y].astype(float)
    if fe is not None:
        g = d[fe]; X = X - X.groupby(g).transform("mean"); yy = yy - yy.groupby(g).transform("mean")
    else:
        X = X.assign(const=1.0)
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, yy.values, rcond=None)
    u = yy.values - Xv @ b
    XtX_inv = np.linalg.pinv(Xv.T @ Xv)
    idx = [X.columns.get_loc(a) for a in alvo]
    S = pd.DataFrame(Xv * u[:, None]).groupby(d[cluster].values).sum().values
    G, N, K = S.shape[0], len(yy), Xv.shape[1]
    meat = S.T @ S
    V = XtX_inv @ meat @ XtX_inv * (G / (G - 1)) * ((N - 1) / (N - K))
    return {a: (float(b[i]), float(np.sqrt(V[i, i]))) for a, i in zip(alvo, idx)}

def ic(c, se):
    return {"gap": pct(c), "ic_baixo": pct(c - 1.96 * se), "ic_alto": pct(c + 1.96 * se), "ep_log": round(se, 5)}

HC = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]
EMP = ["escolaridade", "tam", "uf", "div"]

# ---------- 1. Escada com IC ----------
specs = [("Comparação direta", ["f"], [], None), ("Mesma jornada", ["f", "lh"], [], None),
         ("Mesma instrução", ["f", "lh"], ["escolaridade"], None), ("Mesmo perfil e empregador", HC, EMP, None),
         ("Mesma ocupação", HC, EMP, "cbo"), ("Mesma ocupação, mesma cidade", HC, ["escolaridade", "tam", "div"], "cm")]
escada = []
for nome, cont, cats, fe in specs:
    c, se = ols(df, cont, cats, fe)["f"]
    escada.append({"passo": nome, **ic(c, se)})
    log(" escada", nome, escada[-1])

# ---------- 2. RIF: gap por quantil ----------
quantis = []
y = df.lw.values
h = 1.06 * y.std() * len(y) ** (-1 / 5)
for tau in [0.10, 0.25, 0.50, 0.75, 0.90, 0.95]:
    q = np.quantile(y, tau)
    dens = np.mean(np.exp(-0.5 * ((y - q) / h) ** 2)) / (h * np.sqrt(2 * np.pi))
    df["rif"] = q + (tau - (y <= q)) / dens
    c, se = ols(df, HC, EMP, "cbo", y="rif")["f"]
    bruto = np.quantile(df.lw[df.f == 1], tau) - np.quantile(df.lw[df.f == 0], tau)
    quantis.append({"quantil": int(tau * 100), "bruto": pct(bruto), **ic(c, se),
                    "salario_h": round(float(np.exp(np.quantile(df.lw[df.f == 0], tau)))),
                    "salario_m": round(float(np.exp(np.quantile(df.lw[df.f == 1], tau))))})
    log(" rif", tau, quantis[-1]["bruto"], quantis[-1]["gap"])
df.drop(columns="rif", inplace=True)

# ---------- 3. Risco ----------
# 3a. gap dentro de cada ocupação (células CBO x instrução x faixa etária x UF, por hora), base completa
cel = con.execute("""
with c as (select cbo, escolaridade, (idade//10) fx, substr(mun,1,2) uf, sexo, count(*) n, avg(ln(rem/(horas*4.348))) lw
           from v group by all),
p as (select h.cbo, h.n nh, m.n nm, m.lw - h.lw d from c h join c m using (cbo, escolaridade, fx, uf)
      where h.sexo=1 and m.sexo=2)
select cbo, sum(nh) nh, sum(nm) nm, sum(d*least(nh,nm))/sum(least(nh,nm)) d, sum(least(nh,nm)) w
from p group by cbo having sum(nh) >= 100 and sum(nm) >= 100 order by cbo""").df()
tot_cbo = con.execute("select cbo, count(*) n, avg((sexo=1)::int)*100 pct_h, median(rem) med from v group by 1").df().set_index("cbo")
cel = cel.join(tot_cbo, on="cbo").join(taxa_cbo[["taxa"]], on="cbo").dropna(subset=["taxa"])
cel["gap"] = 100 * (np.exp(cel.d) - 1)
cel["lmed"] = np.log(cel.med)

def wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    return np.average((x - mx) * (y - my), weights=w) / np.sqrt(np.average((x - mx) ** 2, weights=w) * np.average((y - my) ** 2, weights=w))

def boot(fn, n=2000):
    idx = np.arange(len(cel)); vals = []
    for _ in range(n):
        s = cel.iloc[rng.choice(idx, len(idx))]
        vals.append(fn(s))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]

rank = lambda s: s.rank().values
corr = {
    "n_ocupacoes": int(len(cel)), "vinculos": int(cel.n.sum()),
    "pearson_taxa_gap": round(float(wcorr(cel.taxa.values, cel.gap.values, cel.w.values)), 3),
    "pearson_taxa_gap_ic": boot(lambda s: wcorr(s.taxa.values, s.gap.values, s.w.values)),
    "spearman_taxa_gap": round(float(np.corrcoef(rank(cel.taxa), rank(cel.gap))[0, 1]), 3),
    "spearman_taxa_gap_ic": boot(lambda s: np.corrcoef(rank(s.taxa), rank(s.gap))[0, 1]),
    "pearson_taxa_salario": round(float(wcorr(cel.taxa.values, cel.lmed.values, cel.n.values)), 3),
    "pearson_taxa_salario_ic": boot(lambda s: wcorr(s.taxa.values, s.lmed.values, s.n.values)),
    "pearson_homens_gap": round(float(wcorr(cel.pct_h.values, cel.gap.values, cel.w.values)), 3),
    "pearson_homens_gap_ic": boot(lambda s: wcorr(s.pct_h.values, s.gap.values, s.w.values)),
}
# regressão entre ocupações: gap ~ taxa + % homens + log salário mediano (MQP, EP robusto HC1)
Z = np.column_stack([np.ones(len(cel)), cel.taxa, cel.pct_h, cel.lmed]); W = cel.w.values
bz = np.linalg.solve(Z.T @ (Z * W[:, None]), Z.T @ (W * cel.gap.values))
ez = cel.gap.values - Z @ bz
A = np.linalg.inv(Z.T @ (Z * W[:, None])); Bm = (Z * (W * ez)[:, None]).T @ (Z * (W * ez)[:, None])
se_z = np.sqrt(np.diag(A @ Bm @ A) * len(cel) / (len(cel) - 4))
corr["regressao"] = [{"var": n, "coef": round(float(b), 3), "ep": round(float(s), 3)}
                     for n, b, s in zip(["constante", "taxa de acidente (p.p.)", "% homens na ocupação", "log salário mediano"], bz, se_z)]
# quintis de risco: gap médio dentro da ocupação
cel_s = cel.sort_values("taxa").assign(cum=lambda a: a.n.cumsum() / a.n.sum())
cel_s["quintil"] = np.minimum((cel_s.cum * 5).clip(upper=4.9999).astype(int) + 1, 5)
corr["quintis"] = [{"quintil": int(q), "taxa": round(float(np.average(a.taxa, weights=a.n)), 2),
                    "gap_dentro": round(float(np.average(a.gap, weights=a.w)), 1),
                    "pct_h": round(float(np.average(a.pct_h, weights=a.n)), 1)} for q, a in cel_s.groupby("quintil")]
big = cel[cel.n >= 3000]
corr["pontos"] = [{"o": rot(r.cbo), "x": round(r.taxa, 2), "y": round(r.gap, 1), "n": int(r.n), "h": round(r.pct_h)}
                  for r in big.itertuples()]
log("corr", {k: v for k, v in corr.items() if k not in ("pontos", "quintis", "regressao")})

# 3b. interação sexo x risco da ocupação (padronizado), efeito fixo de ocupação
dfr = df.dropna(subset=["taxa"]).copy()
dfr["taxa_z"] = (dfr.taxa - dfr.taxa.mean()) / dfr.taxa.std()
dfr["f_x_taxa"] = dfr.f * dfr.taxa_z
r_int = ols(dfr, HC + ["f_x_taxa"], EMP, "cbo", alvo=("f", "f_x_taxa"))
# 3c. dentro da mesma função: homens em células (CBO x classe CNAE) mais arriscadas?
dfc = df.dropna(subset=["taxa_cel"]).copy()
dif_risco = ols(dfc.assign(rc=dfc.taxa_cel), ["f"], [], "cbo", y="rc")["f"]
sem = ols(dfc, HC, EMP, "cbo")["f"]
com = ols(dfc, HC + ["taxa_cel"], EMP, "cbo", alvo=("f", "taxa_cel"))
risco_dentro = {
    "desvio_padrao_taxa": round(float(dfr.taxa.std()), 3),
    "interacao": {"gap_risco_medio": ic(*r_int["f"]), "coef_interacao_pp": round(100 * r_int["f_x_taxa"][0], 2),
                  "ep_pp": round(100 * r_int["f_x_taxa"][1], 2)},
    "dif_exposicao_pp": round(dif_risco[0], 3), "dif_exposicao_ep": round(dif_risco[1], 3),
    "taxa_media_celula": round(float(dfc.taxa_cel.mean()), 3),
    "gap_sem_risco_celula": ic(*sem), "gap_com_risco_celula": ic(*com["f"]),
    "premio_por_pp_risco": round(100 * com["taxa_cel"][0], 2), "premio_ep": round(100 * com["taxa_cel"][1], 2),
    "cobertura": round(100 * len(dfc) / len(df), 1),
}
log("risco dentro", risco_dentro)

# ---------- 4. Trabalho braçal ----------
occ = con.execute("""select cbo, sexo, count(*) n, avg(ln(rem)) lw, median(rem) med, avg(rem) media from v group by 1,2""").df()
pv = occ.pivot(index="cbo", columns="sexo", values=["n", "lw", "med", "media"]).fillna(0)
nh, nm = pv[("n", 1)], pv[("n", 2)]
ph, pm = nh / nh.sum(), nm / nm.sum()
duncan = 0.5 * float((ph - pm).abs().sum())
lw_h_real = float((pv[("lw", 1)] * nh).sum() / nh.sum()); lw_m_real = float((pv[("lw", 2)] * nm).sum() / nm.sum())
ok = nm >= 30
lw_m_cf = float((ph[ok] * pv.loc[ok, ("lw", 2)]).sum() / ph[ok].sum())      # mulheres com a distribuição ocupacional dos homens
okh = nh >= 30
lw_h_cf = float((pm[okh] * pv.loc[okh, ("lw", 1)]).sum() / pm[okh].sum())  # homens com a distribuição das mulheres
man = con.execute("""select (substr(cbo,1,1) in ('6','7','8','9')) bracal, sexo, count(*) n, avg(rem) media, median(rem) med,
  avg(ln(rem)) lw from v group by 1,2""").df()
tot_s = man.groupby("sexo").n.sum()
man["pct_do_sexo"] = 100 * man.n / man.sexo.map(tot_s)
df["bracal"] = df.cbo.str[0].isin(list("6789")).astype(int)
gb = {k: ic(*ols(df[df.bracal == k], HC, EMP, "cbo")["f"]) for k in (0, 1)}
prem_bracal = ols(df, HC + ["bracal"], EMP, None, alvo=("bracal",))["bracal"]
esp = con.execute("""select cbo, count(*) n, avg((sexo=1)::int)*100 pct_h, median(rem) med from v
  where cbo in ('715210','717020','782510','411010','422105','514320','784205','322205','331205','231210') group by 1""").df()
bracal = {
    "duncan": round(100 * duncan, 1),
    "gap_real_log": round(100 * (lw_m_real - lw_h_real), 1),
    "gap_mulheres_com_ocupacoes_dos_homens": round(100 * (lw_m_cf - lw_h_real), 1),
    "gap_homens_com_ocupacoes_das_mulheres": round(100 * (lw_m_real - lw_h_cf), 1),
    "grupos": [{"bracal": bool(r.bracal), "sexo": int(r.sexo), "n": int(r.n), "pct_do_sexo": round(r.pct_do_sexo, 1),
                "media": round(r.media), "mediana": round(r.med)} for r in man.itertuples()],
    "gap_ajustado_bracal": gb[1], "gap_ajustado_nao_bracal": gb[0],
    "premio_bracal": ic(*prem_bracal),
    "exemplos": [{"ocupacao": rot(r.cbo), "n": int(r.n), "pct_h": round(r.pct_h, 1), "mediana": round(r.med)} for r in esp.sort_values("med").itertuples()],
    "mediana_geral": round(float(con.execute("select median(rem) from v").fetchone()[0])),
}
log("bracal", {k: v for k, v in bracal.items() if k not in ("grupos", "exemplos")})

# ---------- 5. Profissões selecionadas (base completa da profissão) ----------
PROF = {
    "Enfermeiro(a)": ["2235"], "Técnico(a) de enfermagem": ["322205", "322210"], "Auxiliar de enfermagem": ["322230"],
    "Nutricionista": ["223710"], "Psicólogo(a)": ["2515"], "Fisioterapeuta": ["2236"], "Assistente social": ["251605"],
    "Farmacêutico(a)": ["2234"], "Professor(a) educação infantil": ["2311", "3311"],
    "Professor(a) ensino fundamental": ["2312", "2313", "3312"], "Professor(a) ensino médio": ["2321"],
    "Professor(a) ensino superior": ["234"], "Médico(a)": ["2251", "2252", "2253"], "Advogado(a)": ["2410"],
    "Contador(a)": ["252210"], "Engenheiro(a) civil": ["2142"], "Analista de sistemas": ["212405"],
    "Assistente administrativo": ["411010"], "Vendedor(a) do varejo": ["521110"], "Faxineiro(a)": ["514320"],
    "Pedreiro(a)": ["715210"], "Motorista de caminhão": ["782510"],
}
prof = []
for nome, prefs in PROF.items():
    cond = " or ".join(f"cbo like '{p}%'" for p in prefs)
    d = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, mun, div,
      publico::int publico, ln(rem) lw, rem from v where {cond}""").df()
    d["f"] = (d.sexo == 2).astype(float); d["age2"] = d.idade.astype(float) ** 2 / 100; d["ten2"] = d.ten ** 2 / 100; d["lh"] = np.log(d.h)
    row = {"profissao": nome, "n": int(len(d)), "pct_m": round(100 * d.f.mean(), 1),
           "media_m": round(float(d.rem[d.f == 1].mean())), "media_h": round(float(d.rem[d.f == 0].mean())),
           "bruto": round(100 * (d.rem[d.f == 1].mean() / d.rem[d.f == 0].mean() - 1), 1),
           "pct_publico": round(100 * d.publico.mean(), 1)}
    if d.f.sum() >= 100 and (1 - d.f).sum() >= 100:
        cats = ["escolaridade", "tam", "uf", "div"]
        fe = "cbo" if d.cbo.nunique() > 1 else None
        row["ajustado"] = ic(*ols(d, HC, cats, fe, cluster="mun")["f"])
        for setor, s in (("privado", 0), ("publico", 1)):
            ds = d[d.publico == s]
            if ds.f.sum() >= 100 and (1 - ds.f).sum() >= 100:
                row[f"ajustado_{setor}"] = ic(*ols(ds, [x for x in HC if x != "publico"], cats, fe if ds.cbo.nunique() > 1 else None, cluster="mun")["f"])
    prof.append(row)
    log(" prof", nome, row["n"], row["pct_m"], row["bruto"], row.get("ajustado", {}).get("gap"))

# ---------- 6. Robustez ----------
rob_specs = [("Todos", df), ("Setor privado", df[df.publico == 0]), ("Setor público", df[df.publico == 1]),
             ("Só jornada de 40 a 44h", df[df.h.between(40, 44)]), ("Até ensino médio", df[df.escolaridade <= 7]),
             ("Superior completo ou mais", df[df.escolaridade >= 9]), ("Até 29 anos", df[df.idade <= 29]),
             ("40 anos ou mais", df[df.idade >= 40]), ("Salário por hora (em vez de mensal)", df)]
robustez = []
for nome, d in rob_specs:
    y = "lwh" if "hora" in nome else "lw"
    cont = [x for x in HC if not (x == "publico" and d.publico.nunique() == 1)]
    c, se = ols(d, cont, ["escolaridade", "tam", "div"], "cm", y=y)["f"]
    robustez.append({"amostra": nome, "n": int(len(d)), **ic(c, se)})
    log(" robustez", nome, robustez[-1]["gap"])

payload = {"ano": int(ANO), "amostra": int(len(df)), "escada": escada, "quantis": quantis, "correlacao": corr,
           "risco_dentro": risco_dentro, "bracal": bracal, "profissoes": prof, "robustez": robustez}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", OUT)
