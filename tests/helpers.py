"""Apoio dos testes: caminhos, fixture da API do SGS e ambiente isolado em pasta temporária.

Nada aqui acessa a rede nem escreve dentro do repositório: o pipeline roda com as pastas de
dados (src.config) redirecionadas para um diretório temporário. Se existir o empacotador da
skill (src/publicacao/skill.py), os caminhos dele também vão para a pasta temporária.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
DADOS_PUB = DOCS / "dados"
FIXTURE_SGS = RAIZ / "tests" / "fixtures" / "sgs_respostas.json"
SLUG = "credito_modalidade"
RE_CODIGO = re.compile(r"bcdata\.sgs\.(\d+)/")


def ler_json(caminho: Path):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def ler_texto(caminho: Path) -> str:
    """Texto com quebras de linha normalizadas (o checkout no Windows converte para CRLF)."""
    return Path(caminho).read_text(encoding="utf-8").replace("\r\n", "\n")


def fixture_sgs() -> dict:
    """Fixture das respostas do SGS (cópia segura para mutar)."""
    return ler_json(FIXTURE_SGS)


def medida_do_codigo(codigo: int) -> str:
    from src import config
    for _, _, medida, cod in config.series_sgs(config.fonte()):
        if cod == codigo:
            return medida
    raise KeyError(codigo)


def corpo_do_codigo(codigo: int, fx: dict | None = None) -> list[dict]:
    """O que a API devolveria para o código: série própria da fixture ou o padrão da medida."""
    fx = fx or fixture_sgs()
    return fx["por_codigo"].get(str(codigo)) or fx["padrao"][medida_do_codigo(codigo)]


class RespostaFalsa:
    """Substituto mínimo de requests.Response."""

    def __init__(self, corpo, status: int = 200, json_invalido: bool = False):
        self._corpo, self.status_code, self._invalido = corpo, status, json_invalido

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._invalido:
            raise ValueError("Expecting value: resposta HTML do gateway")
        return self._corpo


def _modulo_skill():
    try:
        return importlib.import_module("src.publicacao.skill")
    except ImportError:
        return None


@contextlib.contextmanager
def ambiente_isolado():
    """Redireciona dados/, docs/dados/ (e a skill, se houver) para uma pasta temporária."""
    from src import config

    with tempfile.TemporaryDirectory(prefix="cm-teste-") as tmp:
        raiz = Path(tmp)
        brutos, proc, pub = raiz / "dados" / "brutos", raiz / "dados" / "processados", raiz / "docs" / "dados"
        pub.mkdir(parents=True)
        with contextlib.ExitStack() as pilha:
            pilha.enter_context(mock.patch.object(config, "DIR_BRUTOS", brutos))
            pilha.enter_context(mock.patch.object(config, "DIR_PROCESSADOS", proc))
            pilha.enter_context(mock.patch.object(config, "DIR_PUBLICADOS", pub))
            skill = _modulo_skill()
            if skill is not None:
                dir_skill = raiz / "skill" / skill.NOME_SKILL
                if skill.DIR_SKILL.exists():
                    shutil.copytree(skill.DIR_SKILL, dir_skill)
                eventos = DADOS_PUB / skill.ARQ_EVENTOS.name
                if eventos.exists():
                    shutil.copy(eventos, pub / eventos.name)
                pilha.enter_context(mock.patch.object(skill, "DIR_SKILL", dir_skill))
                pilha.enter_context(mock.patch.object(skill, "DESTINO_ZIP", raiz / "docs" / "skill" / skill.DESTINO_ZIP.name))
                pilha.enter_context(mock.patch.object(skill, "ARQ_EVENTOS", pub / skill.ARQ_EVENTOS.name))
            yield raiz


def _get_falso(fx: dict, falhas_por_codigo: dict | None = None):
    chamadas = []

    def get(url, timeout=None, **_):
        codigo = int(RE_CODIGO.search(url).group(1))
        chamadas.append(url)
        falha = (falhas_por_codigo or {}).get(codigo)
        if falha:
            return falha(sum(1 for u in chamadas if f"sgs.{codigo}/" in u))
        return RespostaFalsa(corpo_do_codigo(codigo, fx))

    get.chamadas = chamadas
    return get


@contextlib.contextmanager
def api_falsa(fx: dict | None = None, falhas_por_codigo: dict | None = None):
    """Troca requests.get pela fixture do SGS e tira as pausas. Sem rede, sem espera.

    `falhas_por_codigo`: {codigo: f(n_tentativa) -> RespostaFalsa} para simular erro/bloqueio.
    """
    get = _get_falso(fx or fixture_sgs(), falhas_por_codigo)
    with mock.patch("requests.get", side_effect=get) as falso, mock.patch("time.sleep"):
        falso.chamadas = get.chamadas
        yield falso


@contextlib.contextmanager
def sem_saida():
    """Silencia os print() do pipeline."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield
