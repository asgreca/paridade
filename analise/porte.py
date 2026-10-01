"""Gap por porte do estabelecimento, natureza jurídica e segmento (divisão CNAE), bruto e na mesma ocupação.
Uso: python analise/porte.py ANO. Saída: resultados/porte_ANO.json."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
AMOSTRA = 20
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)
pct = lambda b: round(100 * (np.exp(b) - 1), 2)

PORTE = "case when tam<=3 then 'Até 9 empregados' when tam<=5 then '10 a 49' when tam=6 then '50 a 99' when tam=7 then '100 a 249' when tam=8 then '250 a 499' when tam=9 then '500 a 999' else '1.000 ou mais' end"
ORDEM_PORTE = ["Até 9 empregados", "10 a 49", "50 a 99", "100 a 249", "250 a 499", "500 a 999", "1.000 ou mais"]
NAT = """case when natjur between 1000 and 1999 then 'Administração pública'
  when natjur in (2011,2038,2020,2275) then 'Empresa estatal'
  when natjur=2046 then 'S.A. de capital aberto' when natjur=2054 then 'S.A. de capital fechado'
  when natjur=2062 then 'Sociedade limitada (Ltda.)'
  when natjur in (2135,2305,2313,2321,2330,2232,2240) then 'Empresário individual e sociedades simples'
  when natjur between 3000 and 3999 then 'Sem fins lucrativos' when natjur between 4000 and 4999 then 'Pessoa física empregadora'
  else 'Outras' end"""

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"""create view v as select *, substr(cnae,1,2) div, (natjur between 1000 and 1999)::int publico, {PORTE} porte, {NAT} nat
  from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}""")
cnae = {"01":"Agricultura e pecuária","02":"Produção florestal","03":"Pesca e aquicultura","05":"Extração de carvão","06":"Extração de petróleo e gás",
 "07":"Extração de minerais metálicos","08":"Extração de minerais não metálicos","09":"Apoio à extração mineral","10":"Fabricação de alimentos","11":"Fabricação de bebidas",
 "12":"Fabricação de fumo","13":"Têxteis","14":"Confecção de roupas","15":"Couro e calçados","16":"Madeira","17":"Papel e celulose","18":"Impressão e gravações",
 "19":"Derivados de petróleo e biocombustíveis","20":"Químicos","21":"Farmacêuticos","22":"Borracha e plástico","23":"Minerais não metálicos","24":"Metalurgia",
 "25":"Produtos de metal","26":"Equipamentos de informática e eletrônicos","27":"Máquinas e materiais elétricos","28":"Máquinas e equipamentos","29":"Veículos automotores",
 "30":"Outros equipamentos de transporte","31":"Móveis","32":"Produtos diversos","33":"Manutenção e reparação de máquinas","35":"Eletricidade e gás","36":"Água",
 "37":"Esgoto","38":"Coleta e tratamento de resíduos","39":"Descontaminação","41":"Construção de edifícios","42":"Obras de infraestrutura","43":"Serviços especializados de construção",
 "45":"Comércio de veículos","46":"Comércio atacadista","47":"Comércio varejista","49":"Transporte terrestre","50":"Transporte aquaviário","51":"Transporte aéreo",
 "52":"Armazenamento e apoio ao transporte","53":"Correio","55":"Alojamento","56":"Alimentação (bares e restaurantes)","58":"Edição","59":"Cinema, vídeo e música",
 "60":"Rádio e televisão","61":"Telecomunicações","62":"Tecnologia da informação","63":"Serviços de informação","64":"Serviços financeiros","65":"Seguros e previdência",
 "66":"Auxiliares financeiros","68":"Atividades imobiliárias","69":"Jurídicas e contabilidade","70":"Sedes de empresas e consultoria","71":"Arquitetura e engenharia",
 "72":"Pesquisa e desenvolvimento","73":"Publicidade","74":"Outras atividades profissionais","75":"Veterinária","77":"Aluguéis","78":"Seleção e locação de mão de obra",
 "79":"Agências de viagem","80":"Vigilância e segurança","81":"Serviços para edifícios","82":"Serviços de escritório","84":"Administração pública","85":"Educação",
 "86":"Saúde","87":"Assistência com alojamento","88":"Assistência social","90":"Artes e espetáculos","91":"Patrimônio cultural","92":"Loterias e apostas","93":"Esporte e lazer",
 "94":"Organizações associativas","95":"Reparação de equipamentos","96":"Serviços pessoais","97":"Serviços domésticos","99":"Organismos internacionais"}

df = con.execute(f"""select sexo, idade, escolaridade, tempo ten, horas h, tam, cbo, substr(mun,1,2) uf, div, publico, porte, nat, ln(rem) lw
  from v where hash(cbo||mun||idade||rem||tempo) % {AMOSTRA} = 0""").df()
df["f"] = (df.sexo == 2).astype(float); df["age2"] = df.idade.astype(float) ** 2 / 100
df["ten2"] = df.ten ** 2 / 100; df["lh"] = np.log(df.h)
log("amostra", len(df))

def design(d, cont, cats):
    X = [d[cont].astype(float)]
    for c in cats:
        X.append(pd.get_dummies(d[c], prefix=c, drop_first=True, dtype=float))
    return pd.concat(X, axis=1)

def ols(d, cont, cats):
    X = design(d, cont, cats); y = d.lw; g = d.cbo
    X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
    Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
    Ai = np.linalg.pinv(Xv.T @ Xv)
    S = pd.DataFrame(Xv * u[:, None]).groupby(g.values).sum().values
    G = S.shape[0]; V = Ai @ (S.T @ S) @ Ai * G / max(G - 1, 1)
    return float(b[0]), float(np.sqrt(V[0, 0]))

HC = ["f", "lh", "idade", "age2", "ten", "ten2"]
def grupo(sql_col, nome_col, d_filtro, cats, sql_where="true", minimo=300):
    brutos = con.execute(f"""select {sql_col} k, count(*) n, avg((sexo=2)::int)*100 pm,
      avg(rem) filter (where sexo=2) m, avg(rem) filter (where sexo=1) h from v where {sql_where} group by 1""").df().set_index("k")
    out = []
    for k, d in d_filtro.groupby(nome_col):
        if k not in brutos.index or d.f.sum() < minimo or (1 - d.f).sum() < minimo:
            continue
        c, se = ols(d, HC + ([] if d.publico.nunique() == 1 else ["publico"]), cats)
        b = brutos.loc[k]
        out.append({"grupo": k, "n": int(b.n), "pct_m": round(b.pm, 1), "media_m": round(b.m), "media_h": round(b.h),
                    "bruto": round(100 * (b.m / b.h - 1), 1), "gap": pct(c), "ic": [pct(c - 1.96 * se), pct(c + 1.96 * se)]})
    return out

priv = df[df.publico == 0]
porte_priv = grupo("porte", "porte", priv, ["escolaridade", "uf", "div"], "publico=0")
porte_priv = sorted(porte_priv, key=lambda x: ORDEM_PORTE.index(x["grupo"]))
log("porte", [(x["grupo"], x["bruto"], x["gap"]) for x in porte_priv])
natur = sorted(grupo("nat", "nat", df[df.nat != "Outras"], ["escolaridade", "tam", "uf", "div"]), key=lambda x: x["gap"], reverse=True)
log("natureza", [(x["grupo"], x["gap"]) for x in natur])
df["seg"] = df["div"]
seg = grupo("div", "seg", df, ["escolaridade", "tam", "uf"], minimo=500)
for x in seg:
    x["codigo"] = x["grupo"]; x["grupo"] = cnae.get(x["grupo"], x["grupo"])
seg = sorted(seg, key=lambda x: x["gap"], reverse=True)
log("segmentos", len(seg), [(x["grupo"], x["gap"]) for x in seg[:5]], [(x["grupo"], x["gap"]) for x in seg[-5:]])
# grande x pequena dentro do mesmo segmento: porte como interação (só privado)
priv = priv.assign(grande=(priv.tam >= 9).astype(float))
priv["f_grande"] = priv.f * priv.grande
X = design(priv, HC + ["grande", "f_grande"], ["escolaridade", "uf", "div"]); y = priv.lw; g = priv.cbo
X = X - X.groupby(g).transform("mean"); y = y - y.groupby(g).transform("mean")
Xv = X.values; b, *_ = np.linalg.lstsq(Xv, y.values, rcond=None); u = y.values - Xv @ b
Ai = np.linalg.pinv(Xv.T @ Xv); S = pd.DataFrame(Xv * u[:, None]).groupby(g.values).sum().values
V = Ai @ (S.T @ S) @ Ai * S.shape[0] / (S.shape[0] - 1)
i0, i1 = X.columns.get_loc("f"), X.columns.get_loc("f_grande")
interacao = {"gap_ate_499": pct(b[i0]), "gap_500_mais": pct(b[i0] + b[i1]), "diferenca_pp": round(100 * b[i1], 2), "ep_pp": round(100 * np.sqrt(V[i1, i1]), 2)}
log("interacao", interacao)
(RESULTADOS / f"porte_{ANO}.json").write_text(json.dumps({"ano": int(ANO), "porte_privado": porte_priv, "natureza": natur, "segmentos": seg,
    "grande_vs_menor": interacao, "amostra": int(len(df))}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok")
