"""Etapa 5 — Publicação da fonte Crédito por modalidade (SGS).

Reúne a saída da análise (Etapa 4) com metadados da fonte e grava um JSON
compacto em ``docs/dados/credito_modalidade.json``, consumido pelo dashboard
``docs/index.html`` + ``docs/js/app-v2.js`` (Etapa 6). Copia também o CSV tratado para
``docs/dados/credito_modalidade.csv``, para download no site e uso pela skill do Claude.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

from src import config
from src.analise import credito_modalidade as analise

SLUG = "credito_modalidade"


def publicar(slug: str = SLUG) -> dict:
    """Monta o pacote final e grava o JSON em docs/dados/. Retorna o pacote."""
    config.garantir_pastas()
    cfg = config.fonte(slug)
    resultado = analise.analisar(slug)

    pacote = {
        "meta": {
            "fonte": cfg["nome"],
            "descricao": cfg["descricao"],
            "url": cfg["url_portal"],
            "unidades": cfg["unidades"],
            "periodicidade": cfg["periodicidade"],
            "licenca": cfg["licenca"],
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "periodo": {
                "inicio": resultado["labels"][0],
                "fim": resultado["labels"][-1],
            },
            # Quantos códigos do SGS estão por trás deste pacote (rastreabilidade).
            "series_sgs": len(config.series_sgs(cfg)),
        },
        **resultado,
    }

    destino = config.DIR_PUBLICADOS / f"{slug}.json"
    destino.write_text(json.dumps(pacote, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[publicacao] JSON do dashboard salvo em {destino}")

    # CSV tidy público: mesmo arquivo da Etapa 3, para download e para a skill do Claude.
    csv_publico = config.DIR_PUBLICADOS / f"{slug}.csv"
    shutil.copyfile(config.DIR_PROCESSADOS / f"{slug}.csv", csv_publico)
    print(f"[publicacao] CSV tidy publicado em {csv_publico}")
    return pacote


if __name__ == "__main__":
    publicar()
