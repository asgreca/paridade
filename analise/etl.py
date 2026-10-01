"""Lê os 7z da RAIS (vínculos, qualquer ano) em streaming e grava parquet com os vínculos ativos em 31/12.
Uso: python analise/etl.py ANO [REGIAO...]  (lê <BRUTOS>/<ANO>/RAIS_VINC_PUB_<REGIAO>.7z; grava <DADOS>/<ANO>/rais_<REGIAO>.parquet)"""
import subprocess, sys, time, unicodedata
from pathlib import Path
import duckdb

ANO = sys.argv[1]
import sys as _s; _s.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BRUTOS, DADOS
SRC = BRUTOS / ANO
OUT = DADOS / ANO
OUT.mkdir(parents=True, exist_ok=True)
REGIOES = ["NORTE", "CENTRO_OESTE", "NORDESTE", "SUL", "MG_ES_RJ", "SP", "NI"]

SQL = """
copy (
select
  try_cast("Sexo - Código" as tinyint) sexo,
  try_cast("Idade" as smallint) idade,
  try_cast("Escolaridade Após 2005 - Código" as tinyint) escolaridade,
  lpad(trim(cast("CBO 2002 Ocupação - Código" as varchar)),6,'0') cbo,
  lpad(trim(cast("CNAE 2.0 Subclasse - Código" as varchar)),7,'0') cnae,
  trim(cast("Município - Código" as varchar)) mun,
  try_cast("Natureza Jurídica - Código" as smallint) natjur,
  try_cast("Tamanho Estabelecimento - Código" as tinyint) tam,
  try_cast("Tipo Vínculo - Código" as smallint) tipo_vinc,
  try_cast("Raça Cor - Código" as tinyint) raca,
  try_cast(replace(cast("Qtd Hora Contr" as varchar),',','.') as double) horas,
  try_cast(replace(cast("Vl Rem Média Nom" as varchar),',','.') as double) rem,
  try_cast(replace(cast("Vl Rem Dezembro Nom" as varchar),',','.') as double) rem_dez,
  try_cast(replace(cast("Tempo Emprego" as varchar),',','.') as double) tempo,
  try_cast("Qtd Dias Afastamento" as smallint) dias_afast,
  try_cast("Causa Afastamento 1 - Código" as smallint) ca1,
  try_cast("Causa Afastamento 2 - Código" as smallint) ca2,
  try_cast("Causa Afastamento 3 - Código" as smallint) ca3,
  try_cast("Ind Trabalho Parcial - Código" as tinyint) parcial,
  try_cast("Ind Trabalho Intermitente - Código" as tinyint) intermitente
from read_csv('/dev/stdin', header=true, delim=',', quote='"', encoding='latin-1', all_varchar=true)
where "Ind Vínculo Ativo 31/12 - Código" = '1'
) to '{out}' (format parquet, compression zstd)
"""

for reg in (sys.argv[2:] or REGIOES):
    out = OUT / f"rais_{reg}.parquet"
    if out.exists():
        print("já existe", out); continue
    t = time.time()
    arq = str(SRC / f"RAIS_VINC_PUB_{reg}.7z")
    # nomes reais do cabeçalho (2024+ trocou "Código" por "Codigo" em algumas colunas)
    cab = subprocess.run(f"7zz x -so '{arq}' 2>/dev/null | head -1", shell=True, capture_output=True).stdout.decode("latin-1").strip()
    tira = lambda x: unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    reais = {tira(c.strip('"')): c.strip('"') for c in cab.split(",")}
    sql = SQL
    for nome in set(__import__("re").findall(r'"([^"]+)"', SQL)):
        if nome not in reais.values() and tira(nome) in reais:
            sql = sql.replace(f'"{nome}"', f'"{reais[tira(nome)]}"')
    p = subprocess.Popen(["7zz", "x", "-so", arq], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    # duckdb lê o stdin do processo filho: roda num subprocess python para receber o pipe
    q = subprocess.run([sys.executable, "-c", f"import duckdb; c=duckdb.connect(); c.execute(\"set enable_progress_bar=false\"); c.execute({sql.format(out=str(out)+'.tmp')!r})"],
                       stdin=p.stdout)
    p.wait()
    if q.returncode == 0:
        Path(str(out) + ".tmp").rename(out)
    n = duckdb.sql(f"select count(*) from '{out}'").fetchone()[0] if out.exists() else "FALHOU"
    print(reg, n, round(time.time() - t), "s", flush=True)
