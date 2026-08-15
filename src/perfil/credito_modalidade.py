"""Etapa E — perfil das tabelas da fonte `credito_modalidade`.

Esta é a fonte multi-série do projeto: 61 códigos do SGS, uma requisição cada. Perfilar
61 tabelas idênticas não teria valor — o que interessa é **o inventário** delas. Por isso:

- **bruto**    — a resposta empilhada das 61 séries, já anotada pela Etapa 2 com
  `segmento`, `modalidade`, `medida` e `codigo_sgs`;
- **tidy**     — `dados/processados/credito_modalidade.csv`;
- **auxiliar** — `series` (o catálogo dos 61 códigos, com vida útil de cada um) e
  `modalidades` (segmento × modalidade e quais medidas existem — a tabela que torna
  visível que **spread só existe nas linhas Total**).

Gera `docs/dados/perfil_credito_modalidade.json`.
"""
from __future__ import annotations

import json

import pandas as pd

from src import config
from src.perfil import nucleo

SLUG = "credito_modalidade"

DECLARACAO: dict[str, dict] = {
    "bruto": {
        "granularidade": "uma linha por código SGS × mês (as 61 séries empilhadas)",
        "chave_primaria": ["codigo_sgs", "data"],
        "colunas": {
            "segmento": ("dimensao", None, "Total, PF ou PJ — anotado pela Etapa 2"),
            "modalidade": ("dimensao", None, "Modalidade de crédito — anotado pela Etapa 2"),
            "medida": ("dimensao", None, "saldo, taxa ou spread — anotado pela Etapa 2"),
            "codigo_sgs": ("chave", None, "Código da série no SGS/BCB"),
            "data": ("data", None, "Mês de referência, no formato DD/MM/AAAA da API"),
            "valor": ("medida", "depende da medida",
                      "Valor da série; a unidade só se resolve pela coluna `medida`"),
        },
    },
    "tidy": {
        "granularidade": "uma linha por mês × segmento × modalidade",
        "chave_primaria": ["ano_mes", "segmento", "modalidade_credito"],
        "colunas": {
            "ano_mes": ("data", None, "Mês de referência (YYYY-MM)"),
            "segmento": ("dimensao", None, "Total, PF (pessoas físicas) ou PJ (pessoas jurídicas)"),
            "modalidade_credito": ("dimensao", None, "Modalidade da operação de crédito"),
            "saldo": ("medida", "R$ milhões", "Saldo da carteira no fim do mês (estoque)"),
            "taxa_juros_aa": ("medida", "% ao ano", "Taxa média de juros das concessões"),
            "spread_pp": ("medida", "p.p. ao ano",
                          "Spread sobre o custo de captação — o BCB só publica nos agregados"),
        },
    },
    "aux_series": {
        "granularidade": "uma linha por código SGS consultado",
        "chave_primaria": ["codigo_sgs"],
        "colunas": {
            "codigo_sgs": ("chave", None, "Código da série no SGS/BCB"),
            "segmento": ("dimensao", None, "Segmento a que a série pertence"),
            "modalidade": ("dimensao", None, "Modalidade a que a série pertence"),
            "medida": ("dimensao", None, "saldo, taxa ou spread"),
            "observacoes": ("medida", "meses", "Meses devolvidos pela API para esta série"),
            "primeiro_mes": ("data", None, "Primeiro mês devolvido"),
            "ultimo_mes": ("data", None, "Último mês devolvido"),
        },
    },
    "aux_modalidades": {
        "granularidade": "uma linha por segmento × modalidade",
        "chave_primaria": ["segmento", "modalidade_credito"],
        "colunas": {
            "segmento": ("dimensao", None, "Total, PF ou PJ"),
            "modalidade_credito": ("chave", None, "Modalidade da operação"),
            "tem_saldo": ("dimensao", None, "A série de saldo existe para esta combinação"),
            "tem_taxa": ("dimensao", None, "A série de taxa existe para esta combinação"),
            "tem_spread": ("dimensao", None, "A série de spread existe — só nos agregados"),
            "meses": ("medida", "meses", "Meses presentes no tidy"),
            "primeiro_mes": ("data", None, "Primeiro mês no tidy"),
            "ultimo_mes": ("data", None, "Último mês no tidy"),
        },
    },
}


def _ler_bruto() -> tuple[pd.DataFrame, dict]:
    caminho = config.DIR_BRUTOS / f"{SLUG}.json"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Bruto ausente: {caminho}. Rode a Etapa 2 (coleta) antes da Etapa E."
        )
    envelope = json.loads(caminho.read_text(encoding="utf-8"))
    return pd.DataFrame(envelope["registros"]), envelope


def _catalogo_series(bruto: pd.DataFrame) -> pd.DataFrame:
    b = bruto.copy()
    b["ano_mes"] = b["data"].str.slice(6, 10) + "-" + b["data"].str.slice(3, 5)
    cat = (b.groupby(["codigo_sgs", "segmento", "modalidade", "medida"])
             .agg(observacoes=("ano_mes", "nunique"),
                  primeiro_mes=("ano_mes", "min"),
                  ultimo_mes=("ano_mes", "max"))
             .reset_index()
             .sort_values("codigo_sgs"))
    return cat


def _catalogo_modalidades(tidy: pd.DataFrame) -> pd.DataFrame:
    def marca(serie: pd.Series) -> str:
        return "sim" if serie.notna().any() else "nao"

    return (tidy.groupby(["segmento", "modalidade_credito"])
            .agg(tem_saldo=("saldo", marca),
                 tem_taxa=("taxa_juros_aa", marca),
                 tem_spread=("spread_pp", marca),
                 meses=("ano_mes", "nunique"),
                 primeiro_mes=("ano_mes", "min"),
                 ultimo_mes=("ano_mes", "max"))
            .reset_index())


def perfilar(slug: str = SLUG) -> dict:
    cfg = config.fonte(slug)
    bruto, envelope = _ler_bruto()
    tidy = pd.read_csv(config.DIR_PROCESSADOS / f"{slug}.csv", dtype={"ano_mes": str})
    series = _catalogo_series(bruto)
    modalidades = _catalogo_modalidades(tidy)

    n_series = int(series["codigo_sgs"].nunique())
    sem_spread = int((modalidades["tem_spread"] == "nao").sum())

    t_bruto = nucleo.perfilar_tabela(
        bruto, id="bruto", camada="bruto",
        nome=f"Respostas das {n_series} séries do SGS, empilhadas",
        arquivo=f"dados/brutos/{slug}.json",
        formato="JSON (API SGS) — não versionado; este perfil é o registro da forma dele",
        origem=cfg["url"],
        declaracao=DECLARACAO["bruto"],
        alertas_extra=[
            f"coletado em {envelope.get('coletado_em', '?')}",
            f"o SGS não tem consulta multi-série: são {n_series} requisições, uma por código, "
            "concatenadas pela Etapa 2",
            "`segmento`, `modalidade` e `medida` NÃO vêm da API — a resposta crua do SGS tem só "
            "`data` e `valor`. Essas três colunas são anotadas pela Etapa 2 a partir do mapa em "
            "src/config.py, e é o que torna as 61 séries uma tabela só",
            "a unidade de `valor` muda conforme a linha: R$ milhões para saldo, % a.a. para taxa, "
            "p.p. para spread. Somar a coluna inteira não significa nada",
        ],
    )
    t_tidy = nucleo.perfilar_tabela(
        tidy, id="tidy", camada="tidy",
        nome="Tidy do projeto — duas dimensões de recorte e três medidas",
        arquivo=f"dados/processados/{slug}.csv",
        formato="CSV UTF-8",
        origem="Etapa 3 (src/tratamento/credito_modalidade.py)",
        declaracao=DECLARACAO["tidy"],
        alertas_extra=[
            "os nulos de `spread_pp` são ESTRUTURAIS: o BCB só publica spread para os agregados "
            f"(linhas `Total`). {sem_spread} das {len(modalidades)} combinações não têm a série. "
            "Não é dado faltante — é ausência com significado",
            "`saldo` é ESTOQUE (posição no fim do mês) e `taxa_juros_aa` é preço médio das "
            "CONCESSÕES do mês. Somar saldos ao longo do tempo, ou tirar média simples de taxas "
            "entre modalidades sem ponderar pelo saldo, são dois erros diferentes e ambos fáceis",
        ],
    )
    t_series = nucleo.perfilar_tabela(
        series, id="aux_series", camada="auxiliar",
        nome=f"Catálogo dos {n_series} códigos SGS consultados",
        arquivo="src/config.py (mapa `series`) + bruto",
        formato="tabela derivada",
        origem="Etapa E",
        declaracao=DECLARACAO["aux_series"],
        alertas_extra=[
            "perfilar as 61 séries individualmente não acrescentaria nada — todas têm a mesma "
            "forma (`data`, `valor`). O que tem valor analítico é este inventário",
        ],
    )
    t_mod = nucleo.perfilar_tabela(
        modalidades, id="aux_modalidades", camada="auxiliar",
        nome="Cobertura de medidas por segmento × modalidade",
        arquivo="derivada do tidy",
        formato="tabela derivada",
        origem="Etapa E",
        declaracao=DECLARACAO["aux_modalidades"],
    )

    bruto_combo = pd.DataFrame({
        "segmento_modalidade": bruto["segmento"] + " | " + bruto["modalidade"]})
    tidy_combo = pd.DataFrame({
        "segmento_modalidade": tidy["segmento"] + " | " + tidy["modalidade_credito"]})
    mod_combo = modalidades.assign(
        segmento_modalidade=modalidades["segmento"] + " | " + modalidades["modalidade_credito"])

    rel_cod = nucleo.relacionamento(
        bruto, "codigo_sgs", series, "codigo_sgs", cardinalidade="N:1",
        uso="toda linha do bruto resolve para uma série registrada em src/config.py")
    rel_mod = nucleo.relacionamento(
        tidy_combo, "segmento_modalidade", mod_combo, "segmento_modalidade",
        cardinalidade="N:1",
        uso="resolve a combinação para quais das três medidas existem")
    rel_bruto_tidy = nucleo.relacionamento(
        bruto_combo, "segmento_modalidade", mod_combo, "segmento_modalidade",
        cardinalidade="N:1",
        uso="nenhuma combinação do bruto se perde no caminho até o tidy")
    for rel in (rel_mod, rel_bruto_tidy):
        rel["de"] = "segmento + modalidade"
        rel["para"] = "segmento + modalidade_credito"

    perfil = nucleo.montar(
        slug=slug,
        fonte_nome=cfg["nome"],
        tabelas=[t_bruto, t_tidy, t_series, t_mod],
        relacionamentos=[
            nucleo.liga(rel_cod, "bruto", "aux_series"),
            nucleo.liga(rel_mod, "tidy", "aux_modalidades"),
            nucleo.liga(rel_bruto_tidy, "bruto", "aux_modalidades"),
        ],
        cobertura=nucleo.cobertura_temporal(tidy),
    )
    nucleo.salvar(perfil, config.DIR_PUBLICADOS / f"perfil_{slug}.json")
    return perfil


if __name__ == "__main__":
    perfilar()
