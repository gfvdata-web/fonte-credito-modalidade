# Prompt — Nova página exploratória: Crédito por modalidade (BCB)

> **Como usar:** cole este arquivo inteiro como prompt em uma sessão nova do Claude Code
> (modelo **Opus**), rodando na raiz do repo `DadosFinanceirosBancoCentral`. É independente
> do prompt da fonte 8 — rode em outra sessão/janela, em paralelo se quiser.

---

## Contexto (leia antes de agir)

Este é o projeto **Dados Financeiros Abertos (BCB)**. A fonte da verdade sobre organização,
pastas e etapas é **`CONTEXTO.md`** na raiz — **leia só as seções abaixo, não o arquivo
inteiro** (as demais seções tratam de outras fontes e não são relevantes para esta sessão):
- Seção 5 (estrutura de pastas) e Seção 6 (Etapas 0 a 7).
- Seção 7 (contrato tidy entre etapas: `ano_mes`, `forma_pagamento`, `quantidade`, `valor`).
- Seção 9 (convenções: slug, nomes de arquivo por fonte).

Da mesma forma, em `catalogo/fontes.md` leia apenas a seção `meios_pagamento_mensal` (fonte
de referência) — não precisa ler o catálogo inteiro nem `catalogo/fontes-candidatas.md` além
do item A6 já indicado abaixo.

Já existe uma fonte implementada de ponta a ponta (`meios_pagamento_mensal`) — use-a como
**modelo de referência** para código, nomenclatura e estilo (veja `src/config.py`,
`src/coleta/meios_pagamento.py`, `src/tratamento/`, `src/analise/`, `src/publicacao/`,
`run_pipeline.py` e `docs/index.html` + `docs/js/app.js`).

O levantamento de fontes candidatas está em `catalogo/fontes-candidatas.md`, item **A6 —
"Crédito — operações, juros e spread por modalidade"** (BCB). Leia essa seção: geo está
marcada como 🟡 **UF (a verificar)** — parte do seu trabalho nesta sessão é confirmar isso.

## Objetivo desta sessão

Criar uma **nova página exploratória** (não mexer em `docs/index.html`) dedicada a
**Crédito por modalidade**, seguindo o pipeline completo (Etapas 1→7), com o mesmo padrão
de qualidade da fonte inicial.

- **Slug da fonte:** `credito_modalidade`
- **Tema:** saldo de crédito, taxa média de juros e spread, por **modalidade** (consignado,
  veículos, imobiliário, cartão, cheque especial etc.), por Pessoa Física e Pessoa Jurídica.
- **Nova página do dashboard:** `docs/credito-modalidade.html` (link cruzado com `index.html`).

## Passo a passo

### Etapa 1 — Confirmar a fonte e documentar
- No portal de dados abertos do BCB (`https://dadosabertos.bcb.gov.br/`) e na API SGS
  (`https://api.bcb.gov.br/dados/serie/...`), **identifique os códigos de série exatos**
  para: saldo de crédito por modalidade, taxa média de juros PF/PJ e spread. O catálogo
  cita como ponto de partida os códigos 20539+ (saldo), 20740/25471 (juros) — **confirme
  os códigos corretos e atualizados**, pois a numeração do SGS é por série individual.
- Confirme também se existe recorte **por UF** para essas séries (o catálogo marca isso
  como "a verificar") ou se é dado só nacional. Isso decide se o contrato tidy precisa da
  coluna `uf` (ver Etapa 3).
- Registre a fonte confirmada em `catalogo/fontes.md` (mesmo formato usado para a fonte
  inicial: URL, parâmetros, colunas, unidades, periodicidade, licença).

### Etapa 2 — Coleta (`src/coleta/credito_modalidade.py`)
- Adicione a entrada `credito_modalidade` em `FONTES` (`src/config.py`), com URL(s) da API
  SGS por série (uma chamada por código de série; a API SGS não faz "multi-série" nativo,
  então o coletor provavelmente itera sobre uma lista de séries e as junta).
- Salve o bruto em `dados/brutos/credito_modalidade.json`, seguindo o mesmo envelope
  (`fonte`, `url`, `coletado_em`, `total_registros`, `registros`) do coletor de referência.

### Etapa 3 — Tratamento (`src/tratamento/credito_modalidade.py`)
- Gere `dados/processados/credito_modalidade.csv` em formato tidy/long.
- **Se confirmar dado só nacional:** reaproveite o contrato existente, trocando
  `forma_pagamento` por `modalidade_credito` (ou equivalente) — combine com o time da
  Etapa 1 para não quebrar o contrato genérico descrito na seção 7 do `CONTEXTO.md`.
- **Se confirmar recorte por UF:** estenda o contrato com a coluna `uf`, do jeito descrito
  no roadmap do catálogo (`catalogo/fontes-candidatas.md`, seção "Observações de
  integração") — sem quebrar a fonte `meios_pagamento_mensal`, que não tem essa coluna.
- Trate: taxa de juros como % (numérico), saldo/valor em R$, datas em `YYYY-MM`.

### Etapa 4 — Análise (`src/analise/credito_modalidade.py`)
- Métricas mínimas: evolução do saldo por modalidade, participação (%) de cada modalidade
  no saldo total, variação da taxa de juros/spread ao longo do tempo, ranking de
  modalidades por custo (taxa) e por volume (saldo).

### Etapa 5 — Publicação (`src/publicacao/credito_modalidade.py`)
- Gere `docs/dados/credito_modalidade.json` com bloco `meta` (fonte, url, gerado_em,
  unidades, período) — igual ao padrão da fonte inicial.

### Etapa 6 — Dashboard (`docs/credito-modalidade.html`)
- Nova página HTML (reaproveite `docs/css/estilo.css`; crie `docs/js/credito-modalidade.js`
  se o JS for específico, ou estenda `app.js` com funções isoladas por página).
- KPIs sugeridos: saldo total de crédito, taxa média ponderada, modalidade com maior saldo,
  modalidade mais cara (maior taxa).
- Gráficos sugeridos (Chart.js): evolução do saldo por modalidade (linhas), participação
  por modalidade (pizza/rosca), comparação de taxas por modalidade (barras).
- Adicione um link de navegação entre `index.html` e `credito-modalidade.html`.

### Etapa 7 — Registro
- Atualize `run_pipeline.py` (dicionário `PIPELINES`) para incluir `credito_modalidade`.
- Atualize o roadmap/status no `CONTEXTO.md` (seção 8 "Fontes de dados" e seção 11
  "Roadmap curto") e o `README.md` com a nova página.

## Critérios de aceite
- `python run_pipeline.py credito_modalidade` roda do início ao fim sem erro.
- Página nova abre localmente (`docs/credito-modalidade.html`) e renderiza os gráficos a
  partir do JSON publicado, sem depender de dados hardcoded.
- Nenhuma fonte existente (`meios_pagamento_mensal`) quebra — rode
  `python run_pipeline.py meios_pagamento_mensal --sem-coleta` para confirmar.
- `catalogo/fontes.md` e `CONTEXTO.md` refletem a fonte nova com status atualizado.
