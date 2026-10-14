"""Carrega a série BCB de Crédito por modalidade (mensal) em formato longo, pronta para análise.

Só usa a biblioteca padrão do Python, para rodar em qualquer ambiente.

Ordem de tentativa (origem "auto"):
  1. API SGS do Banco Central (dado oficial e mais recente; uma requisição por série,
     61 no total, juntadas aqui);
  2. CSV tratado publicado pelo projeto (Cloudflare Pages), caso a API esteja fora ou bloqueada;
  3. se as duas falharem, o script avisa e sai com código 2 — peça o CSV ao usuário
     e rode de novo com --arquivo.

Saída: CSV com as colunas
  ano_mes, segmento, modalidade_credito, saldo, taxa_juros_aa, spread_pp [, saldo_real]

Unidades: saldo em R$ milhões (nominal); taxa em % ao ano; spread em pontos percentuais.
O spread só existe nas linhas modalidade_credito = Total (agregado de cada segmento).

Uso:
  python carregar_dados.py                          # auto, grava credito_modalidade.csv
  python carregar_dados.py --origem bcb             # força a API do SGS
  python carregar_dados.py --arquivo anexo.csv      # usa um arquivo enviado pelo usuário
  python carregar_dados.py --ipca                   # acrescenta saldo deflacionado pelo IPCA
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

URL_SITE = "https://creditomodalidade.gfvdata.com/dados/credito_modalidade.csv"
URL_SGS = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial=01/03/2011"
)
# IPCA — variação mensal (%), série 433 do SGS/BCB.
URL_IPCA = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
    "?formato=json&dataInicial=01/03/2011"
)
CABECALHO_UA = {"User-Agent": "skill-credito-modalidade-bcb/1.0"}
TENTATIVAS = 4
PAUSA_ENTRE_SERIES = 0.2

# segmento -> modalidade -> medida -> código no SGS (cópia de src/config.py do projeto).
# "Total" é a linha agregada do segmento, a única com spread publicado.
SERIES = {
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
}
# medida da configuração -> coluna do arquivo gerado
COLUNA_MEDIDA = {"saldo": "saldo", "taxa": "taxa_juros_aa", "spread": "spread_pp"}
COLUNAS_MEDIDAS = list(COLUNA_MEDIDA.values())


def _baixar(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=CABECALHO_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _baixar_json(url: str, timeout: int = 60):
    """Baixa um JSON do SGS com novas tentativas.

    Sob muitas chamadas seguidas o gateway do SGS responde 200 com uma página HTML de
    "Requisição inválida"; o json.loads falha e a tentativa é repetida com espera.
    """
    erro_final: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return json.loads(_baixar(url, timeout))
        except Exception as exc:
            erro_final = exc
            if tentativa < TENTATIVAS:
                time.sleep(2 ** tentativa)
    raise RuntimeError(f"{url}: {type(erro_final).__name__}: {erro_final}")


# --- Leitura das origens -----------------------------------------------------

def _numero(texto) -> float | None:
    """Converte texto em número; vazio vira None (ausência, não zero)."""
    if texto is None or str(texto).strip() == "":
        return None
    return float(texto)


def _montar(observacoes: list[tuple[str, str, str, str, float]]) -> list[dict]:
    """Junta observações (ano_mes, segmento, modalidade, coluna, valor) em linhas largas."""
    linhas: dict[tuple[str, str, str], dict] = {}
    for ano_mes, segmento, modalidade, coluna, valor in observacoes:
        chave = (ano_mes, segmento, modalidade)
        linha = linhas.setdefault(chave, {
            "ano_mes": ano_mes, "segmento": segmento, "modalidade_credito": modalidade,
            "saldo": None, "taxa_juros_aa": None, "spread_pp": None,
        })
        linha[coluna] = valor
    return list(linhas.values())


def _do_sgs() -> list[dict]:
    """Baixa as 61 séries do SGS e junta no formato longo."""
    observacoes = []
    total = sum(len(m) for mods in SERIES.values() for m in mods.values())
    feitas = 0
    for segmento, modalidades in SERIES.items():
        for modalidade, medidas in modalidades.items():
            for medida, codigo in medidas.items():
                for obs in _baixar_json(URL_SGS.format(codigo=codigo)):
                    dia, mes, ano = obs["data"].split("/")
                    observacoes.append((f"{ano}-{mes}", segmento, modalidade,
                                        COLUNA_MEDIDA[medida], _numero(obs["valor"])))
                feitas += 1
                time.sleep(PAUSA_ENTRE_SERIES)
    print(f"[sgs] {feitas}/{total} séries baixadas.", file=sys.stderr)
    return _montar(observacoes)


def _de_csv(texto: str) -> list[dict]:
    """Lê o CSV longo do projeto (mesmas colunas da saída deste script)."""
    leitor = csv.DictReader(io.StringIO(texto.lstrip("﻿")))
    linhas = list(leitor)
    if not linhas:
        raise ValueError("CSV vazio.")
    obrigatorias = {"ano_mes", "segmento", "modalidade_credito", "saldo", "taxa_juros_aa"}
    if not obrigatorias <= set(linhas[0]):
        raise ValueError(f"Formato de CSV não reconhecido. Colunas: {sorted(linhas[0])}")
    return [{
        "ano_mes": l["ano_mes"],
        "segmento": l["segmento"],
        "modalidade_credito": l["modalidade_credito"],
        "saldo": _numero(l["saldo"]),
        "taxa_juros_aa": _numero(l["taxa_juros_aa"]),
        "spread_pp": _numero(l.get("spread_pp")),
    } for l in linhas]


def _de_bruto(corpo: dict | list) -> list[dict]:
    """Lê o JSON bruto do pipeline (registros com segmento/modalidade/medida/data/valor)."""
    registros = corpo if isinstance(corpo, list) else corpo["registros"]
    observacoes = []
    for reg in registros:
        dia, mes, ano = reg["data"].split("/")
        observacoes.append((f"{ano}-{mes}", reg["segmento"], reg["modalidade"],
                            COLUNA_MEDIDA[reg["medida"]], _numero(reg["valor"])))
    return _montar(observacoes)


def carregar(origem: str, arquivo: str | None) -> tuple[list[dict], str]:
    if arquivo:
        caminho = Path(arquivo)
        if not caminho.is_file():
            print(f"Arquivo não encontrado: {caminho}", file=sys.stderr)
            sys.exit(1)
        texto = caminho.read_text(encoding="utf-8")
        if caminho.suffix.lower() == ".json":
            return _de_bruto(json.loads(texto)), f"arquivo {caminho.name}"
        return _de_csv(texto), f"arquivo {caminho.name}"

    tentativas = {"site": ["site"], "bcb": ["bcb"], "auto": ["bcb", "site"]}[origem]
    erros = []
    for alvo in tentativas:
        try:
            if alvo == "site":
                return _de_csv(_baixar(URL_SITE).decode("utf-8")), f"site do projeto ({URL_SITE})"
            return _do_sgs(), "API SGS do Banco Central"
        except Exception as exc:  # rede bloqueada, timeout, formato inesperado
            erros.append(f"  - {alvo}: {type(exc).__name__}: {exc}")
    print("Não foi possível baixar os dados:\n" + "\n".join(erros), file=sys.stderr)
    print(
        "\nProvável bloqueio de rede no ambiente. Peça ao usuário para baixar o CSV em\n"
        f"  {URL_SITE}\n"
        "e anexá-lo à conversa; depois rode de novo com --arquivo <caminho>.",
        file=sys.stderr,
    )
    sys.exit(2)


# --- Enriquecimento ----------------------------------------------------------

def deflacionar(linhas: list[dict]) -> str | None:
    """Acrescenta `saldo_real` (R$ milhões a preços do último mês com IPCA). Retorna o mês-base."""
    try:
        serie = _baixar_json(URL_IPCA)
    except Exception as exc:
        print(f"[aviso] IPCA indisponível ({type(exc).__name__}); seguindo sem saldo_real.",
              file=sys.stderr)
        return None
    indice, acumulado = {}, 1.0
    for ponto in serie:
        dia, mes, ano = ponto["data"].split("/")
        acumulado *= 1 + float(ponto["valor"]) / 100
        indice[f"{ano}-{mes}"] = acumulado
    meses_comuns = sorted(set(indice) & {l["ano_mes"] for l in linhas})
    if not meses_comuns:
        print("[aviso] IPCA sem meses em comum com a série; seguindo sem saldo_real.",
              file=sys.stderr)
        return None
    base = meses_comuns[-1]
    for l in linhas:
        fator = indice.get(l["ano_mes"])
        if l["saldo"] is None or not fator:
            l["saldo_real"] = None
        else:
            l["saldo_real"] = round(l["saldo"] * indice[base] / fator, 2)
    return base


# --- Saída -------------------------------------------------------------------

def _fmt(n: float | None, casas: int = 0) -> str:
    if n is None:
        return "—"
    return f"{n:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resumir(linhas: list[dict], origem: str, base_ipca: str | None) -> None:
    meses = sorted({l["ano_mes"] for l in linhas})
    ultimo = meses[-1]
    combinacoes = {(l["segmento"], l["modalidade_credito"]) for l in linhas}
    print(f"Origem: {origem}")
    print(f"Período: {meses[0]} a {ultimo} ({len(meses)} meses, {len(combinacoes)} combinações "
          f"segmento x modalidade, {len(linhas)} linhas)")
    print("Unidades: saldo = R$ milhões (nominal); taxa = % ao ano; spread = p.p. ao ano")
    print("Spread: só nas linhas modalidade_credito = Total (agregado de cada segmento)")
    if base_ipca:
        print(f"saldo_real: R$ milhões a preços de {base_ipca} (IPCA, SGS 433)")

    do_mes = [l for l in linhas if l["ano_mes"] == ultimo]
    print(f"\nAgregados no último mês ({ultimo}):")
    print(f"  {'segmento':<9} {'saldo (R$ mi)':>15} {'taxa (% a.a.)':>14} {'spread (p.p.)':>14}")
    for l in sorted(do_mes, key=lambda x: x["segmento"]):
        if l["modalidade_credito"] == "Total":
            print(f"  {l['segmento']:<9} {_fmt(l['saldo']):>15} "
                  f"{_fmt(l['taxa_juros_aa'], 2):>14} {_fmt(l['spread_pp'], 2):>14}")

    for segmento in ("PF", "PJ"):
        total = next((l["saldo"] for l in do_mes
                      if l["segmento"] == segmento and l["modalidade_credito"] == "Total"), None)
        mods = [l for l in do_mes
                if l["segmento"] == segmento and l["modalidade_credito"] != "Total"
                and l["saldo"] is not None]
        if not total or not mods:
            continue
        soma = sum(l["saldo"] for l in mods)
        print(f"\n{segmento} por modalidade em {ultimo} "
              f"(detalhadas cobrem {soma / total:.1%} do saldo; o resto é 'Outras modalidades'):")
        print(f"  {'modalidade':<46} {'saldo (R$ mi)':>14} {'% seg.':>7} {'taxa (% a.a.)':>14}")
        for l in sorted(mods, key=lambda x: -x["saldo"]):
            print(f"  {l['modalidade_credito']:<46} {_fmt(l['saldo']):>14} "
                  f"{l['saldo'] / total:>7.1%} {_fmt(l['taxa_juros_aa'], 2):>14}")


def gravar(linhas: list[dict], saida: Path) -> None:
    colunas = ["ano_mes", "segmento", "modalidade_credito", *COLUNAS_MEDIDAS]
    if any("saldo_real" in l for l in linhas):
        colunas.append("saldo_real")
    with saida.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        for l in sorted(linhas, key=lambda l: (l["ano_mes"], l["segmento"], l["modalidade_credito"])):
            escritor.writerow({k: ("" if l.get(k) is None else l[k]) for k in colunas})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--origem", choices=["auto", "site", "bcb"], default="auto")
    p.add_argument("--arquivo", help="CSV (do projeto) ou JSON bruto enviado pelo usuário")
    p.add_argument("--ipca", action="store_true", help="acrescenta saldo_real deflacionado pelo IPCA")
    p.add_argument("--saida", default="credito_modalidade.csv")
    args = p.parse_args()
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8")

    linhas, origem = carregar(args.origem, args.arquivo)
    base_ipca = deflacionar(linhas) if args.ipca else None
    saida = Path(args.saida)
    gravar(linhas, saida)
    resumir(linhas, origem, base_ipca)
    print(f"\nArquivo gravado: {saida.resolve()}")


if __name__ == "__main__":
    main()
