"""Monta a tabela CBO 2002 -> ISCO-08 -> notas RIASEC (O*NET) -> eixos de Prediger.
Uso: python analise/prepara_interesses.py. Saída: dados_auxiliares/cbo_riasec.csv.

Cadeia de ligação, nesta ordem de prioridade para cada ocupação (CBO de 6 dígitos):
  1. manual      dados_auxiliares/cbo_isco08_manual.csv (ocupação de 6 dígitos ou família de 4), direto em ISCO-08.
                 Cobre as famílias que a tábua oficial do MTE não tem (ocupações criadas na CBO 2002).
  2. direto      tábua oficial do MTE CBO 2002 -> CIUO-88 (ISCO-88), ocupação exata.
  3. familia     ocupação fora da tábua, mas com irmãs da mesma família na tábua: código ISCO-88 mais comum na família.
  Nos níveis 2 e 3, ISCO-88 -> ISCO-08 pela ponte de Ganzeboom e Treiman (isco8808.sps).
ISCO-08 -> O*NET-SOC 2019 pela correspondência oficial ESCO-O*NET (ESCO e Departamento do Trabalho dos EUA, 2022):
  cada ocupação ESCO tem um grupo ISCO-08; a nota de um grupo ISCO-08 é a média das ocupações O*NET ligadas a ele.
  Grupo ISCO-08 sem ligação usa a média do subgrupo (3 dígitos) e, se preciso, do grupo de 2 dígitos.
Notas RIASEC: O*NET 31.0, escala Occupational Interests (OI, 1 a 7).
Eixos de Prediger, fórmulas do manual técnico do ACT Interest Inventory (2023):
  Pessoas/Coisas = 2R + I + C - 2S - A - E   (positivo = coisas)
  Dados/Ideias   = 1,73 (E + C - I - A)      (positivo = dados)"""
import csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))
from config import GEO, CBO_LABELS

ON = GEO / "onet"
AUX = AQUI / "dados_auxiliares"

# O*NET: notas RIASEC por ocupação
oi = defaultdict(dict)
for x in csv.DictReader(open(ON / "career_interest_types.csv", encoding="utf-8")):
    if x["Scale ID"] == "OI":
        oi[x["O*NET-SOC Code"]][x["Element Name"][0]] = float(x["Data Value"])
oi = {k: v for k, v in oi.items() if len(v) == 6}

# ESCO -> ISCO-08 (respostas da API da ESCO, uma por ocupação, em geo/onet/esco_api/)
esco_isco = {}
for f in (ON / "esco_api").glob("*.json"):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    g = [x.get("code") for x in ((d.get("_links") or {}).get("broaderIscoGroup") or [])]
    cod = (g[0] if g else (d.get("code") or "")[:4]) or ""
    if d.get("uri") and re.fullmatch(r"\d{4}", cod[:4]):
        esco_isco[d["uri"]] = cod[:4]

# ESCO-O*NET -> pares (ISCO-08, O*NET)
linhas = list(csv.reader(open(ON / "esco_onet.csv", encoding="utf-8-sig")))
h = [i for i, x in enumerate(linhas) if x and x[0] == "O*NET Id"][0]
pares = defaultdict(list)
for x in linhas[h + 1:]:
    uri = x[3]
    isco = esco_isco.get(uri) if "/occupation/" in uri else re.sub(r"\D", "", uri.rstrip("/").split("/")[-1])[:4]
    if isco and x[0] in oi:
        pares[isco].append(x[0])
LET = "RIASEC"
def media(onets):
    return {l: sum(oi[o][l] for o in onets) / len(onets) for l in LET}
isco_nota = {k: media(v) for k, v in pares.items()}
por_prefixo = lambda n: {p: media([o for k, v in pares.items() if k[:n] == p for o in v]) for p in {k[:n] for k in pares}}
isco3, isco2 = por_prefixo(3), por_prefixo(2)
def nota_isco(c):
    if c in isco_nota: return isco_nota[c], "isco4"
    if c[:3] in isco3: return isco3[c[:3]], "isco3"
    if c[:2] in isco2: return isco2[c[:2]], "isco2"
    return None, None

# ISCO-88 -> ISCO-08 (Ganzeboom e Treiman)
g8808 = {a.zfill(4): b.zfill(4) for a, b in re.findall(r"recode @isko \(\s*(\d+)\s*=\s*(\d+)(?:\.\d)?\s*\)",
                                                         open(ON / "isco8808_ganzeboom.sps", encoding="utf-8-sig").read())}
# CBO 2002 -> ISCO-88 (tábua oficial do MTE)
tab = {x["cbo2002"].replace("-", ""): x["ciuo88"].strip().zfill(4)
       for x in csv.DictReader(open(ON / "cbo2002_ciuo88_mte.csv", encoding="utf-8")) if x["ciuo88"].strip()}
fam = defaultdict(Counter)
for c, i in tab.items():
    fam[c[:4]][i] += 1
man = {x["codigo_cbo"]: x["isco08"] for x in csv.DictReader(open(AUX / "cbo_isco08_manual.csv", encoding="utf-8"))}

rot = json.loads(Path(CBO_LABELS).read_text(encoding="utf-8"))
saida, cont = [], Counter()
for cbo in sorted(rot):
    if cbo in man: isco, nivel = man[cbo], "manual"
    elif cbo[:4] in man: isco, nivel = man[cbo[:4]], "manual"
    elif cbo in tab: isco, nivel = g8808.get(tab[cbo]), "direto"
    elif cbo[:4] in fam: isco, nivel = g8808.get(fam[cbo[:4]].most_common(1)[0][0]), "familia"
    else: isco, nivel = None, "sem"
    n, fonte = nota_isco(isco) if isco else (None, None)
    if n is None:
        nivel = "sem"
    cont[nivel] += 1
    linha = {"cbo": cbo, "isco08": isco or "", "nivel": nivel, "nota_isco": fonte or ""}
    if n:
        linha.update({l: round(n[l], 3) for l in LET})
        linha["pessoas_coisas"] = round(2 * n["R"] + n["I"] + n["C"] - 2 * n["S"] - n["A"] - n["E"], 3)
        linha["dados_ideias"] = round(1.73 * (n["E"] + n["C"] - n["I"] - n["A"]), 3)
        linha["tipo"] = max(LET, key=lambda l: n[l])
    saida.append(linha)

cols = ["cbo", "isco08", "nivel", "nota_isco", *LET, "pessoas_coisas", "dados_ideias", "tipo"]
with open(AUX / "cbo_riasec.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(saida)
print(f"ESCO com ISCO: {len(esco_isco)} | grupos ISCO-08 com nota: {len(isco_nota)} | ocupações O*NET com nota: {len(oi)}")
print("ocupações CBO por nível:", dict(cont))
