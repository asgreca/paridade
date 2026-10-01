# Paridade 1:1

Homens e mulheres ganham diferente fazendo o mesmo trabalho no Brasil? Este repositório traz todo o código em Python que responde a essa pergunta com os microdados da **RAIS 2023, 2024 e 2025**: 150,8 milhões de vínculos formais (cerca de 50 milhões por ano depois dos filtros). Os resultados estão publicados em **[paridade.greca.dev.br](https://paridade.greca.dev.br)**.

O site apresenta os números de forma direta. Aqui estão o caminho completo, as equações e as decisões de tratamento, para quem quiser conferir, criticar ou refazer.

## Resultado principal

Diferença de salário mensal das mulheres em relação aos homens (log-salário, convertido em %):

| Comparação | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| Média simples (todas as mulheres x todos os homens) | -10,8% | -11,0% | -11,0% |
| Mesma jornada | -9,3% | -9,7% | -9,3% |
| Mesma instrução | -19,8% | -19,9% | -19,1% |
| Mesma idade e tempo de casa | -19,8% | -19,7% | -18,9% |
| Mesmo tipo de empregador (porte, UF, setor, público) | -16,8% | -16,8% | -16,3% |
| Mesma ocupação (CBO 6 dígitos) | -10,0% | -9,7% | -9,7% |
| **Mesma ocupação e mesmo município** | **-8,3%** | **-8,1%** | **-8,1%** |
| Mesma ocupação e município, **base completa sem amostra** | -8,37% | -8,18% | -8,00% |

Em resumo: as mulheres estudam mais que os homens, por isso controlar a instrução *aumenta* a diferença. Quando se compara a mesma função na mesma cidade, sobra uma diferença estável de cerca de 8% nos três anos. Horas, adicionais (periculosidade, insalubridade, confinamento, turno), risco de acidente e esforço físico explicam juntos pouco mais de 1 ponto percentual. Os demais achados estão em [RESULTADOS.md](RESULTADOS.md).

## O que tem aqui

```
analise/            os 13 scripts de análise (um por tema, cada um com docstring explicando o que faz)
config.py           caminhos de entrada e saída (sobrescrevíveis por variável de ambiente)
dados_auxiliares/   rótulos oficiais da CBO 2002 (código -> nome da ocupação)
resultados/         os JSONs gerados, exatamente os que alimentam o site
baixar_dados.sh     baixa RAIS (FTP do MTE), malhas e localidades do IBGE, tabelas do SIDRA e IDHM (Ipeadata)
rodar_tudo.sh       executa o pipeline inteiro na ordem certa
extras/imagens.py   OPCIONAL: gera as fotos dos capítulos do site (OpenAI); único ponto que usa chave de API
.env.example        modelo de onde colocar a SUA chave (copie para .env, que nunca vai para o Git)
METODOLOGIA.md      filtros, amostragem, modelos, equações e testes de robustez
DADOS.md            fontes, links, variáveis usadas e dicionário de códigos
RESULTADOS.md       o que cada JSON contém e os principais números
```

| Script | Pergunta que responde | Saída |
|---|---|---|
| `etl.py` | Lê os .7z da RAIS em streaming e grava parquet só com os vínculos ativos em 31/12 | `dados/ANO/rais_*.parquet` |
| `analise.py` | Escada de controles, decomposição Oaxaca-Blinder, instrução, idade, maternidade, risco, horas | `dados_ANO.json`, `evolucao.json` |
| `estatistica.py` | Erros-padrão agrupados, regressão quantílica incondicional (RIF), correlação risco x gap, segregação, profissões, robustez | `estat_ANO.json` |
| `extra.py` | Trabalho operacional em condição adversa (periculosidade, insalubridade, confinamento, turno) e experiência | `extra_ANO.json` |
| `forca.py` | Esforço físico pesado x operacional leve: composição por sexo e gap | `forca_ANO.json` |
| `combinado.py` | Decomposição única: tempo de trabalho + condições do posto, com bootstrap | `combinado_ANO.json` |
| `ocupacoes.py` | Tabela por ocupação: % mulheres, eixo pessoas x coisas, gap na mesma função | `ocupacoes_ANO.json` |
| `teses.py` | Pessoas x coisas, caudas da distribuição, segregação, chegada à diretoria | `teses_ANO.json` |
| `mapa.py` | Gap por mesorregião, UF e região, com teste de homogeneidade (Cochran Q, I²) | `mapa_ANO.json` |
| `porte.py` | Gap por porte da empresa, natureza jurídica e segmento (CNAE) | `porte_ANO.json` |
| `cruzamentos.py` | Mesmo grupo + placebo, pseudo-painel por geração, interação com Censo 2022, PIB e IDHM | `cruzamentos.json` |
| `imprensa.py` | Reproduz números citados pela imprensa em 2025 e 2026 e mede quanto sobra com controles | `imprensa.json` |
| `completa.py` | Valida a regressão principal com **todos** os vínculos, sem amostra | `completa_ANO.json` |

## Como reproduzir

Requisitos: Python 3.11+, [`7zz`](https://www.7-zip.org/) (7-Zip 23+) no PATH, `curl`, cerca de 60 GB livres (os .7z somam ~25 GB; os parquet ~12 GB) e 16 GB de RAM.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./baixar_dados.sh          # RAIS 2023-2025 + IBGE + Ipeadata (demora: são ~25 GB)
./rodar_tudo.sh            # ETL + todas as análises; resultados em resultados/
```

Para rodar um script isolado: `python analise/mapa.py 2025`. Os scripts que usam taxa de acidente ou licença-maternidade leem sempre a RAIS 2023 (veja o motivo em [METODOLOGIA.md](METODOLOGIA.md#afastamentos-2024-e-2025)), então o ETL de 2023 é necessário mesmo para analisar outro ano.

Os caminhos ficam em `config.py` e podem apontar para outro disco:

```bash
PARIDADE_BRUTOS=/disco/rais_7z PARIDADE_DADOS=/disco/parquet python analise/etl.py 2025
```

| Variável | Padrão | Conteúdo |
|---|---|---|
| `PARIDADE_BRUTOS` | `brutos/` | .7z originais da RAIS, em subpastas por ano |
| `PARIDADE_DADOS` | `dados/` | parquet gerados pelo ETL |
| `PARIDADE_GEO` | `geo/` | malhas, municípios e tabelas do Censo |
| `PARIDADE_RESULTADOS` | `resultados/` | JSONs de saída |

Tempo aproximado num Mac mini M4 (16 GB): ETL ~10 min por ano; cada script de análise de 1 a 6 min por ano; `completa.py` ~15 min por ano.

### Determinismo

Não há sorteio aleatório na amostra: um vínculo entra quando `hash(cbo||mun||idade||rem||tempo) % 20 = 0` (função `hash` do DuckDB). Rodar de novo produz a mesma amostra e os mesmos números. Os bootstraps usam `numpy.random.default_rng` com semente fixa, sobre tabelas ordenadas. As somas paralelas do DuckDB podem variar na última casa decimal entre máquinas, e os ICs por bootstrap podem variar em ±0,02.

## Chave de API

A análise **não usa nenhuma chave**: RAIS, IBGE e Ipeadata são abertos. Só o script opcional `extras/imagens.py` (fotos de abertura do site) chama uma API paga. Para usá-lo:

```bash
cp .env.example .env      # edite e coloque OPENAI_API_KEY=sua-chave
python extras/imagens.py
```

O `.env` está no `.gitignore`. Nunca coloque a chave em código nem em commit.

## Limitações

- A RAIS cobre só o emprego **formal** (CLT, estatutários, temporários). Informais e autônomos ficam de fora.
- A RAIS não informa adicionais pagos (periculosidade, insalubridade). A condição é inferida pela ocupação e atividade do posto. Veja [METODOLOGIA.md](METODOLOGIA.md#condições-do-posto).
- O que sobra depois dos controles ("não explicado") não é prova de discriminação. É a diferença que as variáveis disponíveis não explicam. Podem pesar fatores que a RAIS não mede, como negociação, cargo dentro da mesma CBO, bônus e interrupções de carreira anteriores ao vínculo.
- O registro de afastamentos ficou incompleto a partir de 2024, por isso acidente e licença-maternidade usam 2023.

## Licença e citação

Código sob licença MIT. Dados públicos do Ministério do Trabalho e Emprego, IBGE e Ipeadata/PNUD.

Autor: **Aislan Greca**, [Greca Analytics](https://greca.dev.br).
