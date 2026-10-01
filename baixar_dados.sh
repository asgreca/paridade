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

echo "pronto. Próximo passo: ./rodar_tudo.sh"
