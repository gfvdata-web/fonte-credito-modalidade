"""Etapa 3 — Tratamento da fonte Crédito por modalidade (SGS).

O bruto vem "longo por medida" (uma linha por série×mês). Aqui as três medidas viram
colunas, produzindo o formato **tidy** desta fonte:

    ano_mes | segmento | modalidade_credito | saldo | taxa_juros_aa | spread_pp

É a mesma anatomia do contrato da seção 7 do ``CONTEXTO.md`` (dimensões em linha,
medidas em coluna), com ``forma_pagamento`` substituído pelo par ``segmento`` +
``modalidade_credito``. Não há coluna ``uf``: o SGS não publica recorte territorial
para o crédito por modalidade (só por porte de empresa) — ver ``catalogo/fontes.md``.

Grava o resultado em ``dados/processados/credito_modalidade.csv``.
"""
from __future__ import annotations

import json

import pandas as pd

from src import config

SLUG = "credito_modalidade"

# medida no bruto -> coluna no tidy
MEDIDAS = {"saldo": "saldo", "taxa": "taxa_juros_aa", "spread": "spread_pp"}
COLUNAS = ["ano_mes", "segmento", "modalidade_credito", *MEDIDAS.values()]


def _carregar_bruto(slug: str) -> list[dict]:
    caminho = config.DIR_BRUTOS / f"{slug}.json"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Bruto ausente: {caminho}. Rode a Etapa 2 (coleta) antes do tratamento."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))["registros"]


def tratar(slug: str = SLUG) -> pd.DataFrame:
    """Transforma o bruto em DataFrame tidy e salva CSV. Retorna o DataFrame."""
    config.garantir_pastas()
    cfg = config.fonte(slug)
    bruto = pd.DataFrame(_carregar_bruto(slug))

    # Data do SGS ("01/05/2026", sempre dia 1) -> "2026-05".
    data = pd.to_datetime(bruto["data"], format="%d/%m/%Y")
    bruto["ano_mes"] = data.dt.strftime("%Y-%m")
    bruto["valor"] = pd.to_numeric(bruto["valor"], errors="coerce")
    bruto["medida"] = bruto["medida"].map(MEDIDAS)

    tidy = (
        bruto.pivot_table(
            index=["ano_mes", "segmento", "modalidade"],
            columns="medida",
            values="valor",
            aggfunc="first",
        )
        .reset_index()
        .rename(columns={"modalidade": "modalidade_credito"})
        .rename_axis(columns=None)
    )
    # Garante todas as colunas de medida mesmo que alguma série volte vazia.
    for coluna in MEDIDAS.values():
        if coluna not in tidy:
            tidy[coluna] = pd.NA

    # Ordena segmentos e modalidades na ordem declarada em config (não alfabética),
    # para que a análise e o dashboard herdem uma ordem estável e previsível.
    ordem = {
        (segmento, modalidade): (i, j)
        for i, (segmento, modalidades) in enumerate(cfg["series"].items())
        for j, modalidade in enumerate(modalidades)
    }
    chave = list(zip(tidy["segmento"], tidy["modalidade_credito"]))
    tidy["_ord_seg"] = [ordem[k][0] for k in chave]
    tidy["_ord_mod"] = [ordem[k][1] for k in chave]
    tidy = (
        tidy.sort_values(["ano_mes", "_ord_seg", "_ord_mod"])
        .drop(columns=["_ord_seg", "_ord_mod"])
        .reset_index(drop=True)
    )

    tidy = tidy[COLUNAS]
    destino = config.DIR_PROCESSADOS / f"{slug}.csv"
    tidy.to_csv(destino, index=False, encoding="utf-8")
    print(f"[tratamento] {len(tidy)} linhas tidy salvas em {destino}")
    return tidy


if __name__ == "__main__":
    tratar()
