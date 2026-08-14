"""Configuração do repositório — fonte `credito_modalidade`.

Concentra caminhos de pastas e o registro da fonte usado por todas as etapas.
Este repositório cobre **uma única fonte**; o registro segue em formato de dicionário
por slug para manter o mesmo contrato de código das demais fontes do projeto.
"""
from __future__ import annotations

from pathlib import Path

# --- Caminhos base -----------------------------------------------------------
# src/config.py  ->  raiz do projeto = parent de src/
RAIZ = Path(__file__).resolve().parent.parent

DIR_DADOS = RAIZ / "dados"
DIR_BRUTOS = DIR_DADOS / "brutos"            # Etapa 2 (respostas cruas da API)
DIR_PROCESSADOS = DIR_DADOS / "processados"  # Etapa 3 (CSV tidy)
DIR_PUBLICADOS = RAIZ / "docs" / "dados"     # Etapa 5 (JSON consumido pelo front)


def garantir_pastas() -> None:
    """Cria as pastas de dados caso ainda não existam."""
    for pasta in (DIR_BRUTOS, DIR_PROCESSADOS, DIR_PUBLICADOS):
        pasta.mkdir(parents=True, exist_ok=True)


# --- Registro da fonte -------------------------------------------------------
# API do SGS (Sistema Gerenciador de Séries Temporais): uma chamada por código de série.
BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"

SLUG = "credito_modalidade"

FONTES: dict[str, dict] = {
    "credito_modalidade": {
        "nome": "BCB — Crédito por modalidade (SGS)",
        "descricao": (
            "Saldo da carteira, taxa média de juros e spread das operações de crédito "
            "do Sistema Financeiro Nacional, por modalidade e por segmento (PF/PJ)."
        ),
        # Uma chamada por código de série (o SGS não tem consulta multi-série).
        "url": BCB_SGS_URL,
        # Dados nacionais: o SGS só publica recorte por UF para crédito PJ por *porte*
        # (MEI/microempresa/pequeno porte), não por modalidade — por isso não há coluna `uf`.
        "url_portal": "https://dadosabertos.bcb.gov.br/dataset/20539-saldo-da-carteira-de-credito---total",
        # Séries de juros/spread por modalidade começam em mar/2011; o saldo vem de 2007,
        # mas cortamos em 2011-03 para que todas as medidas cubram o mesmo período.
        "data_inicial": "01/03/2011",
        "segmentos": {
            "Total": "Total (PF + PJ)",
            "PF": "Pessoas físicas",
            "PJ": "Pessoas jurídicas",
        },
        # segmento -> modalidade -> medida -> código da série no SGS.
        # "Total" é a linha agregada do segmento (única com spread publicado).
        "series": {
            "Total": {
                "Total": {"saldo": 20539, "taxa": 20714, "spread": 20783},
            },
            "PF": {
                "Total": {"saldo": 20541, "taxa": 20716, "spread": 20785},
                "Cheque especial": {"saldo": 20573, "taxa": 20741},
                "Crédito pessoal não consignado": {"saldo": 20574, "taxa": 20742},
                "Crédito pessoal consignado": {"saldo": 20579, "taxa": 20747},
                "Aquisição de veículos": {"saldo": 20581, "taxa": 20749},
                "Cartão de crédito rotativo": {"saldo": 20587, "taxa": 22022},
                "Cartão de crédito parcelado": {"saldo": 20588, "taxa": 22023},
                "Desconto de cheques": {"saldo": 20591, "taxa": 20755},
                "Crédito rural": {"saldo": 20609, "taxa": 20771},
                "Financiamento imobiliário": {"saldo": 20612, "taxa": 20774},
                "Microcrédito": {"saldo": 20620, "taxa": 20782},
            },
            "PJ": {
                "Total": {"saldo": 20540, "taxa": 20715, "spread": 20784},
                "Desconto de duplicatas e recebíveis": {"saldo": 20544, "taxa": 20719},
                "Capital de giro": {"saldo": 20550, "taxa": 20725},
                "Conta garantida": {"saldo": 20551, "taxa": 20726},
                "Cheque especial": {"saldo": 20552, "taxa": 20727},
                "Aquisição de veículos": {"saldo": 20553, "taxa": 20728},
                "Vendor": {"saldo": 20559, "taxa": 20734},
                "Compror": {"saldo": 20560, "taxa": 20735},
                "Cartão de crédito rotativo": {"saldo": 20561, "taxa": 22019},
                "Cartão de crédito parcelado": {"saldo": 20562, "taxa": 22020},
                "Adiantamento sobre contratos de câmbio (ACC)": {"saldo": 20565, "taxa": 20736},
                "Financiamento a importações": {"saldo": 20566, "taxa": 20737},
                "Financiamento a exportações": {"saldo": 20567, "taxa": 20738},
                "Repasse externo": {"saldo": 20568, "taxa": 20739},
                "Crédito rural": {"saldo": 20597, "taxa": 20760},
                "Financiamento imobiliário": {"saldo": 20600, "taxa": 20763},
                "Financiamento com recursos do BNDES": {"saldo": 20604, "taxa": 20767},
            },
        },
        "unidades": {
            "saldo": "R$ milhões",
            "taxa_juros_aa": "% ao ano",
            "spread_pp": "p.p. ao ano",
        },
        "periodicidade": "mensal",
        "licenca": "Open Database License (ODbL) — Banco Central do Brasil",
    },
}


def series_sgs(cfg: dict) -> list[tuple[str, str, str, int]]:
    """Achata ``cfg['series']`` em ``(segmento, modalidade, medida, codigo)``.

    Usado pela coleta (uma requisição por tupla) e pela análise (para saber quais
    combinações existem sem reabrir o dicionário aninhado).
    """
    return [
        (segmento, modalidade, medida, codigo)
        for segmento, modalidades in cfg["series"].items()
        for modalidade, medidas in modalidades.items()
        for medida, codigo in medidas.items()
    ]


def fonte(slug: str = SLUG) -> dict:
    """Retorna a configuração da fonte pelo slug, com erro claro se ausente."""
    if slug not in FONTES:
        disponiveis = ", ".join(FONTES) or "(nenhuma)"
        raise KeyError(f"Fonte '{slug}' não registrada. Disponíveis: {disponiveis}")
    return FONTES[slug]
