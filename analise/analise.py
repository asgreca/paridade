"""Gap salarial homem x mulher na RAIS (uso: python analise/analise.py ANO): testa a tese de que o gap salarial é multivariado (profissão, horas, risco, carreira).
Três eixos: instrução, idade/maternidade, e ocupações de risco, confinamento e turno.
Entrada: <DADOS>/<ANO>/rais_*.parquet (etl.py). Saída: resultados/dados_ANO.json e resultados/evolucao.json."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
LABELS = CBO_LABELS
ANO = sys.argv[1]
OUT = RESULTADOS / f"dados_{ANO}.json"
AMOSTRA = 20  # 1 em cada N vínculos entra nas regressões

FAIXA = {1: "Até fund. incompleto", 2: "Até fund. incompleto", 3: "Até fund. incompleto", 4: "Até fund. incompleto",
         5: "Fundamental completo", 6: "Médio incompleto", 7: "Médio completo", 8: "Superior incompleto",
         9: "Superior completo", 10: "Mestrado ou doutorado", 11: "Mestrado ou doutorado"}
ORDEM_FAIXA = list(dict.fromkeys(FAIXA.values()))
FX_IDADE = [15, 24, 29, 34, 39, 44, 49, 54, 70]
ROT_IDADE = ["16-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55+"]

# Grupos de ocupação (prefixos CBO 2002 conferidos nos rótulos oficiais). Ordem = prioridade.
GRUPOS = {
    "Confinamento, embarcado ou subsolo": ["7111", "7112", "7113", "3412", "3413", "7827", "3163", "862110"],
    "Periculosidade (NR-16)": ["7321", "9511", "7156", "521135", "519110", "519115", "5173", "5172", "711120"],
    "Turnos irregulares": ["5171", "3222", "2235", "7824", "7825", "8110", "8621", "8622"],
}
CNAE_EXTRATIVA = ("05", "06", "07", "08", "09")

FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
pct = lambda b: round(100 * (np.exp(b) - 1), 1)

con = duckdb.connect()
con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select *, cast(substr(cnae,1,2) as varchar) div,
  (natjur between 1000 and 1999) publico,
  (10 in (ca1,ca2,ca3) or 30 in (ca1,ca2,ca3)) acidente,
  (50 in (ca1,ca2,ca3)) licenca
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
rotulos = json.loads(Path(LABELS).read_text(encoding="utf-8"))
rot = lambda c: rotulos.get(c, c)
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)

def grupo_sql():
    casos = []
    for nome, prefs in GRUPOS.items():
        cond = " or ".join(f"cbo like '{p}%'" for p in prefs)
        if nome.startswith("Confinamento"):
            cond += " or (div in " + str(CNAE_EXTRATIVA) + " and substr(cbo,1,1) in ('7','8','9'))"
        casos.append(f"when {cond} then '{nome}'")
    return "case " + " ".join(casos) + " else 'Demais ocupações' end"

# ---------- 1. Números gerais ----------
tot = con.execute(f"select count(*) from '{DADOS}/{ANO}/rais_*.parquet'").fetchone()[0]
g = con.execute("""
select count(*) n, count(*) filter (where sexo=2) n_m,
  avg(rem) filter (where sexo=1) rem_h, avg(rem) filter (where sexo=2) rem_m,
  median(rem) filter (where sexo=1) med_h, median(rem) filter (where sexo=2) med_m,
  avg(horas) filter (where sexo=1) hor_h, avg(horas) filter (where sexo=2) hor_m,
  avg(rem/(horas*4.348)) filter (where sexo=1) hora_h, avg(rem/(horas*4.348)) filter (where sexo=2) hora_m,
  avg((escolaridade>=9)::int) filter (where sexo=1) sup_h, avg((escolaridade>=9)::int) filter (where sexo=2) sup_m,
  avg((horas<=30)::int) filter (where sexo=1) parcial_h, avg((horas<=30)::int) filter (where sexo=2) parcial_m,
  count(*) filter (where licenca) n_licenca, count(*) filter (where acidente) n_acidente
from v""").df().iloc[0]
geral = {k: float(v) for k, v in g.items()}
geral.update(n_total_ativos=int(tot), n=int(g.n), n_m=int(g.n_m), n_licenca=int(g.n_licenca), n_acidente=int(g.n_acidente),
             pct_mulheres=round(100 * g.n_m / g.n, 1), gap_mensal=round(100 * (g.rem_m / g.rem_h - 1), 1),
             gap_mediana=round(100 * (g.med_m / g.med_h - 1), 1), gap_hora=round(100 * (g.hora_m / g.hora_h - 1), 1))
log("geral", geral["n"], geral["gap_mensal"])

# ---------- 2. Taxa de acidente por ocupação (base completa) ----------
# Registro de afastamentos ficou incompleto a partir de 2024 (todas as causas caem 35-50%): a taxa de
# acidente da ocupação vem sempre de 2023; % homens e salário vêm do ano analisado.
acid = con.execute(f"""
with a as (select cbo, avg((10 in (ca1,ca2,ca3) or 30 in (ca1,ca2,ca3))::int) taxa
           from '{DADOS}/2023/rais_*.parquet' where {FILTRO} group by 1)
select cbo, count(*) n, coalesce(any_value(a.taxa),0) taxa, avg((sexo=1)::int) pct_h, median(rem/(horas*4.348)) med_hora
from v left join a using(cbo) group by 1""").df()
acid_map = acid.set_index("cbo").taxa

# ---------- 3. Amostra para regressões ----------
df = con.execute(f"""
select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, mun, div, publico::int publico,
  licenca::int licenca, ln(rem) lw, case when rem_dez>0 then ln(rem_dez) end lwd, {grupo_sql()} grupo
from v where hash(cbo||mun||idade||rem||ten) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float)
df["age2"] = df.idade.astype(float) ** 2 / 100
df["ten2"] = df.ten ** 2 / 100
df["lh"] = np.log(df.h)
df["faixa"] = df.escolaridade.map(FAIXA)
df["fx_idade"] = pd.cut(df.idade, FX_IDADE, labels=ROT_IDADE).astype(str)
df["cm"] = df.cbo + "_" + df.mun
df["taxa_acid"] = df.cbo.map(acid_map).fillna(0) * 100
log("amostra", len(df))

def design(d, cont, cats):
    X = [d[cont].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def ols(d, cont, cats, fe=None, y="lw"):
    X = design(d, cont, cats); yy = d[y]
    if fe is not None:
        grp = d[fe]
        X = X - X.groupby(grp).transform("mean"); yy = yy - yy.groupby(grp).transform("mean")
    else:
        X = X.assign(const=1.0)
    b, *_ = np.linalg.lstsq(X.values, yy.values, rcond=None)
    return pd.Series(b, index=X.columns)

HC = ["f", "lh", "idade", "age2", "ten", "ten2"]
EMP = ["escolaridade", "tam", "uf", "div"]

# ---------- 4. Escada de controles (remuneração mensal) ----------
escada_specs = [
    ("Comparação direta", "Média de todas as mulheres contra a de todos os homens", ["f"], [], None),
    ("Mesma jornada", "Mesmas horas semanais contratadas", ["f", "lh"], [], None),
    ("Mesma instrução", "Mesmo grau de instrução", ["f", "lh"], ["escolaridade"], None),
    ("Mesma idade e tempo de casa", "Mesma idade e mesma antiguidade no emprego", HC, ["escolaridade"], None),
    ("Mesmo tipo de empregador", "Mesmo porte, estado, setor econômico e público ou privado", HC + ["publico"], EMP, None),
    ("Mesma ocupação", "Mesma função (CBO de 6 dígitos)", HC + ["publico"], EMP, "cbo"),
    ("Mesma ocupação, mesma cidade", "Mesma função no mesmo município", HC + ["publico"], ["escolaridade", "tam", "div"], "cm"),
]
escada = []
for nome, desc, cont, cats, fe in escada_specs:
    b = ols(df, cont, cats, fe)["f"]
    escada.append({"passo": nome, "desc": desc, "gap": pct(b)})
    log(" escada", nome, pct(b))

# ---------- 5. Decomposição Oaxaca-Blinder (pooled com dummy de sexo, Fortin 2008) ----------
cont = HC + ["publico"]
X = design(df, cont, EMP)
grp = df.cbo
Xd = X - X.groupby(grp).transform("mean"); yd = df.lw - df.lw.groupby(grp).transform("mean")
b = pd.Series(np.linalg.lstsq(Xd.values, yd.values, rcond=None)[0], index=X.columns)
resid = df.lw - X.drop(columns="f").values @ b.drop("f").values - b["f"] * df.f
fe_cbo = resid.groupby(df.cbo).mean()
m, fm = df.f == 0, df.f == 1
bruto = df.lw[fm].mean() - df.lw[m].mean()
blocos = {
    "Horas trabalhadas": ["lh"],
    "Instrução": [c for c in X.columns if c.startswith("escolaridade_")],
    "Idade": ["idade", "age2"],
    "Tempo de casa": ["ten", "ten2"],
    "Setor, porte, estado e público/privado": [c for c in X.columns if c.startswith(("tam_", "uf_", "div_"))] + ["publico"],
}
fatores = [{"fator": k, "log": float(((X.loc[fm, c].mean() - X.loc[m, c].mean()) * b[c]).sum())} for k, c in blocos.items()]
# Parte da ocupação: projeta o efeito fixo da ocupação nas características de risco (nível CBO, ponderado)
cb = df.groupby("cbo").agg(n=("f", "size"), taxa=("taxa_acid", "first"), grupo=("grupo", "first"))
cb["fe"] = fe_cbo
Z = pd.get_dummies(cb.grupo, dtype=float).drop(columns="Demais ocupações")
Z["taxa"] = cb.taxa
Zc = Z.assign(const=1.0)
w = np.sqrt(cb.n.values)
gam = pd.Series(np.linalg.lstsq(Zc.values * w[:, None], cb.fe.values * w, rcond=None)[0], index=Zc.columns)
ocup_total = df.cbo.map(fe_cbo)
c_ocup = float(ocup_total[fm].mean() - ocup_total[m].mean())
dif = lambda s_: float(s_[fm].mean() - s_[m].mean())
c_grupos = dif(df.cbo.map((Z.drop(columns="taxa") * gam[Z.columns.drop("taxa")]).sum(axis=1)))
c_taxa = dif(df.cbo.map(Z.taxa * gam["taxa"]))
fatores += [{"fator": "Adicionais: periculosidade, confinamento e turno", "log": c_grupos},
            {"fator": "Risco de acidente da ocupação", "log": c_taxa},
            {"fator": "Demais diferenças de ocupação", "log": c_ocup - c_grupos - c_taxa}]
explicado = sum(x["log"] for x in fatores)
fatores.append({"fator": "Não explicado", "log": float(b["f"])})
for x in fatores:
    x["pp"] = round(100 * x["log"], 1)
decomposicao = {"bruto_pp": round(100 * bruto, 1), "explicado_pp": round(100 * explicado, 1),
                "nao_explicado_pp": round(100 * b["f"], 1), "fatores": fatores,
                "premio_risco": {k: round(100 * v, 1) for k, v in gam.items() if k != "const"}}
log("oaxaca", decomposicao["bruto_pp"], [(x["fator"], x["pp"]) for x in fatores])

# ---------- 6. Instrução ----------
ef = con.execute("""select escolaridade, sexo, count(*) n, avg(rem) rem, avg(rem/(horas*4.348)) hora, avg(horas) horas
  from v group by 1,2""").df()
ef["faixa"] = ef.escolaridade.map(FAIXA)
ef = ef.assign(remw=ef.rem * ef.n, horaw=ef.hora * ef.n, horasw=ef.horas * ef.n).groupby(["faixa", "sexo"])[["n", "remw", "horaw", "horasw"]].sum()
instrucao = []
for fx in ORDEM_FAIXA:
    d = df[df.faixa == fx]
    cats = ["tam", "uf", "div"] + (["escolaridade"] if d.escolaridade.nunique() > 1 else [])
    adj = ols(d, HC + ["publico"], cats, "cbo")["f"]
    h, mm = ef.loc[(fx, 1)], ef.loc[(fx, 2)]
    instrucao.append({"faixa": fx, "n_h": int(h.n), "n_m": int(mm.n), "pct_m": round(100 * mm.n / (h.n + mm.n), 1),
                      "rem_h": round(h.remw / h.n), "rem_m": round(mm.remw / mm.n),
                      "horas_h": round(h.horasw / h.n, 1), "horas_m": round(mm.horasw / mm.n, 1),
                      "gap_bruto": round(100 * ((mm.remw / mm.n) / (h.remw / h.n) - 1), 1), "gap_ajustado": pct(adj)})
    log(" instrucao", fx, instrucao[-1]["gap_bruto"], instrucao[-1]["gap_ajustado"])
gap_sem_instrucao = pct(ols(df, HC + ["publico"], ["tam", "uf", "div"], "cbo")["f"])

top = con.execute("""
with s as (select cbo, sexo, count(*) n, median(rem) med from v where escolaridade>=9 group by 1,2),
t as (select sexo, sum(n) tot from s group by 1)
select s.*, 100.0*n/tot as pct_do_sexo from s join t using(sexo)
qualify row_number() over (partition by sexo order by n desc) <= 10 order by sexo, n desc""").df()
pm_cbo = con.execute("select cbo, avg((sexo=2)::int) pm from v where escolaridade>=9 group by 1").df().set_index("cbo").pm
top_diploma = {k: [{"ocupacao": rot(r.cbo), "pct_do_sexo": round(r.pct_do_sexo, 1), "mediana": round(r.med),
                    "pct_m": round(100 * pm_cbo[r.cbo], 1)} for r in top[top.sexo == s].itertuples()]
               for s, k in [(1, "homens"), (2, "mulheres")]}

# ---------- 7. Idade, maternidade e carreira ----------
idade = []
for fx in ROT_IDADE:
    d = df[df.fx_idade == fx]
    adj = ols(d, ["f", "lh", "idade", "ten", "ten2", "publico"], EMP, "cbo")["f"]
    idade.append({"faixa": fx, "bruto": pct(d.lw[d.f == 1].mean() - d.lw[d.f == 0].mean()), "ajustado": pct(adj)})
desc_idade = con.execute(f"""
select case {' '.join(f"when idade<={hi} then '{r}'" for hi, r in zip(FX_IDADE[1:], ROT_IDADE))} end faixa, sexo,
  avg(tempo) tempo, avg((cbo like '1%')::int) gestao, avg(licenca::int) licenca, avg(horas) horas,
  avg((cbo like '1%')::int) filter (where escolaridade>=9) gestao_sup
from v group by 1,2""").df()
for r in idade:
    for s, suf in [(1, "h"), (2, "m")]:
        x = desc_idade[(desc_idade.faixa == r["faixa"]) & (desc_idade.sexo == s)].iloc[0]
        r[f"tempo_{suf}"] = round(x.tempo, 1); r[f"gestao_{suf}"] = round(100 * x.gestao, 2)
        r[f"gestao_sup_{suf}"] = round(100 * x.gestao_sup, 1); r[f"licenca_{suf}"] = round(100 * x.licenca, 2)
        r[f"horas_{suf}"] = round(x.horas, 1)
log("idade", [(r["faixa"], r["ajustado"]) for r in idade])

# Licença-maternidade em 2023: mulheres de 20 a 45 anos
w = df[(df.f == 1) & df.idade.between(20, 45)].copy()
c_mat = ["licenca", "lh", "idade", "age2", "ten", "ten2", "publico"]
lic_media = pct(ols(w, c_mat, EMP, "cbo")["licenca"])
wd = w[w.lwd.notna()]
lic_dez = pct(ols(wd, c_mat, EMP, "cbo", y="lwd")["licenca"])
# gap de gênero na faixa fértil (20-39) só entre quem NÃO teve licença em 2023
f20 = df[df.idade.between(20, 39) & (df.licenca == 0)]
gap_sem_lic = pct(ols(f20, ["f", "lh", "idade", "age2", "ten", "ten2", "publico"], EMP, "cbo")["f"])
f20b = df[df.idade.between(20, 39)]
gap_com_lic = pct(ols(f20b, ["f", "lh", "idade", "age2", "ten", "ten2", "publico"], EMP, "cbo")["f"])
mat = con.execute("""select count(*) filter (where licenca and sexo=2) n,
  avg(tempo) filter (where licenca and sexo=2) tempo_lic, avg(tempo) filter (where not licenca and sexo=2 and idade between 20 and 45) tempo_outras,
  median(idade) filter (where licenca and sexo=2) idade_med
  from v""").df().iloc[0]
maternidade = {"n": int(mat.n), "idade_mediana": float(mat.idade_med), "efeito_media_ano": lic_media, "efeito_dezembro": lic_dez,
               "gap_20_39_todas": gap_com_lic, "gap_20_39_sem_licenca": gap_sem_lic,
               "tempo_lic": round(mat.tempo_lic, 1), "tempo_outras": round(mat.tempo_outras, 1)}
log("maternidade", maternidade)

# ---------- 8. Risco, confinamento e turno ----------
gd = con.execute(f"""select {grupo_sql()} grupo, count(*) n, avg((sexo=1)::int) pct_h, avg(rem) rem,
  median(rem/(horas*4.348)) med_hora from v group by 1""").df()
gd["taxa"] = gd.grupo.map(df.assign(t=df.taxa_acid / 100).groupby("grupo").t.mean())
prem = ols(df.assign(**{f"g{i}": (df.grupo == k).astype(float) for i, k in enumerate(GRUPOS)}),
           ["f", "lh", "idade", "age2", "ten", "ten2", "publico"] + [f"g{i}" for i in range(len(GRUPOS))], ["escolaridade", "tam", "uf"])
grupos = []
for i, k in enumerate(list(GRUPOS) + ["Demais ocupações"]):
    x = gd[gd.grupo == k].iloc[0]
    exemplos = acid[acid.cbo.str.startswith(tuple(GRUPOS[k]))].nlargest(5, "n").cbo.map(rot).tolist() if k in GRUPOS else []
    grupos.append({"grupo": k, "n": int(x.n), "pct_h": round(100 * x.pct_h, 1), "rem": round(x.rem),
                   "taxa_acidente": round(100 * x.taxa, 2), "premio": pct(prem[f"g{i}"]) if k in GRUPOS else 0.0,
                   "exemplos": exemplos})
# quintis de risco medido (taxa de acidente da ocupação, ponderado por trabalhadores)
acid_s = acid.sort_values("taxa").assign(cum=lambda a: a.n.cumsum() / a.n.sum())
acid_s["quintil"] = np.minimum((acid_s.cum * 5).clip(upper=4.9999).astype(int) + 1, 5)
quintis = [{"quintil": int(q), "taxa": round(100 * (a.taxa * a.n).sum() / a.n.sum(), 2),
            "pct_h": round(100 * (a.pct_h * a.n).sum() / a.n.sum(), 1),
            "med_hora": round(float((a.med_hora * a.n).sum() / a.n.sum()), 2)} for q, a in acid_s.groupby("quintil")]
# gap sem as ocupações de risco/confinamento/turno
dem = df[df.grupo == "Demais ocupações"]
gap_sem_risco = pct(ols(dem, HC + ["publico"], EMP, "cbo")["f"])
gap_sem_risco_bruto = pct(dem.lw[dem.f == 1].mean() - dem.lw[dem.f == 0].mean())
risco = {"grupos": grupos, "quintis": quintis, "gap_sem_risco": gap_sem_risco, "gap_sem_risco_bruto": gap_sem_risco_bruto}
log("risco", gap_sem_risco, [(x["grupo"][:12], x["pct_h"], x["premio"]) for x in grupos])

# ---------- 9. Dentro da mesma ocupação e mesma instrução (base completa, por hora) ----------
ocup = con.execute("""
with c as (select cbo, escolaridade, sexo, count(*) n, avg(ln(rem/(horas*4.348))) lw from v group by 1,2,3),
p as (select h.cbo, h.n nh, m.n nm, m.lw - h.lw d from c h join c m
      on h.cbo=m.cbo and h.escolaridade=m.escolaridade and h.sexo=1 and m.sexo=2)
select cbo, sum(nh) nh, sum(nm) nm, sum(d*least(nh,nm))/sum(least(nh,nm)) d
from p group by cbo having sum(nh)>=200 and sum(nm)>=200""").df()
ocup["gap"] = (100 * (np.exp(ocup.d) - 1)).round(1)
ocup["n"] = ocup.nh + ocup.nm
hist = pd.cut(ocup.gap.clip(-49.9, 49.9), list(range(-50, 55, 5))).value_counts().sort_index()
grandes = ocup.nlargest(25, "n")
ocupacoes = {"n": int(len(ocup)), "vinculos": int(ocup.n.sum()),
             "mulher_ganha_mais": int((ocup.gap > 2).sum()), "empate": int(ocup.gap.between(-2, 2).sum()),
             "homem_ganha_mais": int((ocup.gap < -2).sum()), "mediana_gap": round(float(ocup.gap.median()), 1),
             "hist": [{"de": int(i.left), "ate": int(i.right), "n": int(v)} for i, v in hist.items()],
             "grandes": [{"ocupacao": rot(r.cbo), "n": int(r.n), "pct_m": round(100 * r.nm / r.n, 1), "gap": float(r.gap)}
                         for r in grandes.itertuples()]}
log("ocupacoes", ocupacoes["n"], ocupacoes["mulher_ganha_mais"], ocupacoes["homem_ganha_mais"])

# ---------- 10. Distribuição de horas ----------
horas = con.execute("""
select case when horas<=20 then 'Até 20h' when horas<=30 then '21 a 30h' when horas<40 then '31 a 39h'
            when horas<44 then '40 a 43h' else '44h' end faixa,
  100.0*count(*) filter (where sexo=1)/sum(count(*) filter (where sexo=1)) over () h,
  100.0*count(*) filter (where sexo=2)/sum(count(*) filter (where sexo=2)) over () m
from v group by 1""").df().set_index("faixa").loc[["Até 20h", "21 a 30h", "31 a 39h", "40 a 43h", "44h"]].round(1).reset_index()

payload = {
    "meta": {"ano": int(ANO), "fonte": f"RAIS {ANO}, Ministério do Trabalho e Emprego (microdados públicos de vínculos)",
             "gerado": time.strftime("%Y-%m-%d"), "amostra_regressoes": int(len(df)), "fracao_amostra": f"1 em {AMOSTRA}",
             "filtro": f"Vínculos ativos em 31/12/{ANO} com jornada contratada de 10 a 48 h/semana, remuneração média de R$ 500 ou mais e idade de 16 a 70 anos."},
    "geral": geral, "escada": escada, "decomposicao": decomposicao, "instrucao": instrucao,
    "gap_sem_instrucao": gap_sem_instrucao, "top_diploma": top_diploma, "idade": idade, "maternidade": maternidade,
    "risco": risco, "ocupacoes": ocupacoes, "horas": horas.to_dict("records"),
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", OUT)

# resumo por ano para a seção de evolução
EVO = RESULTADOS / "evolucao.json"
evo = json.loads(EVO.read_text(encoding="utf-8")) if EVO.exists() else {}
fat = {x["fator"]: x["pp"] for x in decomposicao["fatores"]}
evo[ANO] = {"n": geral["n"], "pct_mulheres": geral["pct_mulheres"], "gap_mensal": geral["gap_mensal"],
            "gap_bruto": escada[0]["gap"], "gap_instrucao": escada[2]["gap"], "gap_ocupacao": escada[-2]["gap"],
            "gap_final": escada[-1]["gap"], "nao_explicado_pp": decomposicao["nao_explicado_pp"],
            "sup_m": geral["sup_m"], "sup_h": geral["sup_h"], "horas_pp": fat["Horas trabalhadas"],
            "instrucao_pp": fat["Instrução"], "gap_idade_50_54": idade[-2]["ajustado"], "gap_idade_16_24": idade[0]["ajustado"]}
EVO.write_text(json.dumps(dict(sorted(evo.items())), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("evolucao", sorted(evo))
