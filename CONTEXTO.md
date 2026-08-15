# CONTEXTO — fonte `credito_modalidade`

> Arquivo-mestre de contexto **deste repositório**. Cole/aponte este arquivo ao abrir uma
> sessão sobre esta fonte. Ao pedir uma tarefa, cite a **Etapa** correspondente
> (ex.: "trabalhar na **Etapa 4**", "ajustar a **Etapa 6** sem quebrar a **Etapa 5**").
>
> A visão de todas as fontes do projeto (convenções comuns, catálogo de candidatas,
> roadmap global) vive no repositório **`controle-global`**. Aqui só o que é desta fonte.

---

## 1. O que este repositório faz

Coleta, trata, analisa e publica a série **BCB — Crédito por modalidade (SGS)**: saldo da
carteira, taxa média de juros e spread das operações de crédito do Sistema Financeiro
Nacional, por modalidade e por segmento (PF/PJ), de mar/2011 em diante.

- **Fonte:** Banco Central do Brasil, API SGS (Sistema Gerenciador de Séries Temporais).
  Dicionário completo em [`catalogo/fonte.md`](catalogo/fonte.md).
- **Entrega:** dashboard estático em `docs/`, publicado via GitHub Pages.
- **Escopo:** uma fonte só. Nada aqui depende de outro repositório do projeto.

**Duas particularidades desta fonte:**
1. É **multi-série**: o SGS não tem consulta multi-série, então a Etapa 2 faz **uma
   requisição por código** (61 códigos) e concatena as respostas.
2. Tem **duas dimensões** (`segmento` × `modalidade_credito`), enquanto as demais fontes do
   projeto têm uma só — o contrato tidy comum acomoda isso sem mudar de forma.

## 2. Princípios de trabalho

- **Integração acima de tudo:** cada etapa tem contrato de entrada/saída definido (seção 5).
  Alterações devem respeitar esses contratos.
- **Não quebrar:** ao ajustar uma etapa, verificar as vizinhas (a que produz a entrada e a
  que consome a saída). `run_pipeline.py` deve continuar rodando de ponta a ponta.
- **Reprodutibilidade:** qualquer JSON publicado deve ser regenerável rodando o pipeline.
- **Idioma do código:** nomes de funções/variáveis e comentários em português.

## 3. Stack

| Camada | Tecnologia |
|--------|-----------|
| Coleta / tratamento / análise | Python 3.13 (`requests`, `pandas`) |
| Publicação de dados | JSON estático gerado pelo Python |
| Front-end / dashboard | HTML + CSS + JavaScript com Chart.js (via CDN) |
| Hospedagem | GitHub Pages (pasta `/docs`) |

## 4. Estrutura de pastas

```
fonte-credito-modalidade/
├── CONTEXTO.md                 # este arquivo
├── README.md
├── requirements.txt
├── run_pipeline.py             # orquestra as Etapas 2→5
├── src/
│   ├── config.py               # caminhos + registro da fonte (mapa dos 61 códigos SGS)
│   ├── coleta/credito_modalidade.py       # Etapa 2 (uma requisição por série)
│   ├── tratamento/credito_modalidade.py   # Etapa 3
│   ├── analise/credito_modalidade.py      # Etapa 4
│   ├── perfil/credito_modalidade.py       # Etapa E (+ perfil/nucleo.py)
│   └── publicacao/credito_modalidade.py   # Etapa 5
├── dados/
│   ├── brutos/                 # respostas cruas do SGS (regeneráveis; fora do git)
│   └── processados/            # CSV tidy
├── docs/                       # Etapas 6 e E — site publicado
│   ├── explorar.html                   # Etapa E — perfil + pauta analitica
│   ├── js/explorar.js
│   ├── dados/perfil_credito_modalidade.json  # Etapa E (gerado)
│   ├── dados/notas_credito_modalidade.json   # Etapa E (a mao, nunca sobrescrito)
│   ├── index.html
│   ├── css/estilo.css
│   ├── js/app.js
│   └── dados/credito_modalidade.json
├── catalogo/fonte.md           # Etapa 1 — dicionário de dados
└── prompts/                    # prompt de abertura de sessão desta fonte
```

## 5. As Etapas e os contratos entre elas

```
[API SGS — 61 séries]  ──Etapa 2──▶  dados/brutos/credito_modalidade.json
                                          │
                                     ──Etapa 3──▶  dados/processados/credito_modalidade.csv
                                          │
                     ┌────────────────────┴─────────────────┐
                ──Etapa 4──▶ métricas          ──Etapa 5──▶ docs/dados/credito_modalidade.json
                                                        │
                                                   ──Etapa 6──▶ docs/index.html
```

| Etapa | Nome | Código | Entrada → Saída | Status |
|-------|------|--------|-----------------|--------|
| 1 | Catálogo da fonte | `catalogo/fonte.md` | — → dicionário de dados | ✅ |
| 2 | Ingestão / coleta | `src/coleta/` | 61 chamadas ao SGS → JSON bruto | ✅ |
| 3 | Tratamento & modelagem | `src/tratamento/` | JSON bruto → CSV tidy | ✅ |
| 4 | Análise estatística | `src/analise/` | CSV tidy → métricas (+ resíduo) | ✅ |
| E | Exploração & pauta | `src/perfil/`, `docs/explorar.html` | bruto + tidy + auxiliares → perfil + pauta | ✅ |
| 5 | Publicação de dados | `src/publicacao/` | tidy + métricas → JSON do front | ✅ |
| 6 | Dashboard | `docs/` | JSON → site interativo | ✅ |
| 7 | Documentação & deploy | `README.md`, GitHub Pages | — → site no ar | 🟡 |

**Formato tidy (saída da Etapa 3):** `ano_mes`, `segmento`, `modalidade_credito`, `saldo`,
`taxa_juros_aa`, `spread_pp`. Segue a anatomia comum do projeto — **dimensões em linha,
medidas em coluna**, com `ano_mes` sempre como primeira dimensão; aqui as dimensões são
duas (`segmento` + `modalidade_credito`).

> `spread_pp` só é preenchido nas linhas `modalidade_credito = Total` — o BCB não publica
> spread por modalidade. Qualquer visualização de spread precisa filtrar por isso.

## 6. Convenções

- **Slug da fonte:** `credito_modalidade` — reutilizado em `src/`, `dados/` e `docs/dados/`.
- **Datas:** `data` do SGS (`DD/MM/AAAA`) normalizada para string `YYYY-MM`.
- **JSON do front:** sempre com bloco `meta` (fonte, url, gerado_em, unidades, período).
- **Unidades:** saldo em R$ milhões; taxa em % ao ano; spread em p.p. ao ano.
- **Recorte temporal:** série cortada em `01/03/2011` para alinhar saldo, juros e spread.

## 7. Como referenciar as etapas nos prompts

- "Melhorar as métricas da **Etapa 4** (adicionar sazonalidade), atualizando a **Etapa 5**."
- "Redesenhar o dashboard da **Etapa 6** sem alterar o contrato de dados da **Etapa 5**."
- Sempre que uma mudança afetar o contrato da seção 5, avise para eu ajustar as etapas vizinhas.

## 8. Roadmap curto

- [ ] Etapa 2: monitorar a estabilidade do gateway SGS (retry já implementado); avaliar cache
      incremental para não rebaixar as 61 séries inteiras a cada execução.
- [ ] Etapa 4: sazonalidade, médias móveis, correlação entre saldo e taxa.
- [ ] Etapa 6: comparação lado a lado PF × PJ na mesma modalidade.
- [ ] Etapa 7: automação de atualização agendada e melhorias de acessibilidade.

## Etapa E — exploração

Roda depois da Etapa 3 e antes da 4. Perfila quatro tabelas: o bruto (as 61 series do SGS
empilhadas), o tidy, o catalogo dos 61 codigos e a matriz de cobertura segmento x modalidade.
Segue a regra da especificacao para fontes multi-serie: perfilar as 61 series individualmente
nao acrescentaria nada (todas tem a mesma forma), entao o que se perfila e o **inventario**.

Especificacao completa no repositorio `controle-global`, em
`prompts/modelo-pagina-exploracao.md`. **A Etapa E so adiciona:** a unica alteracao em arquivo
existente foi o link "Explorar dados" na navegacao do `index.html`.
