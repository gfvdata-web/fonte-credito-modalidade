"""Etapa 2 — Coleta da fonte BCB: Crédito por modalidade (SGS).

A API do SGS atende **uma série por requisição** (não há consulta multi-série), então
este coletor itera sobre os códigos registrados em ``config.FONTES[...]['series']`` e
concatena as respostas em um único envelope, gravado em
``dados/brutos/credito_modalidade.json``.

Nada é transformado aqui além de anexar a identificação da série (segmento, modalidade,
medida) a cada observação — o tratamento fica na Etapa 3.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import requests

from src import config

SLUG = "credito_modalidade"

# O gateway do SGS às vezes recusa requisições legítimas (HTML de "Requisição inválida")
# quando recebe muitas chamadas seguidas — daí a pausa entre séries e o retry com espera.
PAUSA_ENTRE_SERIES = 0.2
TENTATIVAS = 4


def _baixar_serie(url: str, timeout: int) -> list[dict]:
    """Baixa uma série do SGS, com novas tentativas em caso de bloqueio temporário."""
    erro_final: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = requests.get(url, timeout=timeout)
            resposta.raise_for_status()
            # Sob bloqueio o gateway responde 200 com uma página HTML; .json() falha.
            return resposta.json()
        except (requests.RequestException, ValueError) as erro:
            erro_final = erro
            if tentativa < TENTATIVAS:
                time.sleep(2 ** tentativa)  # 2s, 4s, 8s
    raise RuntimeError(f"Falha ao baixar {url}: {erro_final}")


def coletar(slug: str = SLUG, timeout: int = 60) -> list[dict]:
    """Baixa todas as séries configuradas e salva o JSON bruto. Retorna os registros."""
    config.garantir_pastas()
    cfg = config.fonte(slug)
    series = config.series_sgs(cfg)

    print(f"[coleta] consultando: {cfg['nome']} ({len(series)} séries do SGS)")
    registros: list[dict] = []
    for i, (segmento, modalidade, medida, codigo) in enumerate(series, start=1):
        url = cfg["url"].format(codigo=codigo) + f"&dataInicial={cfg['data_inicial']}"
        observacoes = _baixar_serie(url, timeout)
        for obs in observacoes:
            registros.append({
                "segmento": segmento,
                "modalidade": modalidade,
                "medida": medida,
                "codigo_sgs": codigo,
                "data": obs["data"],      # "DD/MM/AAAA"
                "valor": obs["valor"],    # string decimal
            })
        print(f"[coleta]   {i}/{len(series)} série {codigo} "
              f"({segmento} · {modalidade} · {medida}): {len(observacoes)} observações")
        time.sleep(PAUSA_ENTRE_SERIES)

    envelope = {
        "fonte": cfg["nome"],
        "url": cfg["url"],
        "coletado_em": datetime.now(timezone.utc).isoformat(),
        "total_registros": len(registros),
        "registros": registros,
    }
    destino = config.DIR_BRUTOS / f"{slug}.json"
    destino.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[coleta] {len(registros)} registros salvos em {destino}")
    return registros


if __name__ == "__main__":
    coletar()
