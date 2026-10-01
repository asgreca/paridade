"""Testes das teses sobre o gap que a RAIS permite verificar (uso: python analise/teses.py ANO). Saída: resultados/teses_ANO.json.
1. Eixo pessoas x coisas; 2. caudas da distribuição e dispersão; 3. segregação por instrução e por renda regional
(análogo interno do 'paradoxo da igualdade'); 4. chegada à diretoria por idade."""
import json, sys, time
from pathlib import Path
import duckdb, numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
OUT = RESULTADOS / f"teses_{ANO}.json"
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:5.0f}s]", *a, flush=True)

# Eixo de interesses pela CBO (subgrupos principais e famílias)
PESSOAS = ["22", "23", "2515", "2516", "2524", "32", "33", "34", "4221", "5151", "5162", "5134", "5141"]
COISAS = ["21", "31", "6", "7", "8", "9"]
def eixo_sql():
    p = " or ".join(f"cbo like '{x}%'" for x in PESSOAS if not x.startswith("34"))
    c = " or ".join(f"cbo like '{x}%'" for x in COISAS)
    return f"case when {p} then 'Pessoas' when {c} then 'Coisas e sistemas' else 'Outras' end"

muns = json.loads((GEO / "municipios.json").read_text(encoding="utf-8"))
m2meso = {str(m["id"])[:6]: str(m["microrregiao"]["mesorregiao"]["id"]) for m in muns if m.get("microrregiao")}

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.register("mm", pd.DataFrame({"mun": list(m2meso), "meso": list(m2meso.values())}))
con.execute(f"""create view v as select p.*, mm.meso, {eixo_sql()} eixo from '{DADOS}/{ANO}/rais_*.parquet' p
  left join mm on mm.mun = p.mun where {FILTRO}""")

# 1. Eixo pessoas x coisas
eixo = con.execute("""select eixo, count(*) n, avg((sexo=2)::int)*100 pm, median(rem) mediana, avg(rem) media,
  avg(rem) filter (where sexo=2)/avg(rem) filter (where sexo=1)*100-100 gap_bruto from v group by 1""").df()
eixo_inst = con.execute("""select eixo, case when escolaridade>=9 then 'Superior' else 'Até médio' end inst,
  avg((sexo=2)::int)*100 pm, median(rem) mediana from v where eixo<>'Outras' group by 1,2""").df()
# gap na mesma ocupação dentro de cada eixo: células ocupação x instrução x idade x UF
gap_eixo = con.execute("""
with c as (select eixo, cbo, escolaridade, idade//10 fx, substr(mun,1,2) uf, sexo, count(*) n, avg(ln(rem)) lw from v group by all),
p as (select h.eixo, h.n nh, m.n nm, m.lw-h.lw d from c h join c m using (eixo, cbo, escolaridade, fx, uf) where h.sexo=1 and m.sexo=2)
select eixo, 100*(exp(sum(d*least(nh,nm))/sum(least(nh,nm)))-1) gap from p group by 1""").df().set_index("eixo").gap
eixo_out = [{"eixo": r.eixo, "n": int(r.n), "pct_m": round(r.pm, 1), "mediana": round(r.mediana), "media": round(r.media),
             "gap_bruto": round(r.gap_bruto, 1), "gap_mesma_ocupacao": round(float(gap_eixo[r.eixo]), 1)} for r in eixo.itertuples()]
eixo_inst_out = [{"eixo": r.eixo, "inst": r.inst, "pct_m": round(r.pm, 1), "mediana": round(r.mediana)} for r in eixo_inst.itertuples()]
log("eixo", eixo_out)

# 2. Caudas: participação feminina por fatia da distribuição e dispersão
q = con.execute("""select quantile_cont(rem, [0.5,0.9,0.99,0.999]) from v""").fetchone()[0]
caudas = []
for nome, lim in (("Todos", 0), ("Top 50%", q[0]), ("Top 10%", q[1]), ("Top 1%", q[2]), ("Top 0,1%", q[3])):
    pm = con.execute(f"select avg((sexo=2)::int)*100 from v where rem >= {lim}").fetchone()[0]
    caudas.append({"fatia": nome, "piso": round(lim), "pct_m": round(pm, 1)})
disp = con.execute("""select sexo, stddev_samp(ln(rem)) dp, quantile_cont(ln(rem),0.9)-quantile_cont(ln(rem),0.1) p90p10 from v group by 1""").df().set_index("sexo")
disp_dentro = con.execute("""
with c as (select cbo, sexo, var_samp(ln(rem)) vr, count(*) n from v group by 1,2 having count(*) >= 100),
p as (select h.cbo, h.vr vh, m.vr vm, least(h.n,m.n) w from c h join c m on h.cbo=m.cbo and h.sexo=1 and m.sexo=2)
select sum(w*vh)/sum(w) vh, sum(w*vm)/sum(w) vm, avg((vh>vm)::int)*100 pct_ocup_h_mais_disperso, count(*) n from p""").df().iloc[0]
caudas_out = {"fatias": caudas, "dp_h": round(float(disp.loc[1].dp), 3), "dp_m": round(float(disp.loc[2].dp), 3),
              "p90p10_h": round(float(disp.loc[1].p90p10), 3), "p90p10_m": round(float(disp.loc[2].p90p10), 3),
              "razao_var_dentro": round(float(disp_dentro.vh / disp_dentro.vm), 3),
              "pct_ocup_h_mais_disperso": round(float(disp_dentro.pct_ocup_h_mais_disperso), 1), "n_ocup": int(disp_dentro.n)}
# diretoria: dirigentes de empresa (CBO 121, 122, 123) por idade
dire = con.execute("""select case when idade<30 then '<30' when idade<35 then '30-34' when idade<40 then '35-39' when idade<45 then '40-44'
  when idade<50 then '45-49' when idade<55 then '50-54' else '55+' end fx, avg((sexo=2)::int)*100 pm, count(*) n
  from v where (cbo like '121%' or cbo like '122%' or cbo like '123%') group by 1 order by 1""").df()
caudas_out["diretoria_idade"] = [{"faixa": r.fx, "pct_m": round(r.pm, 1), "n": int(r.n)} for r in dire.itertuples()]
log("caudas", caudas_out)

# 3. Segregação (Duncan) por instrução e por renda média da mesorregião
def duncan(where):
    d = con.execute(f"select cbo, sexo, count(*) n from v where {where} group by 1,2").df().pivot(index="cbo", columns="sexo", values="n").fillna(0)
    return round(50 * float((d[1] / d[1].sum() - d[2] / d[2].sum()).abs().sum()), 1)
seg_inst = [{"inst": n, "duncan": duncan(w)} for n, w in (("Até fundamental", "escolaridade<=5"), ("Médio", "escolaridade between 6 and 8"),
                                                        ("Superior", "escolaridade=9"), ("Mestrado/doutorado", "escolaridade>=10"))]
mes = con.execute("select meso, avg(rem) renda, count(*) n from v where meso is not null group by 1 having count(*) >= 20000 order by meso").df()
mes["duncan"] = [duncan(f"meso='{m}'") for m in mes.meso]
mes["lr"] = np.log(mes.renda)
r = float(np.corrcoef(mes.lr, mes.duncan)[0, 1])
# IC por bootstrap
rng = np.random.default_rng(1); bs = []
for _ in range(2000):
    s = mes.sample(len(mes), replace=True, random_state=int(rng.integers(1e9)))
    bs.append(np.corrcoef(s.lr, s.duncan)[0, 1])
mes_s = mes.sort_values("renda"); mes_s["q"] = pd.qcut(mes_s.renda, 4, labels=["1º quartil (mais pobres)", "2º", "3º", "4º quartil (mais ricas)"])
seg_out = {"por_instrucao": seg_inst, "corr_renda_segregacao": round(r, 2), "corr_ic": [round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)],
           "n_mesos": int(len(mes)), "quartis": [{"q": str(k), "duncan": round(float(g.duncan.mean()), 1), "renda": round(float(g.renda.mean()))} for k, g in mes_s.groupby("q", observed=True)],
           "pontos": [{"r": round(x.renda), "d": x.duncan} for x in mes.itertuples()]}
log("segregacao", {k: v for k, v in seg_out.items() if k != "pontos"})

OUT.write_text(json.dumps({"ano": int(ANO), "eixo": eixo_out, "eixo_instrucao": eixo_inst_out, "caudas": caudas_out, "segregacao": seg_out},
                          ensure_ascii=False, indent=1, default=float), encoding="utf-8")
log("ok", OUT)
