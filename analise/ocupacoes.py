"""Tabela por ocupação: composição de gênero, eixo pessoas x coisas, mediana e gap na mesma função.
Uso: python analise/ocupacoes.py ANO. Saída: resultados/ocupacoes_ANO.json (pontos + fluxos para o Sankey)."""
import json, sys
from pathlib import Path
import duckdb, numpy as np

AQUI = Path(__file__).resolve().parent.parent
import sys as _sys; _sys.path.insert(0, str(AQUI))
from config import BRUTOS, DADOS, GEO, RESULTADOS, CBO_LABELS
ANO = sys.argv[1]
LABELS = CBO_LABELS
FILTRO = "horas between 10 and 48 and rem >= 500 and idade between 16 and 70 and sexo in (1,2) and escolaridade between 1 and 11"
rot = json.loads(Path(LABELS).read_text(encoding="utf-8"))
sys.path.insert(0, str(AQUI))
PESSOAS = ["22", "23", "2515", "2516", "2524", "32", "33", "4221", "5151", "5162", "5134", "5141"]
COISAS = ["21", "31", "6", "7", "8", "9"]
eixo = ("case when " + " or ".join(f"cbo like '{x}%'" for x in PESSOAS) + " then 'Pessoas' when "
        + " or ".join(f"cbo like '{x}%'" for x in COISAS) + " then 'Coisas e sistemas' else 'Outras' end")

con = duckdb.connect(); con.execute("set enable_progress_bar=false")
con.execute(f"create view v as select * from '{DADOS}/{ANO}/rais_*.parquet' where {FILTRO}")
d = con.execute(f"""
with c as (select cbo, escolaridade, idade//10 fx, substr(mun,1,2) uf, sexo, count(*) n, avg(ln(rem)) lw from v group by all),
p as (select h.cbo, h.n nh, m.n nm, m.lw-h.lw d from c h join c m using (cbo, escolaridade, fx, uf) where h.sexo=1 and m.sexo=2),
g as (select cbo, 100*(exp(sum(d*least(nh,nm))/sum(least(nh,nm)))-1) gap, sum(least(nh,nm)) w from p group by 1)
select t.cbo, any_value({eixo}) eixo, count(*) n, avg((sexo=2)::int)*100 pm, median(rem) med, any_value(g.gap) gap, any_value(g.w) w
from v t left join g using (cbo) group by t.cbo having count(*) >= 1000 order by t.cbo""").df()
d["comp"] = np.where(d.pm >= 70, "Predominantemente feminina", np.where(d.pm <= 30, "Predominantemente masculina", "Mista"))
d["quem"] = np.where(d.w.fillna(0) < 50, "Sem comparação possível",
             np.where(d.gap > 2, "Mulher ganha mais", np.where(d.gap < -2, "Homem ganha mais", "Empate (±2%)")))
pontos = [{"o": rot.get(r.cbo, r.cbo), "c": r.cbo, "e": r.eixo, "n": int(r.n), "pm": round(r.pm, 1), "med": round(r.med),
           "gap": None if np.isnan(r.gap) or r.w < 50 else round(r.gap, 1), "comp": r.comp} for r in d.itertuples()]
f1 = d.groupby(["eixo", "comp"]).n.sum().reset_index()
f2 = d.groupby(["comp", "quem"]).n.sum().reset_index()
fluxos = [{"de": r.eixo, "para": r.comp, "n": int(r.n)} for r in f1.itertuples()] + \
         [{"de": r.comp, "para": r.quem, "n": int(r.n)} for r in f2.itertuples()]
resumo = d.groupby("comp").apply(lambda g: {"ocupacoes": int(len(g)), "vinculos": int(g.n.sum()),
          "mediana_pond": round(float(np.average(g.med, weights=g.n))),
          "gap_medio": round(float(np.average(g.gap.dropna(), weights=g.w[g.gap.notna()])), 1)}, include_groups=False).to_dict()
Path(RESULTADOS / f"ocupacoes_{ANO}.json").write_text(json.dumps({"ano": int(ANO), "pontos": pontos, "fluxos": fluxos, "resumo": resumo},
                                                                      ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
print(len(pontos), resumo)
