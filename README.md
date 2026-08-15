# Crédito por Modalidade — BCB/SGS

Pipeline e dashboard da série **BCB — Crédito por modalidade (SGS)**: saldo da carteira,
taxa média de juros e spread das operações de crédito do Sistema Financeiro Nacional, por
modalidade e por segmento (PF/PJ), de mar/2011 em diante.

**Painel publicado:** https://gfvdata-web.github.io/fonte-credito-modalidade/
**Explorar os dados (Etapa E):** https://gfvdata-web.github.io/fonte-credito-modalidade/explorar.html

> 📄 Organização do repositório e etapas do pipeline: **[CONTEXTO.md](CONTEXTO.md)**
> 📚 Dicionário de dados da fonte: **[catalogo/fonte.md](catalogo/fonte.md)**
> 🌐 Visão de todas as fontes do projeto: repositório **`controle-global`**

## Como rodar

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_pipeline.py
```

O pipeline executa Etapa 2 (coleta) → Etapa 3 (tratamento) → Etapa 5 (publicação) e grava
o JSON que o dashboard consome em `docs/dados/`.

`python run_pipeline.py --sem-coleta` reaproveita o dado bruto já baixado (não chama a API).

> A coleta faz **61 requisições** ao SGS (uma por série), com pausa entre elas — leva
> alguns minutos. O gateway do BCB ocasionalmente responde com uma página de erro em HTTP
> 200; a Etapa 2 já trata isso com retry e espera crescente.

Para ver o dashboard localmente:

```bash
python -m http.server 8000 --directory docs
```

> **Etapa E.** `python run_pipeline.py --sem-perfil` pula a perfilagem.
> `docs/dados/notas_credito_modalidade.json` é **escrito à mão** e nenhum script o sobrescreve:
> é onde ficam as armadilhas, os comparativos, o contexto externo pesquisado e a pauta
> de visualizações que alimentam a página `explorar.html`.

## Estrutura

| Pasta | Etapa | Papel |
|-------|-------|-------|
| `catalogo/` | 1 | Dicionário de dados da fonte |
| `src/coleta/` | 2 | Coleta das 61 séries do SGS → `dados/brutos/` |
| `src/tratamento/` | 3 | Tidy → `dados/processados/` |
| `src/analise/` | 4 | Estatística, métricas e resíduo por segmento |
| `src/perfil/` | E | Perfil das tabelas → `docs/dados/perfil_*.json` |
| `src/publicacao/` | 5 | JSON → `docs/dados/` |
| `docs/index.html` | 6 | Dashboard (site publicado) |
| `docs/explorar.html` | E | Perfil das tabelas + pauta analítica |
| `prompts/` | — | Prompt de abertura de sessão desta fonte |

## Licença dos dados

Open Database License (ODbL) — Banco Central do Brasil. Detalhes em
[`catalogo/fonte.md`](catalogo/fonte.md).
