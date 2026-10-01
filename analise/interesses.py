"""Homens e mulheres no eixo pessoas x coisas de Prediger, medido pelo conteúdo das ocupações (O*NET), e o salário ao longo dele.
Requer dados_auxiliares/cbo_riasec.csv (python analise/prepara_interesses.py).
Uso: python analise/interesses.py ANO. Saída: resultados/interesses_ANO.json.

1. Cobertura da ligação CBO -> O*NET, em vínculos, por nível (manual, direto, família).
2. d de Cohen entre homens e mulheres nas notas das ocupações em que trabalham (positivo = homens acima), nos eixos
   pessoas/coisas e dados/ideias e nos seis tipos RIASEC. Comparável em sinal ao d = 0,93 de Su, Rounds e Armstrong (2009),
   mas mede o emprego que as pessoas têm, não o interesse declarado em questionário.
3. Quintis do eixo pessoas/coisas: % de mulheres, mediana salarial e gap na mesma ocupação (efeito fixo de CBO).
4. Tipo RIASEC dominante da ocupação: mesma tabela.
5. Regressão sem efeito fixo de ocupação: quanto o eixo paga (por desvio-padrão) e se o gap muda ao longo dele.
6. Áreas STEM pelos grupos ISCO-08, no recorte de Su e colegas: engenharia, computação, ciências exatas e da vida, saúde.
7. Robustez: o d só com a ligação oficial (níveis direto e família), sem a ligação manual."""
import json, sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))
from config import DADOS, RESULTADOS

ANO = sys.argv[1]
OUT = RESULTADOS / f"interesses_{ANO}.json"
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
AMOSTRA = 20
pct = lambda b: round(100 * (np.exp(b) - 1), 2)
LET = list("RIASEC")
NOME = {"R": "Realista", "I": "Investigativo", "A": "Artístico", "S": "Social", "E": "Empreendedor", "C": "Convencional"}

tab = pd.read_csv(AQUI / "dados_auxiliares" / "cbo_riasec.csv", dtype={"cbo": str, "isco08": str})
con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.register("tab", tab)
con.execute(f"""create view v as select p.*, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico, t.*
  exclude (cbo) from '{DADOS}/{ANO}/rais_*.parquet' p left join tab t on t.cbo = p.cbo where {FILTRO}""")

cob = con.execute("select coalesce(nivel,'sem') nivel, count(*) n from v group by 1").df().set_index("nivel").n
cobertura = {k: round(100 * float(v) / cob.sum(), 2) for k, v in cob.items()}

def cohen(col, where="pessoas_coisas is not null"):
    r = con.execute(f"""select avg({col}) filter (where sexo=1) mh, avg({col}) filter (where sexo=2) mm,
      var_samp({col}) filter (where sexo=1) vh, var_samp({col}) filter (where sexo=2) vm,
      count(*) filter (where sexo=1) nh, count(*) filter (where sexo=2) nm from v where {where}""").df().iloc[0]
    sp = np.sqrt(((r.nh - 1) * r.vh + (r.nm - 1) * r.vm) / (r.nh + r.nm - 2))
    return {"media_h": round(float(r.mh), 3), "media_m": round(float(r.mm), 3), "d": round(float((r.mh - r.mm) / sp), 3)}

d = {"pessoas_coisas": cohen("pessoas_coisas"), "dados_ideias": cohen("dados_ideias"), **{NOME[l]: cohen(l) for l in LET}}
d_oficial = {"pessoas_coisas": cohen("pessoas_coisas", "pessoas_coisas is not null and nivel in ('direto','familia')"),
             "dados_ideias": cohen("dados_ideias", "pessoas_coisas is not null and nivel in ('direto','familia')")}

# distribuição do eixo por sexo (para o gráfico)
lim = con.execute("select quantile_cont(pessoas_coisas,0.005), quantile_cont(pessoas_coisas,0.995) from v").fetchone()
bordas = np.linspace(lim[0], lim[1], 31)
hist = con.execute(f"""select sexo, least(30, greatest(1, floor((pessoas_coisas - {bordas[0]}) / ({bordas[-1]} - {bordas[0]}) * 30) + 1))::int b, count(*) n
  from v where pessoas_coisas is not null group by 1,2""").df()
hist["b"] = hist.b.clip(1, 30)
hp = hist.groupby(["b", "sexo"]).n.sum().unstack(fill_value=0)
hp = hp / hp.sum()
distribuicao = [{"de": round(float(bordas[i - 1]), 2), "ate": round(float(bordas[i]), 2),
                 "h": round(float(hp.loc[i, 1]) if i in hp.index else 0, 4), "m": round(float(hp.loc[i, 2]) if i in hp.index else 0, 4)} for i in range(1, 31)]

# amostra para regressões
df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, div, publico, ln(rem) lw,
  pessoas_coisas pc, dados_ideias di, tipo, isco08 from v where pessoas_coisas is not null and hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100; df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)

def ols(d_, cont, cats, fe=None, alvo=("f",)):
    X = pd.concat([d_[cont].astype(float)] + [pd.get_dummies(d_[c], prefix=c, drop_first=True, dtype=float) for c in cats], axis=1)
    y = d_.lw
    if fe:
        g = d_[fe]; X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
    else:
        X = X.assign(const=1.0)
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv); S = pd.DataFrame(Xv * u[:, None]).groupby(d_.cbo.values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / max(G - 1, 1)
    return {a: (float(b[X.columns.get_loc(a)]), float(np.sqrt(V[X.columns.get_loc(a), X.columns.get_loc(a)]))) for a in alvo}

HC = ["f", "lh", "idade", "age2", "ten", "ten2", "publico"]
EMP = ["escolaridade", "tam", "uf", "div"]
ic = lambda c, se: {"gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]}

def bloco(col, ordem=None):
    out = []
    for k, g in df.groupby(col, observed=True):
        if g.f.sum() < 300 or (1 - g.f).sum() < 300:
            continue
        c, se = ols(g, HC, EMP, "cbo")["f"]
        out.append({"grupo": str(k), "n": int(len(g)) * AMOSTRA, "pct_m": round(100 * g.f.mean(), 1),
                    "mediana": round(float(np.exp(g.lw.median()))), **ic(c, se)})
    return out

df["quintil"] = pd.qcut(df.pc, 5, labels=["1º (mais pessoas)", "2º", "3º", "4º", "5º (mais coisas)"])
quintis = bloco("quintil")
for q, (lo, hi) in zip(quintis, df.groupby("quintil", observed=True).pc.agg(["min", "max"]).values):
    q["faixa"] = [round(float(lo), 2), round(float(hi), 2)]
tipos = bloco("tipo")
for t in tipos:
    t["grupo"] = NOME[t["grupo"]]

# o eixo paga? (sem efeito fixo de ocupação)
df["pc_z"] = (df.pc - df.pc.mean()) / df.pc.std(); df["di_z"] = (df.di - df.di.mean()) / df.di.std(); df["f_pc"] = df.f * df.pc_z
r = ols(df, HC + ["pc_z", "di_z", "f_pc"], EMP, None, alvo=("f", "pc_z", "di_z", "f_pc"))
eixo_paga = {"premio_coisas_por_dp": ic(*r["pc_z"]), "premio_dados_por_dp": ic(*r["di_z"]),
             "gap_no_meio_do_eixo": ic(*r["f"]), "mudanca_do_gap_por_dp_para_coisas_pp": round(100 * r["f_pc"][0], 2),
             "ep_pp": round(100 * r["f_pc"][1], 2)}

# STEM pelos grupos ISCO-08 (recorte de Su e colegas)
STEM = {"Engenharia": ("214", "215"), "Computação e TI": ("25",), "Ciências exatas": ("211", "212"),
        "Ciências da vida": ("213",), "Medicina e saúde (nível superior)": ("22",)}
df["stem"] = None
for k, ps in STEM.items():
    df.loc[df.isco08.fillna("").str.startswith(ps), "stem"] = k
stem = bloco("stem")

OUT.write_text(json.dumps({"ano": int(ANO), "cobertura_vinculos_pct": cobertura, "d": d, "d_so_ligacao_oficial": d_oficial,
                           "distribuicao": distribuicao, "quintis": quintis, "tipos": tipos, "eixo_paga": eixo_paga, "stem": stem,
                           "amostra": int(len(df))}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
print(json.dumps({"cobertura": cobertura, "d": {k: v["d"] for k, v in d.items()}, "d_oficial": {k: v["d"] for k, v in d_oficial.items()},
                  "quintis": [(q["grupo"], q["pct_m"], q["mediana"], q["gap"]) for q in quintis],
                  "tipos": [(t["grupo"], t["pct_m"], t["gap"]) for t in tipos], "eixo": eixo_paga,
                  "stem": [(s["grupo"], s["pct_m"], s["gap"]) for s in stem]}, ensure_ascii=False, indent=1))
