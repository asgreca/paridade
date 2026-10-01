# Dados e fontes

Todas as fontes são públicas e abertas. **Nenhuma exige cadastro nem chave de API.** O script `baixar_dados.sh` baixa tudo.

## RAIS: Relação Anual de Informações Sociais

- **Quem publica:** Ministério do Trabalho e Emprego (MTE), Programa de Disseminação das Estatísticas do Trabalho (PDET).
- **Página oficial dos microdados:** <https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/microdados-rais-e-caged>
- **FTP:** `ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/<ANO>/`
- **Arquivos usados:** `RAIS_VINC_PUB_{NORTE,NORDESTE,CENTRO_OESTE,SUL,MG_ES_RJ,SP,NI}.7z` (vínculos), 2023, 2024 e 2025. NI = UF não identificada.
- **Layout e dicionário:** `ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/Layouts/vínculos/`
- **Tamanho:** cerca de 8 GB compactado por ano e 50 GB descompactado. O ETL não descompacta no disco.

### Colunas usadas

| Coluna original | Nome no parquet | Uso |
|---|---|---|
| Ind Vínculo Ativo 31/12 - Código | (filtro) | só vínculos ativos no fim do ano |
| Sexo - Código | `sexo` | 1 masculino, 2 feminino |
| Idade | `idade` | controle, faixas, coortes |
| Escolaridade Após 2005 - Código | `escolaridade` | 11 níveis (ver METODOLOGIA.md) |
| CBO 2002 Ocupação - Código | `cbo` | ocupação, 6 dígitos (efeito fixo) |
| CNAE 2.0 Subclasse - Código | `cnae` | atividade, 7 dígitos; usamos divisão (2) e classe (5) |
| Município - Código | `mun` | 6 dígitos (código IBGE sem o verificador) |
| Natureza Jurídica - Código | `natjur` | público (1000 a 1999), estatal, S.A., Ltda. etc. |
| Tamanho Estabelecimento - Código | `tam` | porte, 10 faixas |
| Tipo Vínculo - Código | `tipo_vinc` | lido, não filtrado |
| Raça Cor - Código | `raca` | só em `imprensa.py` |
| Qtd Hora Contr | `horas` | jornada semanal contratada |
| Vl Rem Média Nom | `rem` | **salário analisado**: remuneração média mensal nominal |
| Vl Rem Dezembro Nom | `rem_dez` | robustez |
| Tempo Emprego | `tempo` | meses no vínculo atual (tempo de casa) |
| Qtd Dias Afastamento | `dias_afast` | duração dos afastamentos |
| Causa Afastamento 1, 2, 3 - Código | `ca1`, `ca2`, `ca3` | 10 e 30 acidente; 50 licença-maternidade |
| Ind Trabalho Parcial - Código | `parcial` | descritivo |
| Ind Trabalho Intermitente - Código | `intermitente` | descritivo |

## CBO 2002: Classificação Brasileira de Ocupações

- **Quem publica:** MTE. Página: <https://cbo.mte.gov.br>
- **No repositório:** `dados_auxiliares/cbo_labels.json`, um mapa de código de 6 dígitos para o título oficial da ocupação. Serve só para rotular. Os prefixos usados para agrupar ocupações estão em [METODOLOGIA.md](METODOLOGIA.md#6-condições-do-posto).

## CNAE 2.0

- **Quem publica:** IBGE / Concla. Busca: <https://concla.ibge.gov.br/busca-online-cnae.html>
- Os nomes das divisões (2 dígitos) estão em `analise/porte.py`.

## IBGE: localidades e malhas

| Arquivo | Endpoint | Uso |
|---|---|---|
| `geo/municipios.json` | <https://servicodados.ibge.gov.br/api/v1/localidades/municipios> | município → microrregião → mesorregião → UF |
| `geo/mesos_nomes.json` | <https://servicodados.ibge.gov.br/api/v1/localidades/mesorregioes> | nomes das 137 mesorregiões |
| `geo/meso.json` | `api/v3/malhas/paises/BR?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=mesorregiao` | mapa de calor (site) |
| `geo/uf.json` | `api/v3/malhas/paises/BR?...&intrarregiao=UF` | contorno dos estados (site) |

Documentação: <https://servicodados.ibge.gov.br/api/docs/localidades> e <https://servicodados.ibge.gov.br/api/docs/malhas?versao=3>

## IBGE: SIDRA (Censo 2022, população e PIB)

API: <https://apisidra.ibge.gov.br>. Todas as consultas são no nível de município (`n6`).

| Arquivo | Tabela | Variáveis e recortes | Indicador derivado |
|---|---|---|---|
| `fecund.json` | [10078](https://sidra.ibge.gov.br/tabela/10078) | v13315 mulheres 12+, v13316 filhos tidos, v13317 filhos nos últimos 12 meses | filhos por mulher; nascimentos por mil mulheres |
| `forca_sexo.json` | [10299](https://sidra.ibge.gov.br/tabela/10299) | v1641 pessoas 14+, por sexo (c2) e condição na força de trabalho (c629) | participação feminina e masculina |
| `renda_sexo.json` | [10299](https://sidra.ibge.gov.br/tabela/10299) | v13502 rendimento médio dos ocupados, por sexo | renda feminina ÷ masculina (inclui informais) |
| `alfab.json` | [10091](https://sidra.ibge.gov.br/tabela/10091) | v2513 taxa de alfabetização 15+ | alfabetização |
| `pop.json` | [4714](https://sidra.ibge.gov.br/tabela/4714) | v93 população residente 2022 | população; denominador do PIB per capita |
| `pib.json` | [5938](https://sidra.ibge.gov.br/tabela/5938) | v37 PIB a preços correntes 2021 (mil R$) | PIB per capita |

As URLs completas, com todos os códigos de classificação, estão em `baixar_dados.sh`.

## IDHM: Atlas do Desenvolvimento Humano (PNUD, Ipea, FJP)

- **Série:** `ADH_IDHM` no Ipeadata, ano 2010 (último IDHM municipal do Atlas com base censitária).
- **Endpoint OData:** `http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_IDHM')`
- **Arquivo:** `geo/censo/idhm.json`

## Interesses vocacionais: O*NET, ESCO e tábuas de conversão

| Arquivo | Fonte | Uso |
|---|---|---|
| `geo/onet/career_interest_types.csv` | [O*NET 31.0](https://www.onetcenter.org/database.html), Departamento do Trabalho dos EUA, licença CC BY 4.0 | notas RIASEC (1 a 7) por ocupação americana |
| `geo/onet/esco_onet.csv` | [Correspondência ESCO-O*NET](https://esco.ec.europa.eu/en/about-esco/data-science-and-esco/crosswalk-between-esco-and-onet), Comissão Europeia e Departamento do Trabalho dos EUA, 2022 | ocupações O*NET -> ocupações ESCO |
| `geo/onet/esco_api/*.json` | [API da ESCO](https://esco.ec.europa.eu/en/use-esco/use-esco-services-api) | grupo ISCO-08 de cada ocupação ESCO |
| `geo/onet/cbo2002_ciuo88_mte.csv` | Tábua oficial CBO 2002 x CBO 94 x CIUO 88 do MTE, na cópia verificável do pacote [ocupacoesBR](https://github.com/moraespeixoto/ocupacoesBR) | CBO -> ISCO-88 |
| `geo/onet/isco8808_ganzeboom.sps` | Ganzeboom e Treiman, International Stratification and Mobility File | ISCO-88 -> ISCO-08 |
| `dados_auxiliares/cbo_isco08_manual.csv` | ligação manual deste projeto, com observação em cada linha | famílias que a tábua não cobre e correções de erros da tábua |
| `dados_auxiliares/cbo_riasec.csv` | gerado por `prepara_interesses.py` | CBO -> ISCO-08 -> notas RIASEC e eixos de Prediger |

Fórmulas dos eixos: manual técnico do [ACT Interest Inventory](https://www.act.org/content/dam/act/unsecured/documents/ACT-Interest-Inventory-Technical-Manual.pdf) (2023).

## O que não está no repositório

Os dados brutos (`brutos/`), os parquet (`dados/`) e as tabelas do IBGE (`geo/`) não são versionados. Juntos somam dezenas de GB, e qualquer pessoa pode baixá-los das fontes oficiais com `./baixar_dados.sh`. Os **resultados** (`resultados/*.json`) estão versionados. São exatamente os arquivos que o site lê.
