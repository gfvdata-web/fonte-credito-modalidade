# Crédito por Modalidade — BCB/SGS

Pipeline e dashboard da série **BCB — Crédito por modalidade (SGS)**: saldo da carteira,
taxa média de juros e spread das operações de crédito do Sistema Financeiro Nacional, por
modalidade e por segmento (PF/PJ), de mar/2011 em diante.

**Painel publicado:** https://creditomodalidade.gfvdata.com/
**Explorar os dados (Etapa E):** https://creditomodalidade.gfvdata.com/explorar.html
**Skill do Claude:** https://creditomodalidade.gfvdata.com/skill/credito-modalidade-bcb.zip
— ensina o Claude a baixar a série atualizada e analisá-la sem cair nas armadilhas da fonte.
**CSV tidy:** https://creditomodalidade.gfvdata.com/dados/credito_modalidade.csv

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

O pipeline executa Etapa 2 (coleta) → Etapa 3 (tratamento) → Etapa E (perfil) → Etapa 5
(publicação) e grava em `docs/dados/` o JSON do painel, o CSV público e o perfil; por fim
regenera `skill/credito-modalidade-bcb/references/eventos.md` e o zip da skill.

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

> `docs/dados/eventos_credito_modalidade.json` (marcos e notícias anotados no painel) também é
> **escrito à mão**.

## Atualização automática

O workflow [`.github/workflows/atualizacao-mensal.yml`](.github/workflows/atualizacao-mensal.yml)
roda o pipeline **todo dia 5** (06:17 de Brasília) e commita na `main` os dados regenerados; o
Cloudflare Pages republica o site em seguida. O BCB divulga as séries de crédito cerca de quatro
semanas depois do fim do mês (agosto sai no fim de setembro), então no dia 5 de outubro a
série já traz agosto.
Só há commit quando o conteúdo muda de verdade. Para disparar manualmente:

```bash
gh workflow run atualizacao-mensal.yml
```

Testes (sem rede, segundos; o pre-commit já roda):

```bash
bash scripts/check
```

## Estrutura

| Pasta | Etapa | Papel |
|-------|-------|-------|
| `catalogo/` | 1 | Dicionário de dados da fonte |
| `src/coleta/` | 2 | Coleta das 61 séries do SGS → `dados/brutos/` |
| `src/tratamento/` | 3 | Tidy → `dados/processados/` |
| `src/analise/` | 4 | Estatística, métricas e resíduo por segmento |
| `src/perfil/` | E | Perfil das tabelas → `docs/dados/perfil_*.json` |
| `src/publicacao/` | 5 | JSON → `docs/dados/` |
| `docs/index.html` | 6 | Painel narrativo com eventos (site publicado) |
| `docs/skill.html` | 6 | Como baixar e usar a skill do Claude |
| `docs/explorar.html` | E | Perfil das tabelas + pauta analítica (fora do menu) |
| `skill/` | 5 | Skill do Claude (empacotada em `docs/skill/`) |
| `cloudflare/`, `functions/`, `wrangler.toml` | 7 | Contador de downloads (Pages Function + D1 `downloads`); `docs/_routes.json` limita as rotas |
| `scripts/`, `tests/` | — | `scripts/check` e testes sem rede |
| `.github/workflows/` | 7 | Atualização mensal |
| `prompts/` | — | Prompt de abertura de sessão desta fonte |

**Contagem de downloads.** O código (Pages Function `functions/_middleware.js`) só roda em `/contagem.json`,
`/skill/*` e `/dados/*` (`docs/_routes.json`; o resto sai direto dos estáticos). Cada GET 200 inteiro do zip da
skill ou do CSV soma 1 no D1 `downloads` (binding em `wrangler.toml`, compartilhado com os outros dois sites de
dados abertos), por arquivo, dia (Brasília) e tipo (navegador, script — a skill baixa o CSV em Python — ou
robô). Nada de IP nem cookie. `/contagem.json` publica o resumo, lido pelo painel-status.
`cloudflare/contagem.mjs` é igual nos 3 repos.

## Licença dos dados

Open Database License (ODbL) — Banco Central do Brasil. Detalhes em
[`catalogo/fonte.md`](catalogo/fonte.md).
