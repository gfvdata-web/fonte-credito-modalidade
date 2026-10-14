"""Etapa 5 (complemento) — Empacota a skill do Claude para download no site.

A skill vive em ``skill/credito-modalidade-bcb/``. Este módulo:

1. regenera ``references/eventos.md`` a partir de ``docs/dados/eventos_credito_modalidade.json``,
   para o catálogo de marcos da skill nunca divergir do que o painel mostra;
2. compacta a pasta em ``docs/skill/credito-modalidade-bcb.zip``, servido pelo Cloudflare Pages.

A skill não embute a série: ela baixa o dado na hora (API SGS do BCB ou CSV do site), então o
zip só precisa ser regenerado quando instruções ou eventos mudarem.
"""
from __future__ import annotations

import json
import zipfile

from src import config

NOME_SKILL = "credito-modalidade-bcb"
DIR_SKILL = config.RAIZ / "skill" / NOME_SKILL
DESTINO_ZIP = config.RAIZ / "docs" / "skill" / f"{NOME_SKILL}.zip"
ARQ_EVENTOS = config.DIR_PUBLICADOS / "eventos_credito_modalidade.json"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _mes_extenso(ano_mes: str) -> str:
    ano, mes = ano_mes.split("-")
    return f"{MESES[int(mes) - 1]}/{ano}"


def gerar_eventos_md() -> None:
    eventos = sorted(json.loads(ARQ_EVENTOS.read_text(encoding="utf-8")), key=lambda e: e["data"])
    linhas = [
        "# Marcos históricos do crédito por modalidade",
        "",
        "Catálogo curado no painel, em ordem cronológica. Use-o para situar mudanças na série,",
        "citando um evento só quando a data bater com o que o dado mostra (\"coincide com\",",
        "não \"causou\"). Cada evento indica os segmentos (PF/PJ) e as modalidades afetadas.",
        "",
        "> Arquivo gerado a partir de `eventos_credito_modalidade.json`; não edite à mão.",
        "",
    ]
    for ev in eventos:
        segmentos = ", ".join(ev.get("segmentos") or []) or "—"
        modalidades = ", ".join(ev.get("modalidades") or []) or "—"
        linhas += [
            f"## {_mes_extenso(ev['data'])} — {ev['titulo']}",
            f"*Segmentos: {segmentos} · Modalidades: {modalidades}*",
            "",
            ev["descricao"],
            "",
            f"Fonte: {ev['fonte']}",
            "",
        ]
    destino = DIR_SKILL / "references" / "eventos.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"[skill] {len(eventos)} eventos escritos em {destino}")


def empacotar() -> None:
    gerar_eventos_md()
    DESTINO_ZIP.parent.mkdir(parents=True, exist_ok=True)
    arquivos = sorted(
        p for p in DIR_SKILL.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    with zipfile.ZipFile(DESTINO_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for arq in arquivos:
            # A pasta da skill fica na raiz do zip, como o claude.ai espera.
            zf.write(arq, arq.relative_to(DIR_SKILL.parent).as_posix())
    print(f"[skill] {len(arquivos)} arquivos empacotados em {DESTINO_ZIP}")


if __name__ == "__main__":
    empacotar()
