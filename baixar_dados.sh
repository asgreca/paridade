#!/usr/bin/env bash
# Baixa tudo o que a análise usa. Nenhuma fonte exige chave de API.
#   RAIS (vínculos) 2023, 2024, 2025 ......... FTP do Ministério do Trabalho e Emprego (~25 GB)
#   Municípios, mesorregiões e malhas ......... API de localidades e malhas do IBGE
#   Censo 2022, população e PIB municipal ..... API do SIDRA (IBGE)
#   IDHM 2010 ................................. API OData do Ipeadata (série ADH_IDHM, Atlas PNUD)
# Uso: ./baixar_dados.sh [ANOS...]   (padrão: 2023 2024 2025)
set -euo pipefail
cd "$(dirname "$0")"
BRUTOS="${PARIDADE_BRUTOS:-brutos}"; GEO="${PARIDADE_GEO:-geo}"
ANOS=(2023 2024 2025); [ $# -gt 0 ] && ANOS=("$@")
REGIOES=(NORTE NORDESTE CENTRO_OESTE SUL MG_ES_RJ SP NI)

echo "== RAIS =="
for a in "${ANOS[@]}"; do
  mkdir -p "$BRUTOS/$a"
  for r in "${REGIOES[@]}"; do
    f="$BRUTOS/$a/RAIS_VINC_PUB_$r.7z"
    [ -s "$f" ] && { echo "já existe $f"; continue; }
    echo "baixando $a $r"
    curl -fL --retry 5 --retry-delay 10 -C - -o "$f.part" "ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/$a/RAIS_VINC_PUB_$r.7z" \
      && mv "$f.part" "$f" || echo "AVISO: não baixou $a $r (confira o nome no FTP)"
  done
done

echo "== IBGE: localidades e malhas =="
mkdir -p "$GEO/censo"
IBGE=https://servicodados.ibge.gov.br/api
curl -fsS "$IBGE/v1/localidades/municipios" -o "$GEO/municipios.json"
curl -fsS "$IBGE/v1/localidades/mesorregioes" -o "$GEO/mesos_nomes.json"
curl -fsS "$IBGE/v3/malhas/paises/BR?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=mesorregiao" -o "$GEO/meso.json"
curl -fsS "$IBGE/v3/malhas/paises/BR?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=UF" -o "$GEO/uf.json"

echo "== IBGE: SIDRA (nível municipal, n6) =="
SIDRA=https://apisidra.ibge.gov.br/values
# 10078: mulheres de 12+ anos, filhos tidos e nascidos nos últimos 12 meses (Censo 2022)
curl -fsS "$SIDRA/t/10078/n6/all/v/13315,13316,13317/p/2022/c12232/58896/c1568/120704/c12293/58898" -o "$GEO/censo/fecund.json"
# 10299: pessoas de 14+ por sexo e condição na força de trabalho (Censo 2022)
curl -fsS "$SIDRA/t/10299/n6/all/v/1641/p/2022/c2/4,5/c629/32385,32386,32387/c58/95253" -o "$GEO/censo/forca_sexo.json"
# 10299: rendimento médio mensal dos ocupados por sexo (Censo 2022)
curl -fsS "$SIDRA/t/10299/n6/all/v/13502/p/2022/c2/4,5/c629/32387/c58/95253" -o "$GEO/censo/renda_sexo.json"
# 10091: taxa de alfabetização 15+ (Censo 2022)
curl -fsS "$SIDRA/t/10091/n6/all/v/2513/p/2022/c2/6794/c58/95253/c2661/32776/c1/6795" -o "$GEO/censo/alfab.json"
# 4714: população residente (Censo 2022)
curl -fsS "$SIDRA/t/4714/n6/all/v/93/p/2022" -o "$GEO/censo/pop.json"
# 5938: PIB a preços correntes, mil R$ (2021)
curl -fsS "$SIDRA/t/5938/n6/all/v/37/p/2021" -o "$GEO/censo/pib.json"

echo "== Ipeadata: IDHM (Atlas do Desenvolvimento Humano, PNUD) =="
curl -fsS "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_IDHM')" -o "$GEO/censo/idhm.json"

echo "== Interesses vocacionais: O*NET, ESCO e tábuas de conversão =="
ON="$GEO/onet"; mkdir -p "$ON/esco_api"
# O*NET 31.0 (Departamento do Trabalho dos EUA, licença CC BY 4.0): notas RIASEC por ocupação
curl -fsSL -A "Mozilla/5.0" "https://www.onetcenter.org/dl_files/database/db_31_0_csv/career_interest_types.csv" -o "$ON/career_interest_types.csv"
# Correspondência oficial ESCO-O*NET (Comissão Europeia e Departamento do Trabalho dos EUA, 2022)
curl -fsSL -A "Mozilla/5.0" "https://esco.ec.europa.eu/system/files/2023-08/ONET_(Occupations)_0_updated.csv" -o "$ON/esco_onet.csv"
# Grupo ISCO-08 de cada ocupação ESCO, pela API pública da ESCO (uma consulta por ocupação; leva alguns minutos)
python3 - "$ON" <<'PY'
import csv, sys
on = sys.argv[1]
r = list(csv.reader(open(f"{on}/esco_onet.csv", encoding="utf-8-sig"))); h = [i for i, x in enumerate(r) if x and x[0] == "O*NET Id"][0]
open(f"{on}/uris.txt", "w").write("\n".join(sorted({x[3] for x in r[h + 1:] if "/occupation/" in x[3]})))
PY
xargs -n1 -P8 sh -c 'f="'"$ON"'/esco_api/$(basename "$0").json"; [ -s "$f" ] || curl -s --retry 3 --max-time 40 -o "$f" "https://ec.europa.eu/esco/api/resource/occupation?uri=$0&language=en"' < "$ON/uris.txt"
# Tábua oficial CBO 2002 x CBO 94 x CIUO 88 (MTE), na cópia verificável do pacote ocupacoesBR,
# raspada família a família de mtecbo.gov.br/cbosite/pages/tabua/FiltroConversao_CBO2002_CBO94_CIUO88.jsf
curl -fsSL "https://raw.githubusercontent.com/moraespeixoto/ocupacoesBR/main/inst/extdata/fontes/tabua_oficial.csv" -o "$ON/cbo2002_ciuo88_mte.csv"
# Ponte ISCO-88 -> ISCO-08 de Ganzeboom e Treiman (International Stratification and Mobility File)
curl -fsSL "https://raw.githubusercontent.com/moraespeixoto/ocupacoesBR/main/inst/extdata/fontes/ganzeboom/isco8808.sps" -o "$ON/isco8808_ganzeboom.sps"

echo "pronto. Próximo passo: ./rodar_tudo.sh"
