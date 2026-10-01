"""Reproduz na RAIS os números citados pela imprensa em 2025-2026 e mede quanto deles sobra com controles.
Uso: python analise/imprensa.py  (roda 2023, 2024, 2025). Saída: resultados/imprensa.json."""
import json, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
OUT = RESULTADOS / "imprensa.json"
AMOSTRA = 20
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
UF = {"11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO","21":"MA","22":"PI","23":"CE","24":"RN","25":"PB",
      "26":"PE","27":"AL","28":"SE","29":"BA","31":"MG","32":"ES","33":"RJ","35":"SP","41":"PR","42":"SC","43":"RS","50":"MS",
      "51":"MT","52":"GO","53":"DF"}
SECOES = [("Agropecuária", 1, 3), ("Indústria extrativa", 5, 9), ("Indústria de transformação", 10, 33), ("Eletricidade, água e resíduos", 35, 39),
          ("Construção", 41, 43), ("Comércio", 45, 47), ("Transporte e correio", 49, 53), ("Alojamento e alimentação", 55, 56),
          ("Informação e comunicação", 58, 63), ("Finanças e seguros", 64, 66), ("Serviços profissionais e técnicos", 68, 75),
          ("Serviços administrativos", 77, 82), ("Administração pública e defesa", 84, 84), ("Educação", 85, 85),
          ("Saúde e serviço social", 86, 88), ("Outros serviços", 90, 99)]
pct = lambda b: round(100 * (np.exp(b) - 1), 1)
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)

def secao_sql():
    return "case " + " ".join(f"when cast(div as int) between {a} and {b} then '{n}'" for n, a, b in SECOES) + " else 'Outros serviços' end"

def design(d, cont, cats):
    X = [d[cont].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def ols(d, cont, cats, fe, alvo="f", cluster="cbo"):
    X = design(d, cont, cats); y = d.lw
    g = d[fe]; X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv); i = X.columns.get_loc(alvo)
    S = pd.DataFrame(Xv * u[:, None]).groupby(d[cluster].values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / (G - 1)
    return float(b[i]), float(np.sqrt(V[i, i]))

def ic(c, se):
    return {"gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]}

HC = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]
res = {}
for ANO in ("2023", "2024", "2025"):
    con = duckdb.connect(); con.execute("set enable_progress_bar=false")
    con.execute(f"""create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999) publico,
      substr(mun,1,2) uf from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
    r = {}
    q = lambda s: con.execute(s).df().iloc[0]
    # 1. universo do MTE: setor privado, estabelecimentos com 100+ empregados
    x = q("select avg(rem) filter (where sexo=2) m, avg(rem) filter (where sexo=1) h, count(*) n from v where not publico and tam >= 7")
    r["mte_bruto"] = round(100 * (x.m / x.h - 1), 1); r["mte_media_m"] = round(x.m); r["mte_media_h"] = round(x.h); r["mte_n"] = int(x.n)
    # 2. todo o emprego formal (como o Cadastro Central de Empresas do IBGE): quanto os homens ganham a mais
    x = q("select avg(rem) filter (where sexo=2) m, avg(rem) filter (where sexo=1) h from v")
    r["formal_homens_a_mais"] = round(100 * (x.h / x.m - 1), 1); r["formal_mulheres_a_menos"] = round(100 * (x.m / x.h - 1), 1)
    # 3. superior completo e 4. direção e gerência (CBO grupo 1)
    for k, cond in (("superior", "escolaridade >= 9"), ("gestao", "cbo like '1%'")):
        x = q(f"select avg(rem) filter (where sexo=2) m, avg(rem) filter (where sexo=1) h from v where {cond}")
        r[f"{k}_bruto"] = round(100 * (x.m / x.h - 1), 1); r[f"{k}_media_m"] = round(x.m); r[f"{k}_media_h"] = round(x.h)
    # 5. setores e 6. estados (bruto na base completa)
    sec = con.execute(f"""select {secao_sql()} secao, count(*) n, avg((sexo=2)::int)*100 pm,
      avg(rem) filter (where sexo=2) / avg(rem) filter (where sexo=1) * 100 - 100 bruto from v group by 1""").df()
    ufs = con.execute(f"""select uf, avg(rem) filter (where sexo=2) / avg(rem) filter (where sexo=1) * 100 razao
      from v where not publico and tam >= 7 and uf in {tuple(UF)} group by 1""").df()
    # 7. raça: mulheres negras x homens não negros
    x = q("""select avg(rem) filter (where sexo=2 and raca in (4,8)) mn, avg(rem) filter (where sexo=1 and raca in (2,6)) hb from v""")
    r["raca_bruto"] = round(100 * (x.mn / x.hb - 1), 1)

    # amostra para os ajustes
    df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, uf, mun, div, raca,
      publico::int publico, ln(rem) lw, {secao_sql()} secao
      from v where hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
    df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100
    df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h); df["cm"] = df.cbo + "_" + df.mun
    EMP = ["escolaridade", "tam", "uf", "div"]
    mte = df[(df.publico == 0) & (df.tam >= 7)]
    r["mte_mesma_ocupacao"] = ic(*ols(mte, [c for c in HC if c != "publico"], EMP, "cbo"))
    r["mte_mesma_ocupacao_cidade"] = ic(*ols(mte, [c for c in HC if c != "publico"], ["escolaridade", "tam", "div"], "cm"))
    r["todos_mesma_ocupacao_cidade"] = ic(*ols(df, HC, ["escolaridade", "tam", "div"], "cm"))
    sup = df[df.escolaridade >= 9]
    r["superior_ajustado"] = ic(*ols(sup, HC, EMP, "cbo"))
    ges = df[df.cbo.str.startswith("1")]
    r["gestao_ajustado"] = ic(*ols(ges, HC, EMP, "cbo"))
    # raça: mulher negra x homem não negro, mesma ocupação e perfil
    rc = df[((df.f == 1) & df.raca.isin([4, 8])) | ((df.f == 0) & df.raca.isin([2, 6]))]
    r["raca_ajustado"] = ic(*ols(rc, HC, EMP, "cbo"))
    # setores: gap ajustado dentro de cada seção (mesma ocupação)
    setores = []
    for s in sec.itertuples():
        d = df[df.secao == s.secao]
        adj = ic(*ols(d, HC, ["escolaridade", "tam", "uf"], "cbo")) if d.f.sum() > 300 and (1 - d.f).sum() > 300 else None
        setores.append({"secao": s.secao, "n": int(s.n), "pct_m": round(s.pm, 1), "bruto": round(s.bruto, 1), "ajustado": adj})
    r["setores"] = sorted(setores, key=lambda z: z["bruto"])
    # estados: razão bruta (universo MTE) x gap ajustado (todos, mesma ocupação)
    estados = []
    for u in ufs.itertuples():
        d = df[df.uf == u.uf]
        adj = ic(*ols(d, HC, ["escolaridade", "tam", "div"], "cbo"))
        estados.append({"uf": UF.get(u.uf, u.uf), "razao_bruta": round(u.razao, 1), "ajustado": adj})
    r["estados"] = sorted(estados, key=lambda z: z["razao_bruta"])
    br = np.array([e["razao_bruta"] for e in estados]); aj = np.array([e["ajustado"]["gap"] for e in estados])
    r["estados_corr_bruto_ajustado"] = round(float(np.corrcoef(br, aj)[0, 1]), 2)
    r["estados_amplitude_bruta"] = round(float(br.max() - br.min()), 1)
    r["estados_amplitude_ajustada"] = round(float(aj.max() - aj.min()), 1)
    res[ANO] = r
    log(ANO, {k: v for k, v in r.items() if k not in ("setores", "estados")})

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", OUT)
