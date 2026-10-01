# Metodologia

Este documento descreve como os números do Paridade 1:1 foram produzidos: base, filtros, amostra, modelos e testes. Cada seção indica o script e a função onde o cálculo está.

## 1. Base: RAIS vínculos

A Relação Anual de Informações Sociais é o registro administrativo que todo empregador formal entrega ao Ministério do Trabalho. Cada linha é um **vínculo**, ou seja, um contrato de trabalho num estabelecimento. Uma pessoa com dois empregos aparece duas vezes. Os microdados públicos não identificam pessoas nem empresas.

**ETL (`analise/etl.py`).** Os arquivos `RAIS_VINC_PUB_<REGIAO>.7z` (7 por ano) são descompactados em streaming (`7zz x -so`) e lidos pelo DuckDB direto do stdin (`read_csv('/dev/stdin', encoding='latin-1', all_varchar=true)`), sem gravar o CSV no disco (cada ano tem ~50 GB descompactado). Fica só quem tem `Ind Vínculo Ativo 31/12 = 1`. As colunas são convertidas com `try_cast`, e a vírgula decimal vira ponto. A saída é um parquet zstd por região.

Duas armadilhas do layout:

- A partir de 2024 alguns cabeçalhos trocaram "Código" por "Codigo". O ETL lê a primeira linha, normaliza os nomes (remove acentos e caixa) e reescreve a consulta com o nome real.
- CBO, CNAE e município podem vir com espaço à esquerda. Por isso todos passam por `trim` e `lpad`.

| Ano | Vínculos ativos em 31/12 | Após filtros | Mulheres |
|---|---:|---:|---:|
| 2023 | 55.818.007 | 48.870.760 | 45,1% |
| 2024 | 57.800.651 | 50.041.592 | 45,4% |
| 2025 | 60.691.770 | 51.842.214 | 46,1% |

O total após filtros nos três anos é de 150,8 milhões.

## 2. Filtros

Aplicados em todos os scripts (constante `FILTRO`):

```sql
horas between 10 and 48          -- jornada contratada semanal plausível
and rem >= 500                   -- remuneração média mensal nominal (exclui registros quase zerados)
and idade between 16 and 70
and sexo in (1,2)                -- 1 = masculino, 2 = feminino
and escolaridade between 1 and 11
```

A variável de salário é `Vl Rem Média Nom`, a remuneração média mensal nominal do ano. Ela inclui salário-base, adicionais, horas extras, comissões e gratificações habituais. Usamos sempre o **log** dessa remuneração (`lw = ln(rem)`), e os coeficientes são convertidos em diferença percentual por `100·(e^β − 1)`.

## 3. Amostra das regressões

As estatísticas descritivas (médias, medianas, contagens, taxas) usam a **base completa**. As regressões usam 1 em cada 20 vínculos (cerca de 2,5 milhões por ano), escolhidos de forma determinística:

```sql
where hash(cbo||mun||idade||rem||tempo) % 20 = 0
```

Com 2,5 milhões de observações o erro-padrão do gap principal fica em décimos de ponto percentual, e a matriz de dummies cabe na memória. O mapa (`mapa.py`) usa 1 em 5 para ter observações suficientes nas mesorregiões menores.

**A amostra não muda o resultado.** `completa.py` refaz a regressão principal com **todos** os vínculos. Como o efeito fixo de ocupação só envolve vínculos da mesma ocupação, a base é dividida em 24 lotes de ocupações inteiras (`hash(cbo) % 24`). Em cada lote a regressão é demeaned por ocupação (ou ocupação × município), e somamos X'X e X'y. A solução β = (Σ X'X)⁻¹ Σ X'y é exatamente a da base inteira.

| Ano | Mesma ocupação: amostra / completa | Mesma ocupação e cidade: amostra / completa |
|---|---|---|
| 2023 | -10,0% / -10,04% | -8,3% / -8,37% |
| 2024 | -9,7% / -9,74% | -8,1% / -8,18% |
| 2025 | -9,7% / -9,60% | -8,1% / -8,00% |

## 4. Modelo principal: escada de controles

`analise.py`, seção 4. Para cada degrau estimamos por MQO:

```
ln(rem_i) = α + δ·mulher_i + X_i'β + μ_g(i) + ε_i
```

δ é o gap ajustado. Os controles entram em degraus, para mostrar o que cada um faz com o gap:

| Degrau | Controles contínuos | Dummies | Efeito fixo μ |
|---|---|---|---|
| Comparação direta | nenhum | nenhuma | nenhum |
| Mesma jornada | ln(horas) | nenhuma | nenhum |
| Mesma instrução | ln(horas) | escolaridade (11 níveis) | nenhum |
| Mesma idade e tempo de casa | + idade, idade²/100, tempo de casa, tempo²/100 | escolaridade | nenhum |
| Mesmo tipo de empregador | + público | + porte (tam), UF, divisão CNAE (2 dígitos) | nenhum |
| Mesma ocupação | idem | idem | CBO 6 dígitos |
| Mesma ocupação, mesma cidade | idem | escolaridade, porte, divisão CNAE | CBO × município |

**Efeitos fixos por demeaning (within).** Com ~2.600 ocupações e ~200 mil células ocupação × município, não dá para criar dummies. Subtraímos de y e de cada coluna de X a média do grupo (`X - X.groupby(g).transform("mean")`) e rodamos MQO sem constante. Pelo teorema de Frisch-Waugh-Lovell, isso dá o mesmo β que as dummies.

**Erro-padrão (`estatistica.py`, `ols`).** É robusto e agrupado (cluster) por ocupação, ou por município nas regressões dentro de uma profissão:

```
V = (X'X)⁻¹ (Σ_g S_g S_g') (X'X)⁻¹ · G/(G−1),   S_g = Σ_{i∈g} x_i û_i
```

Assim os vínculos da mesma ocupação podem ter erros correlacionados. É a escolha conservadora: o IC fica mais largo que o de MQO puro.

**Por que a instrução aumenta o gap.** 36% das mulheres têm superior completo, contra 21% dos homens. Comparar pessoas com a mesma escolaridade tira a vantagem educacional delas, e o gap vai de -9% para -19%. A ocupação traz o gap de volta a -10%: parte da diferença está em mulheres com diploma em ocupações que pagam menos por diploma.

## 5. Decomposição Oaxaca-Blinder

**Versão do `analise.py` (seção 5).** É a versão pooled com dummy de sexo (Fortin, 2008; Jann, 2008). Primeiro estimamos β na amostra conjunta com efeito fixo de ocupação. Depois:

```
ȳ_M − ȳ_H = Σ_k (x̄_M,k − x̄_H,k)·β_k  +  (μ̄_M − μ̄_H)  +  δ
            └──── parte explicada ────┘  └ ocupação ┘   └ não explicada ┘
```

Os termos explicados são agrupados em horas, instrução, idade, tempo de casa e empregador. A parte da ocupação (diferença média dos efeitos fixos μ_cbo entre mulheres e homens) é **projetada** nas características da ocupação, numa regressão em nível de CBO ponderada por √n:

```
μ̂_cbo = γ0 + γ1·periculosidade + γ2·confinamento + γ3·turno + γ4·taxa_acidente + u
```

Daí saem quanto da segregação ocupacional se deve aos adicionais (periculosidade, confinamento, turno), quanto ao risco de acidente e quanto às demais diferenças entre ocupações.

**Versão do `combinado.py`.** É uma decomposição única com todas as explicações de "tempo e condição de trabalho" juntas:

- **horas:** ln(horas);
- **tempo de casa:** tempo e tempo²;
- **experiência potencial de Mincer:** exp = idade − anos de estudo − 6, com o mapa `ANOS_ESTUDO`;
- **condições do posto:** periculosidade, insalubridade, confinamento e turno, como dummies;
- **risco medido do posto:** taxa de acidente na célula CBO × classe CNAE (5 dígitos), na RAIS 2023, com ≥ 50 vínculos.

Ela roda sem e com efeito fixo de ocupação. O erro-padrão de cada contribuição vem de **bootstrap por ocupação**: 30 réplicas, sorteando ocupações inteiras com reposição (semente 7). Ocupações repetidas viram grupos distintos no efeito fixo.

## 6. Condições do posto

A RAIS **não informa** se o adicional de periculosidade ou insalubridade é pago. A condição é atribuída ao posto pela ocupação (CBO) e, em alguns casos, pela atividade (CNAE). Os prefixos foram conferidos nos rótulos oficiais da CBO 2002 (`dados_auxiliares/cbo_labels.json`):

| Condição | Critério |
|---|---|
| Periculosidade (NR-16) | CBO com prefixo 7321, 9511, 7156, 521135, 519110, 519115, 5173, 5172, 711120 (eletricistas de rede, frentistas, vigilantes, explosivos) |
| Insalubridade (NR-15) | CBO 8485, 5142, 7222, 7223, 821, 822, 7232, 7243, 7244, 723315, 632605, 622110; ou ocupação operacional (CBO 6 a 9) em abate de animais (CNAE 1011 a 1013) ou coleta e tratamento de resíduos (381, 382); ou faxineiro (514320) em saúde (CNAE 86) |
| Confinamento, embarcado, subsolo | CBO 7111, 7112, 7113, 3412, 3413, 7827, 3163, 862110 (mineração, marítimos, petróleo); ou ocupação operacional (CBO 7 a 9) na indústria extrativa (CNAE 05 a 09) |
| Turno irregular | CBO 5171, 3222, 2235, 7824, 7825, 8110, 8621, 8622 (vigias, enfermagem, motoristas, operadores de processo contínuo) |
| Risco alto medido | célula CBO × classe CNAE no top 20% dos vínculos operacionais por taxa de acidente (2023) |

O critério do confinamento começou só pela CNAE extrativa, mas isso captava pessoal de escritório das mineradoras. Por isso ficou restrito às ocupações de produção (CBO 7, 8, 9).

## 7. Afastamentos 2024 e 2025

Usamos as causas de afastamento da RAIS (até 3 por vínculo, `ca1` a `ca3`):

- **10 e 30**: acidente de trabalho típico e de trajeto. Taxa de acidente da ocupação = % de vínculos com ao menos um desses afastamentos no ano.
- **50**: licença-maternidade. Na RAIS 2023, 98% dos casos são mulheres e a mediana é de 120 dias, o que confirma o código.

**O registro de afastamentos ficou incompleto a partir de 2024**: todas as causas caem de 35% a 50% de um ano para o outro, sem nenhuma mudança real que explique isso. Os licenciamentos foram 620 mil em 2023, 333 mil em 2024 e 249 mil em 2025. Por isso **a taxa de acidente e a licença-maternidade vêm sempre da RAIS 2023**, inclusive quando o salário analisado é de 2024 ou 2025. Por esse motivo o ETL de 2023 é obrigatório.

## 8. Regressão quantílica incondicional (RIF)

`estatistica.py`, seção 2 (Firpo, Fortin e Lemieux, 2009). Para cada quantil τ ∈ {10, 25, 50, 75, 90, 95} calculamos a função de influência recentrada:

```
RIF(y; q_τ) = q_τ + (τ − 1{y ≤ q_τ}) / f_Y(q_τ)
```

A densidade f_Y(q_τ) é estimada por kernel gaussiano com banda de Silverman (1,06·σ·n^(−1/5)). Em seguida rodamos a mesma regressão com efeito fixo de ocupação, com RIF no lugar de ln(rem). O coeficiente de "mulher" é o efeito sobre o quantil **incondicional** da distribuição de salários. Ele mostra se a diferença está na base ou no topo (teto de vidro).

## 9. Mesmo grupo e placebo

`cruzamentos.py`, seção 1. Este teste não usa regressão.

1. Agrupamos os vínculos em **células** de ocupação (CBO 6 dígitos) × município × escolaridade × faixa de idade de 10 anos.
2. Ficam as células com ≥ 10 homens e ≥ 10 mulheres. Em 2025 são 147.523 células e 26,5 milhões de vínculos.
3. Em cada célula, d = média de ln(rem) das mulheres − média dos homens. O resumo é a média ponderada por min(n_H, n_M).

**Placebo.** Dentro de cada célula, os homens são divididos em duas metades por um hash (`hash(cbo||mun||idade||rem||tempo||horas) % 2`), e as metades são comparadas da mesma forma (exigindo ≥ 5 em cada metade). O mesmo é feito com as mulheres. Se o método criasse diferenças artificiais, o placebo também mostraria gap. Resultado em 2025: homem × homem 0,0% e mulher × mulher 0,0%, contra mulher × homem -8,9%. Em 74% das células as mulheres ganham mais de 2% a menos.

## 10. Maternidade e carreira

- **Perfil por idade (`analise.py`, seção 7).** Gap ajustado (mesma ocupação) em faixas de idade, com tempo de casa, presença em gestão e taxa de licença por faixa.
- **Pseudo-painel por geração (`cruzamentos.py`, 2a).** Os microdados não seguem pessoas. Por isso acompanhamos **coortes de nascimento** (1955-64 … 2000-07) de 2023 a 2025. Se a pausa da maternidade gerasse o gap, as coortes que entram na idade fértil deveriam ver o gap crescer nesses dois anos. O modelo omite idade, porque dentro da coorte ela é quase constante.
- **Fecundidade do município (2b).** Interação mulher × filhos por mulher do município (Censo 2022, padronizada).
- **Licença em 2023 (2c).** Percentual de mulheres de 20 a 39 anos com licença no ano.

## 11. Indicadores do município

`cruzamentos.py`, seção 3. O município do vínculo é cruzado com:

- **Censo 2022:** filhos por mulher, nascimentos nos 12 meses por mil mulheres, participação na força de trabalho por sexo, renda feminina/masculina e alfabetização;
- **PIB per capita 2021** e **população 2022**, ambos em log;
- **IDHM 2010**.

Cada indicador z, padronizado (média 0, DP 1), entra em interação com o sexo:

```
ln(rem) = δ·mulher + θ·(mulher × z_mun) + λ·z_mun + X'β + μ_cbo + ε
```

θ diz quanto o gap muda quando o indicador sobe 1 desvio-padrão. O EP é agrupado por município. Também rodamos um modelo com todos os indicadores juntos e quartis de fecundidade e de IDHM.

## 12. Heterogeneidade regional

`mapa.py`. Para cada uma das 137 mesorregiões com ≥ 300 vínculos de cada sexo na amostra 1/5, estimamos o gap com efeito fixo de ocupação e EP agrupado por ocupação. Testamos se os gaps são iguais entre regiões com a estatística de meta-análise:

```
Q = Σ w_r (b_r − b̄)²,   w_r = 1/se_r²,   I² = (Q − (k−1))/Q
τ² (DerSimonian-Laird) = max(0, (Q − (k−1)) / (Σw − Σw²/Σw))
```

Em 2025: Q = 1.550 (136 gl) e I² = 91%. As regiões diferem de verdade, mas τ = 2,8 p.p. em torno de uma média de -7,5%, e **nenhuma** das 137 mesorregiões tem mulheres ganhando mais na mesma ocupação. O mesmo teste é feito por UF e por grande região.

## 13. Segregação e composição

- **Índice de Duncan:** D = ½ Σ_cbo |h_cbo/H − m_cbo/M|, a fração de mulheres (ou homens) que precisaria trocar de ocupação para igualar as distribuições. É calculado no total, por escolaridade e por mesorregião (`teses.py`). A correlação com a renda da região tem IC por bootstrap de mesorregiões (2.000 réplicas).
- **Contrafactual de distribuição ocupacional (`estatistica.py`, seção 4):** salário médio que as mulheres teriam com a distribuição ocupacional dos homens, mantendo o salário feminino de cada ocupação.
- **Correlação risco × gap:** entre ocupações, ponderada por vínculos, com IC por bootstrap de ocupações (2.000 réplicas, semente 42). Pearson e Spearman.

## 14. Eixo pessoas x coisas

`ocupacoes.py` e `teses.py`. As ocupações são classificadas pelo prefixo da CBO:

- **Pessoas:** 22 (saúde), 23 (ensino), 2515 (psicólogos), 2516 (assistentes sociais), 2524 (RH), 32, 33, 34, 4221, 5151, 5162, 5134, 5141;
- **Coisas e sistemas:** 21 (ciências exatas e engenharia), 31 (técnicos de exatas), 6, 7, 8 e 9 (produção, agro, manutenção);
- **Outras:** o restante.

O gap dentro da ocupação é calculado por **pareamento exato** em células de ocupação × escolaridade × faixa de idade × UF, com média dos d ponderada por min(n_H, n_M). Ocupações com peso < 50 ficam como "sem comparação possível".

## 14b. Ocupações com maior presença feminina

`feminina.py`. Em cada ano, as 20 ocupações (CBO de 6 dígitos) com maior percentual de mulheres entre as que têm 50 mil vínculos ou mais. Para cada uma, com **todos** os vínculos da ocupação, estimamos

```
ln(rem) = α + δ·mulher + ln(horas), idade, idade², tempo de casa, tempo², público + dummies de instrução, porte, UF e divisão CNAE + ε
```

com erro-padrão agrupado por município. O resumo conta em quantas o IC de 95% fica abaixo de zero (homem ganha mais), cruza o zero (empate) ou fica acima (mulher ganha mais), e calcula a média de δ ponderada pelo número de vínculos.

## 15. Esforço físico

`forca.py`. "Esforço físico pesado" reúne pedreiros e serventes, carregadores, trabalhadores agrícolas braçais, mineiros, abate de animais e coleta de lixo (prefixos em `PESADO`). "Operacional leve ou de precisão" reúne embaladores, costureiras e montadores de precisão (`LEVE`). Medimos:

- a composição por sexo;
- o gap dentro de cada classe, com efeito fixo de ocupação;
- o prêmio do trabalho pesado sobre o leve para o mesmo sexo e perfil, sem efeito fixo de ocupação.

## 16. Porte e segmento

`porte.py`. Porte do estabelecimento (`tam`) em 7 faixas, só setor privado. Natureza jurídica em 8 grupos e divisão CNAE (2 dígitos). Cada grupo entra só com o mínimo de vínculos de cada sexo na amostra: 300 para porte e natureza jurídica, 500 para segmento. Também rodamos a interação mulher × (500+ empregados) num único modelo com efeito fixo de ocupação, para testar se a diferença entre grande e pequena empresa é estatisticamente significativa.

## 17. Números da imprensa

`imprensa.py` reproduz na RAIS números divulgados em 2025 e 2026:

- **Relatório de Transparência Salarial do MTE:** setor privado, estabelecimentos com 100+ empregados;
- **comparação com o Cempre do IBGE:** "homens ganham X% a mais";
- **superior completo, cargos de direção (CBO 1), mulheres negras × homens não negros, setores e estados.**

Depois aplicamos os controles para mostrar quanto do número divulgado é composição e quanto sobra na mesma ocupação e cidade.

## 18. Robustez

`estatistica.py`, seção 6. O gap com efeito fixo ocupação × município é reestimado por subgrupo:

- privado e público;
- só jornada de 40 a 44 h;
- até ensino médio e superior completo;
- até 29 anos e 40 anos ou mais;
- com salário **por hora** (rem / (horas × 4,348)) no lugar do mensal.

## Códigos usados

| Variável | Códigos |
|---|---|
| Escolaridade (após 2005) | 1 analfabeto, 2 até 5ª incompleto, 3 5ª completo, 4 6ª a 9ª, 5 fundamental completo, 6 médio incompleto, 7 médio completo, 8 superior incompleto, 9 superior completo, 10 mestrado, 11 doutorado |
| Tamanho do estabelecimento | 1 zero, 2 até 4, 3 de 5 a 9, 4 de 10 a 19, 5 de 20 a 49, 6 de 50 a 99, 7 de 100 a 249, 8 de 250 a 499, 9 de 500 a 999, 10 1.000 ou mais |
| Natureza jurídica | 1000 a 1999 = administração pública (variável `publico`) |
| Causa de afastamento | 10 e 30 acidente de trabalho (típico e trajeto), 50 licença-maternidade |
| Sexo | 1 masculino, 2 feminino |

## Referências

- Blinder, A. (1973). Wage discrimination: reduced form and structural estimates. *Journal of Human Resources*, 8(4).
- Oaxaca, R. (1973). Male-female wage differentials in urban labor markets. *International Economic Review*, 14(3).
- Fortin, N. (2008). The gender wage gap among young adults in the United States. *Journal of Human Resources*, 43(4).
- Firpo, S., Fortin, N. e Lemieux, T. (2009). Unconditional quantile regressions. *Econometrica*, 77(3).
- Duncan, O. D. e Duncan, B. (1955). A methodological analysis of segregation indexes. *American Sociological Review*, 20(2).
- DerSimonian, R. e Laird, N. (1986). Meta-analysis in clinical trials. *Controlled Clinical Trials*, 7(3).
- Cameron, A. C. e Miller, D. (2015). A practitioner's guide to cluster-robust inference. *Journal of Human Resources*, 50(2).
- Machado, C. e Pinho Neto, V. (2016). *The labor market consequences of maternity leave policies: evidence from Brazil*. FGV EPGE. [hdl.handle.net/10438/17859](https://hdl.handle.net/10438/17859)
