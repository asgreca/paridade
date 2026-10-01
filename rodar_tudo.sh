#!/usr/bin/env bash
# Executa o pipeline completo na ordem em que um passo depende do outro.
# Uso: ./rodar_tudo.sh [ANOS...]   (padrão: 2023 2024 2025; 2023 é sempre necessário, ver METODOLOGIA.md)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python}"
ANOS=(2023 2024 2025); [ $# -gt 0 ] && ANOS=("$@")

for a in "${ANOS[@]}"; do
  echo "== ETL $a =="; "$PY" analise/etl.py "$a"
done
for a in "${ANOS[@]}"; do
  for s in analise estatistica extra mapa teses ocupacoes combinado porte forca completa; do
    echo "== $s $a =="; "$PY" "analise/$s.py" "$a"
  done
done
# scripts que comparam os três anos de uma vez
echo "== imprensa (2023-2025) =="; "$PY" analise/imprensa.py
echo "== cruzamentos (2023-2025) =="; "$PY" analise/cruzamentos.py
echo "pronto: resultados em ${PARIDADE_RESULTADOS:-resultados}/"
