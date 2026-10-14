---
name: credito-modalidade-bcb
description: Analisa a série mensal oficial do Banco Central sobre crédito no Brasil por modalidade — saldo da carteira, taxa média de juros e spread de pessoas físicas e jurídicas (cheque especial, cartão rotativo e parcelado, consignado, financiamento imobiliário, veículos, capital de giro, crédito rural, BNDES, microcrédito etc.), de mar/2011 até o mês mais recente. Baixa o dado atualizado do SGS, corrige as armadilhas da fonte (unidades, spread só nos agregados, estoque contra fluxo, taxas que não se somam, valores nominais) e situa os resultados nos marcos históricos. Use sempre que o usuário perguntar sobre juros, taxa, spread, saldo, endividamento, participação ou crescimento do crédito por modalidade no Brasil; quiser gráficos, relatórios ou números sobre cartão de crédito, consignado, financiamento imobiliário ou capital de giro; ou citar o painel "Crédito por modalidade", mesmo sem mencionar o Banco Central.
---

# Crédito por modalidade no Brasil (BCB)

Esta skill acompanha o painel **Crédito por modalidade**
(https://creditomodalidade.gfvdata.com/). A fonte é o SGS (Sistema Gerenciador de Séries
Temporais) do Banco Central do Brasil, aberto e gratuito: 61 séries mensais de saldo, taxa
de juros e spread, por segmento (Total, PF, PJ) e por modalidade, de mar/2011 em diante.

A tabela parece simples, mas quase todo erro de análise vem de detalhes que ela não mostra
(unidades, o que é estoque e o que é fluxo, onde o spread não existe). O papel desta skill
é evitar esses erros e devolver ao usuário uma análise em que ele possa confiar.

## 1. Carregar os dados

Rode o script incluído. Ele busca as 61 séries no SGS, junta num formato longo e imprime um
resumo do último mês:

```bash
python scripts/carregar_dados.py            # grava credito_modalidade.csv
python scripts/carregar_dados.py --ipca     # + saldo_real deflacionado pelo IPCA
```

O script tenta a API do SGS e, se ela falhar, o CSV publicado no site do projeto. Leia o
resumo antes de analisar: ele já responde muitas perguntas simples.

**Se a rede estiver bloqueada** (comum em ambientes isolados), o script sai com código 2.
Nesse caso:
1. Se você tiver uma ferramenta de busca na web, tente abrir
   `https://creditomodalidade.gfvdata.com/dados/credito_modalidade.csv`
   e salvar o conteúdo num arquivo.
2. Se não der, peça ao usuário para baixar esse CSV pelo navegador e anexá-lo à conversa.
3. Depois rode `python scripts/carregar_dados.py --arquivo <caminho>`.

Não invente nem "lembre" números da série. Se não conseguir carregar os dados, diga isso ao
usuário. Números de memória ficam desatualizados em semanas.

### Colunas do arquivo gerado

| Coluna | Significado |
|---|---|
| `ano_mes` | `AAAA-MM` |
| `segmento` | `Total`, `PF` ou `PJ` |
| `modalidade_credito` | `Total` (agregado do segmento) ou o nome da modalidade |
| `saldo` | **R$ milhões**, posição da carteira no fim do mês (estoque), nominal |
| `taxa_juros_aa` | **% ao ano**, taxa média das operações contratadas no mês (fluxo) |
| `spread_pp` | **pontos percentuais ao ano**; só existe nas linhas `modalidade_credito = Total` |
| `saldo_real` | só com `--ipca`: R$ milhões a preços do último mês com IPCA |

São 29 combinações segmento × modalidade (3 agregados, 10 modalidades PF, 16 PJ).

## 2. As armadilhas (leia antes de calcular qualquer coisa)

1. **Spread só existe nos três agregados.** Para modalidades, `spread_pp` é nulo em todos os
   meses. Nulo aqui significa "não publicado", não zero: não preencha, não interpole, não
   calcule média. Análise de spread só vale para Total, PF e PJ.
2. **Saldo é estoque, taxa é fluxo.** O saldo é a posição no fim do mês; a taxa é o preço
   das operações novas do mês, não o custo da carteira existente. Nunca some saldos de meses
   diferentes (conta o mesmo empréstimo várias vezes) e não trate a taxa como o juro que o
   estoque paga.
3. **Taxas não se somam nem se tiram em média simples.** O rotativo cobra mais de 400% a.a.
   e o imobiliário perto de 11%. Para qualquer agregação de taxa, **pondere pelo saldo**:
   taxa do grupo = soma(taxa × saldo) / soma(saldo).
4. **As modalidades não fecham o segmento.** As detalhadas somam cerca de 82% do saldo PF e
   70% do PJ. O resto é "Outras modalidades" (`Total` do segmento menos a soma das
   modalidades). Para participação, use o saldo do `Total` do segmento como denominador.
5. **Valores nominais.** A série cobre 15 anos sem correção pela inflação. Para comparar
   saldo entre anos distantes, use `--ipca` e mostre o real ao lado do nominal. Taxa e
   spread já são percentuais e não precisam de deflação.
6. **A série começa em mar/2011.** O saldo existe desde antes, mas o corte alinha as três
   medidas. Não afirme nada sobre antes disso.
7. **Nacional.** Não há recorte por estado ou município nesta fonte.
8. **Meses recentes podem ser revisados.** Informe sempre o último mês usado.

Mais detalhes em `references/armadilhas.md`.

## 3. Como analisar

Escolha a medida certa para a pergunta. Saldo responde "quanto há de crédito" e "onde
cresceu"; taxa responde "quanto custa o dinheiro novo"; spread responde "quanto sobra
depois do custo de captação", e só no nível PF/PJ/Total. Quando a pergunta for "o crédito
ficou mais caro?", mostre a taxa **e** o peso das modalidades (saldo), porque a mistura de
modalidades muda a média sem que nenhum preço mude.

Receitas comuns (pandas):

```python
import pandas as pd
df = pd.read_csv("credito_modalidade.csv", parse_dates=["ano_mes"])
pf = df[(df["segmento"] == "PF") & (df["modalidade_credito"] != "Total")]

# Participação de cada modalidade no saldo do segmento (denominador = Total do segmento)
total_pf = df[(df["segmento"] == "PF") & (df["modalidade_credito"] == "Total")].set_index("ano_mes")["saldo"]
saldo = pf.pivot_table(index="ano_mes", columns="modalidade_credito", values="saldo")
part = saldo.div(total_pf, axis=0)          # o que falta para 100% é "Outras modalidades"

# CAGR com os meses reais entre as pontas (não assuma 12 meses por ano)
def cagr(serie):
    s = serie.dropna()
    anos = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1 / anos) - 1

# Variação da taxa em pontos percentuais (taxa já é %, então subtraia; não use pct_change)
taxa = pf.pivot_table(index="ano_mes", columns="modalidade_credito", values="taxa_juros_aa")
var_pp_12m = taxa.diff(12)

# Taxa média ponderada pelo saldo (nunca média simples)
def taxa_ponderada(g):
    return (g["taxa_juros_aa"] * g["saldo"]).sum() / g["saldo"].sum()
tx_pf = pf.groupby("ano_mes").apply(taxa_ponderada)

# Spread: só nas linhas Total de cada segmento
spread = df[df["modalidade_credito"] == "Total"].pivot_table(
    index="ano_mes", columns="segmento", values="spread_pp")

# Saldo deflacionado (rode o script com --ipca): use saldo_real para comparar anos distantes
real = pf.pivot_table(index="ano_mes", columns="modalidade_credito", values="saldo_real")
```

- **Taxa em p.p., saldo em %.** A variação de taxa se diz em pontos percentuais (de 39%
  para 41% são 2 p.p., não 5%). A variação de saldo se diz em %.
- **Rotativo muda a escala.** Com taxa acima de 400% a.a., ele domina qualquer eixo linear.
  Use escala logarítmica ou um gráfico próprio.
- **Para explicar mudanças**, consulte `references/eventos.md` (marcos catalogados com
  segmentos e modalidades afetados). Cite o evento só quando a data bater com o dado.
  Coincidência não prova causa: use "coincide com", não "foi causado por".
- `references/achados.md` traz leituras já feitas no projeto. Use como ponto de partida,
  mas **recalcule os números com o dado atual** antes de citá-los.

## 4. Gráficos

Use as cores do painel. Elas são atribuídas por posição (ranking de saldo no segmento
mostrado), não fixas por modalidade: as cinco maiores recebem as cores abaixo, na ordem, e
o restante vira "Outras modalidades" em cinza.

| Posição | Cor (claro) | Cor (escuro) |
|---|---|---|
| 1ª maior | `#2a78d6` | `#3987e5` |
| 2ª | `#eb6834` | `#d95926` |
| 3ª | `#1baf7a` | `#199e70` |
| 4ª | `#eda100` | `#c98500` |
| 5ª | `#4a3aa7` | `#9085e9` |
| Outras modalidades | `#97a09a` | `#6b736d` |

Destaques do painel: verde `#0d7a3e` (positivo) e vermelho `#b3261e` (negativo).

- Participação no saldo: área empilhada 100% **por segmento** (PF e PJ separados; empilhar
  26 modalidades de segmentos diferentes fica ilegível).
- Taxas com ordens de grandeza muito diferentes: escala logarítmica, ou barras horizontais.
- Spread: linhas só para Total, PF e PJ. Não plote spread por modalidade (sai vazio).
- Marque eventos relevantes como linhas verticais com rótulo curto.

## 5. Como entregar a resposta

- Comece pela resposta direta, em uma ou duas frases, com o número principal.
- Diga o período e o último mês usado ("dados até jun/2026").
- Diga a unidade (R$ milhões, % a.a., p.p.) e se o saldo é nominal ou corrigido pelo IPCA.
- Quando a pergunta tocar alguma das armadilhas, mencione-a numa linha, sem sermão.
- Termine com a fonte: *Fonte: Banco Central do Brasil — SGS, crédito por modalidade
  (dados abertos). Tratamento: painel Crédito por modalidade
  (https://creditomodalidade.gfvdata.com/).*
- Escreva no idioma do usuário (a fonte e os nomes das modalidades ficam em português).
