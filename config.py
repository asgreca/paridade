"""Caminhos do projeto. Todos podem ser trocados por variável de ambiente, sem editar código.

    PARIDADE_BRUTOS      arquivos .7z da RAIS, em <BRUTOS>/<ANO>/RAIS_VINC_PUB_*.7z   (padrão: ./brutos)
    PARIDADE_DADOS       parquet gerado pelo etl, em <DADOS>/<ANO>/rais_*.parquet      (padrão: ./dados)
    PARIDADE_GEO         malhas/localidades IBGE e tabelas do Censo (<GEO>/censo)      (padrão: ./geo)
    PARIDADE_RESULTADOS  saída JSON de cada análise                                     (padrão: ./resultados)
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BRUTOS = Path(os.environ.get("PARIDADE_BRUTOS", RAIZ / "brutos"))
DADOS = Path(os.environ.get("PARIDADE_DADOS", RAIZ / "dados"))
GEO = Path(os.environ.get("PARIDADE_GEO", RAIZ / "geo"))
RESULTADOS = Path(os.environ.get("PARIDADE_RESULTADOS", RAIZ / "resultados"))
CBO_LABELS = RAIZ / "dados_auxiliares" / "cbo_labels.json"
RESULTADOS.mkdir(parents=True, exist_ok=True)
