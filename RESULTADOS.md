# Resultados

Números de **2025**, salvo indicação. Os três anos estão nos JSONs de `resultados/`. Gap = quanto as mulheres ganham a menos (negativo) ou a mais (positivo) que os homens. IC = intervalo de confiança de 95%, com erro-padrão agrupado.

## 1. A diferença existe e é estável

| | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| Média simples | -10,8% | -11,0% | -11,0% |
| Mesma instrução | -19,8% | -19,9% | -19,1% |
| Mesma ocupação | -10,0% | -9,7% | -9,7% |
| Mesma ocupação e cidade | -8,3% | -8,1% | -8,1% |
| Idem, base completa | -8,37% | -8,18% | -8,00% |

Fonte: `dados_ANO.json` → `escada`; `completa_ANO.json`.

## 2. Comparando grupos idênticos

147.523 células de mesma ocupação, cidade, escolaridade e faixa de idade, com 26,5 milhões de vínculos (`cruzamentos.json` → `grupo`):

- gap médio de -8,9%;
- mulheres ganham menos em 74% das células, empatam (±2%) em 14% e ganham mais em 12%;
- **placebo**: homem × homem 0,0% e mulher × mulher 0,0%. O método não cria diferença onde ela não existe.

## 3. Horas, adicionais e risco explicam pouco

Decomposição única, com efeito fixo de ocupação (`combinado_2025.json` → `com_ocupacao`). Contribuições ao gap bruto de -9,5 p.p. (EP por bootstrap entre parênteses):

| Fator | p.p. |
|---|---:|
| Horas contratadas | -2,34 (0,39) |
| Tempo no emprego atual | +0,71 (0,72) |
| Experiência na carreira | -0,21 (0,35) |
| Periculosidade, insalubridade, confinamento, turno | +0,04 |
| Risco de acidente do posto | -0,12 (0,08) |
| Instrução | +5,29 (1,17) |
| Empregador | -0,62 (0,98) |
| Ocupação (demais diferenças) | -2,10 (2,34) |
| **Não explicado** | **-10,14 (0,62)** |

As mulheres trabalham menos horas contratadas (40,5 contra 42,1 por semana). Quase não estão em postos de periculosidade (0,8% contra 5,4% dos homens) nem de confinamento (0,06% contra 0,76%). Ainda assim, dentro da mesma ocupação, essas condições somam menos de 1 p.p. A instrução joga **a favor** delas.

## 4. Trabalho operacional e força física

`forca_2025.json`, `extra_2025.json`, `estat_2025.json` → `bracal`:

- Trabalho operacional (CBO 6 a 9) não paga prêmio: com o mesmo perfil, a diferença em relação às demais funções é de -0,5% (IC -6,5 a +5,8). Em valores brutos, ele paga menos.
- Esforço físico pesado: 16,9% de mulheres, gap de -12,8% na mesma ocupação. Operacional leve ou de precisão: 44,9% de mulheres, gap de -9,8%.
- Para homens, o trabalho pesado paga +10,8% sobre o leve (IC 3,9 a 18,2). É o teto do que a força física poderia explicar, cerca de 3 p.p. do gap.

## 5. Teto de vidro

Gap na mesma ocupação por quantil da distribuição de salários (RIF, `estat_2025.json` → `quantis`):

| p10 | p25 | p50 | p75 | p90 | p95 |
|---:|---:|---:|---:|---:|---:|
| -2,1% | -5,4% | -10,6% | -13,2% | -14,3% | -16,9% |

## 6. Carreira e maternidade

- Gap na mesma ocupação por idade: -4% aos 16-24 anos, cerca de -7% aos 25-29 e cerca de -11% depois dos 35 (`dados_2025.json` → `idade`).
- Pseudo-painel por geração (`cruzamentos.json` → `painel`): as coortes jovens (1995-99 e 2000-07) mostram o gap crescendo de 2023 a 2025 (-6,1% → -7,0% e -3,6% → -4,3%), justamente quando entram na idade de ter filhos. Coortes mais velhas ficam estáveis.

## 7. Porte e segmento

`porte_2025.json`:

- Setor privado, mesma ocupação: até 9 empregados -6,0%; 500 ou mais -11,7% (diferença de -2,7 p.p., EP 1,1). **Empresas grandes têm gap maior.**
- Natureza jurídica: empresário individual -4,3%, administração pública -7,4%, S.A. -10,3%, pessoa física empregadora -14,4%.
- Segmentos com maior gap (entre os com 200 mil+ vínculos): borracha e plástico -16,1%, máquinas elétricas -15,8%, químicos -15,5%. Menor gap: saúde -4,5%, seleção de mão de obra -4,9%, varejo -4,9%.

## 8. Território

`mapa_2025.json`: **nenhuma das 137 mesorregiões** tem mulheres ganhando mais na mesma ocupação. As regiões diferem (I² = 91%), mas em torno de -7,5%, com desvio de 2,8 p.p. Os indicadores do município (`cruzamentos.json` → `interacoes`) têm efeito pequeno, de no máximo 1,6 p.p. por desvio-padrão. Cidades maiores (+1,6 p.p.) e lugares onde a renda das mulheres no Censo é mais próxima da dos homens (+1,0 p.p.) têm gap menor. Onde nascem mais filhos, o gap é um pouco maior (-0,5 p.p.).

## 9. Números da imprensa

`imprensa.json`: o número do MTE (setor privado, 100+ empregados) é reproduzido como -20,2% em 2025. Na mesma ocupação e cidade ele cai para -8,3%. Manchetes que dizem "na mesma função as mulheres ganham 20% menos" exageram: o número de 20% é a média geral, não a mesma função.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `dados_ANO.json` | `meta`, `geral` (contagens e médias), `escada`, `decomposicao` (Oaxaca), `instrucao`, `idade`, `maternidade`, `risco`, `ocupacoes`, `horas` |
| `evolucao.json` | resumo por ano para os gráficos de comparação |
| `estat_ANO.json` | `escada` com IC, `quantis` (RIF), `correlacao` risco × gap, `risco_dentro`, `bracal`, `profissoes`, `robustez` |
| `extra_ANO.json` | `bracal_adverso`, `tempo_casa`, `experiencia`, `perfil_exp`, `perfil_tempo`, `retorno` |
| `forca_ANO.json` | `classes` (pesado, leve, outro operacional), `premio_pesado_sobre_leve`, `perigo` |
| `combinado_ANO.json` | `sem_ocupacao`, `com_ocupacao` (fatores em p.p. com EP), `medias` |
| `ocupacoes_ANO.json` | `pontos` (uma linha por ocupação com 1.000+ vínculos), `fluxos` (Sankey), `resumo` |
| `teses_ANO.json` | eixo pessoas x coisas, caudas, segregação (Duncan), diretoria por idade |
| `mapa_ANO.json` | `mesos`, `ufs`, `regioes`, testes `homog_*` |
| `porte_ANO.json` | `porte_privado`, `natureza`, `segmentos`, `grande_vs_menor` |
| `completa_ANO.json` | validação com a base completa |
| `cruzamentos.json` | `grupo` e placebo, `painel`, `interacoes`, `conjunto`, quartis, `licenca` |
| `imprensa.json` | por ano: números reproduzidos e ajustados |
