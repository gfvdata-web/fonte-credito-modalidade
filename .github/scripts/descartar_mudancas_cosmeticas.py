"""Etapa 7 — Descarta mudanças que não alteram o conteúdo publicado.

Roda depois do pipeline, no workflow de atualização mensal. Para cada arquivo publicado,
compara a versão nova com a do último commit e, se a diferença for só cosmética, restaura
a versão do commit (``git checkout HEAD -- <arquivo>``). Assim o workflow só commita quando
o BCB trouxe dado novo ou revisado, e não todo mês por causa de um carimbo de data.

O que conta como cosmético:

- JSON: só os carimbos de execução mudaram — ``meta.gerado_em`` e o alerta
  ``"coletado em <data>"`` que a Etapa E copia do bruto para o perfil;
- ZIP: mesmos arquivos com o mesmo conteúdo (CRC) — muda só a data interna dos membros;
- demais (CSV): só a quebra de linha (CRLF x LF) mudou.

Uso:
    python .github/scripts/descartar_mudancas_cosmeticas.py ARQUIVO [ARQUIVO ...]

Imprime ``mudou=true`` ou ``mudou=false`` e, se existir, grava o mesmo em ``$GITHUB_OUTPUT``.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def _versao_no_head(caminho: str) -> bytes | None:
    """Conteúdo do arquivo no último commit, ou None se ele ainda não é versionado."""
    proc = subprocess.run(["git", "show", f"HEAD:{caminho}"], capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


RE_COLETADO_EM = re.compile(r"^coletado em \S+$")


def _sem_coletado_em(valor: object) -> object:
    if isinstance(valor, dict):
        return {k: _sem_coletado_em(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sem_coletado_em(v) for v in valor]
    if isinstance(valor, str) and RE_COLETADO_EM.match(valor):
        return "coletado em"
    return valor


def _json_sem_carimbo(conteudo: bytes) -> object:
    dados = json.loads(conteudo.decode("utf-8"))
    if isinstance(dados, dict) and isinstance(dados.get("meta"), dict):
        dados["meta"].pop("gerado_em", None)
    return _sem_coletado_em(dados)


def _membros_zip(conteudo: bytes) -> list[tuple[str, int, int]]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        return sorted((i.filename, i.CRC, i.file_size) for i in zf.infolist())


def so_cosmetica(caminho: str, antes: bytes, depois: bytes) -> bool:
    if antes == depois:
        return True
    sufixo = Path(caminho).suffix.lower()
    if sufixo == ".json":
        return _json_sem_carimbo(antes) == _json_sem_carimbo(depois)
    if sufixo == ".zip":
        return _membros_zip(antes) == _membros_zip(depois)
    return antes.replace(b"\r\n", b"\n") == depois.replace(b"\r\n", b"\n")


def main(caminhos: list[str]) -> bool:
    for caminho in caminhos:
        arq = Path(caminho)
        if not arq.exists():
            print(f"[mudancas] {caminho}: não existe, ignorado.")
            continue
        antes = _versao_no_head(caminho)
        if antes is None:
            print(f"[mudancas] {caminho}: arquivo novo.")
            continue
        if so_cosmetica(caminho, antes, arq.read_bytes()):
            subprocess.run(["git", "checkout", "HEAD", "--", caminho], check=True)
            print(f"[mudancas] {caminho}: sem mudança de conteúdo, restaurado.")
        else:
            print(f"[mudancas] {caminho}: conteúdo mudou.")

    existentes = [c for c in caminhos if Path(c).exists()]
    if not existentes:
        return False
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *existentes],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return bool(status)


if __name__ == "__main__":
    mudou = main(sys.argv[1:])
    linha = f"mudou={'true' if mudou else 'false'}"
    print(f"[mudancas] {linha}")
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
