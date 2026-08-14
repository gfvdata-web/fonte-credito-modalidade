# Dicionário de dados — `credito_modalidade`

> BCB · Crédito por modalidade (SGS). Etapa 1 do pipeline.
> Este arquivo documenta **apenas a fonte deste repositório**. A visão consolidada de todas
> as fontes do projeto vive no repositório `controle-global`.

- **Órgão:** Banco Central do Brasil (BCB) — Departamento de Estatísticas
- **API:** SGS (Sistema Gerenciador de Séries Temporais) — REST, sem chave
- **Endpoint (uma série por requisição):**
  ```
  https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=01/03/2011
  ```
  > O SGS **não tem consulta multi-série**: a Etapa 2 itera sobre os 61 códigos
  > registrados em `src/config.py` (`series`) e concatena as respostas.
  > Formatos: `json` (usado), `csv`. Parâmetros opcionais `dataInicial`/`dataFinal`
  > em `DD/MM/AAAA`; `/dados/ultimos/{n}` traz só as últimas observações.
- **Periodicidade:** mensal · **Histórico:** mar/2011 →
- **Licença:** Open Database License (ODbL) — BCB
- **Portal:** https://dadosabertos.bcb.gov.br/dataset/20539-saldo-da-carteira-de-credito---total
- **Metadados por série:** a API CKAN do portal resolve código → título/periodicidade:
  `https://dadosabertos.bcb.gov.br/api/3/action/package_search?q=codigo_sgs:"20539"`

## Geografia: nacional (⚪), verificado

O catálogo de candidatas marcava o recorte por UF como "a verificar". **Verificado: não
existe.** O SGS publica crédito por UF apenas para *porte de empresa* — "Saldo de crédito
pessoa jurídica por estado" (microempresa `25747+`, pequeno porte `25925+`) e "Saldo de
crédito por estado — MEI" (`27327+`) — que é um corte **diferente** do de modalidade e não
se cruza com ele. Por isso o tidy desta fonte **não tem coluna `uf`**, e o contrato genérico
do projeto segue intacto.

## Dicionário de dados (resposta do SGS)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `data` | string `DD/MM/AAAA` | Mês de referência (sempre dia 01) |
| `valor` | string decimal | Valor da série; a unidade depende do código consultado |

## Séries usadas

Três medidas, combinadas por segmento × modalidade (mapa completo em `src/config.py`):

| Medida | Unidade | Cobertura |
|--------|---------|-----------|
| `saldo` | R$ milhões | agregados + todas as modalidades |
| `taxa` | % ao ano | agregados + todas as modalidades |
| `spread` | p.p. ao ano | **só os agregados** — o BCB não publica spread por modalidade |

Agregados (linha `Total` de cada segmento):

| Segmento | saldo | taxa | spread |
|----------|-------|------|--------|
| Total | 20539 | 20714 | 20783 |
| Pessoas físicas (PF) | 20541 | 20716 | 20785 |
| Pessoas jurídicas (PJ) | 20540 | 20715 | 20784 |

Modalidades detalhadas: **10 em PF** (cheque especial, crédito pessoal consignado e não
consignado, aquisição de veículos, cartão rotativo e parcelado, desconto de cheques,
crédito rural, financiamento imobiliário, microcrédito) e **16 em PJ** (desconto de
duplicatas, capital de giro, conta garantida, cheque especial, aquisição de veículos,
vendor, compror, cartão rotativo e parcelado, ACC, financiamentos a importações e
exportações, repasse externo, crédito rural, financiamento imobiliário, BNDES).

> **Recorte temporal:** o saldo existe desde 2007 (e o total, desde 1988), mas juros e
> spread só a partir de **mar/2011** — o corte em `01/03/2011` alinha as três medidas.

> **Cobertura parcial, por desenho:** as modalidades detalhadas não esgotam o segmento
> (somam ~82% do saldo PF e ~70% do PJ). A Etapa 4 calcula o resíduo
> (`saldo do segmento − soma das modalidades`) e o dashboard o exibe como
> *"Outras modalidades"*, para que as fatias fechem com o saldo real do segmento.

> **Estabilidade da API:** o gateway do SGS às vezes responde HTTP 200 com uma página HTML
> de "Requisição inválida" quando recebe muitas chamadas em sequência. A Etapa 2 trata isso
> com pausa entre séries e retry com espera crescente.

## Formato tidy após a Etapa 3

| Coluna | Descrição |
|--------|-----------|
| `ano_mes` | `YYYY-MM` |
| `segmento` | `Total` / `PF` / `PJ` |
| `modalidade_credito` | `Total` (agregado do segmento) ou o nome da modalidade |
| `saldo` | R$ milhões |
| `taxa_juros_aa` | % ao ano |
| `spread_pp` | p.p. ao ano — preenchido só nas linhas `modalidade_credito = Total` |

Mesma anatomia do contrato tidy do projeto (dimensões em linha, medidas em coluna), com
`forma_pagamento` substituído pelo par `segmento` + `modalidade_credito`.
