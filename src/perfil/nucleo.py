"""Etapa E — motor genérico de perfilagem.

Mede o que está no arquivo: tipos, nulos, distintos, estatísticas, chave primária,
duplicatas, lacunas de período, órfãos de join e amostra início+fim. **Não adivinha
semântica** — `papel`, `unidade` e `descricao` vêm da `DECLARACAO` do módulo da fonte.

Este arquivo é idêntico em todas as fontes do projeto (duplicação deliberada, como o
`estilo.css`). Ao corrigir algo aqui, replique nas outras fontes.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

VERSAO_PERFIL = 1

LIMITE_TEXTO = 80        # truncamento de célula de texto na amostra
LINHAS_AMOSTRA = 25      # 25 primeiras + 25 últimas
TOP_VALORES = 10
CASAS_DECIMAIS = 4


# --- Conversão segura para JSON ----------------------------------------------

def _py(valor: Any) -> Any:
    """Converte tipos numpy/pandas para tipos nativos, com NaN -> None."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if pd.isna(valor) if not isinstance(valor, (list, dict, tuple)) else False:
        return None
    if hasattr(valor, "item"):          # numpy scalar
        valor = valor.item()
    if isinstance(valor, float):
        return round(valor, CASAS_DECIMAIS)
    if isinstance(valor, (pd.Timestamp, datetime)):
        return str(valor)
    if isinstance(valor, str) and len(valor) > LIMITE_TEXTO:
        return valor[:LIMITE_TEXTO] + "…"
    return valor


def _num(serie: pd.Series, func: str) -> Any:
    """Aplica uma estatística tolerando série vazia ou toda nula."""
    limpa = serie.dropna()
    if limpa.empty:
        return None
    return _py(getattr(limpa, func)())


# --- Perfil de coluna ---------------------------------------------------------

def _perfilar_coluna(nome: str, serie: pd.Series, decl: tuple | None) -> dict:
    papel, unidade, descricao = decl if decl else ("nao_declarado", None, None)
    n = len(serie)
    nulos = int(serie.isna().sum())
    tipo_no_arquivo = str(serie.dtype)   # antes de qualquer conversão

    # Medida entregue como texto (a API do SGS faz isso) ainda é medida: converte para
    # calcular a estatística de verdade, mas registra que o arquivo guarda string.
    armazenado_texto = False
    if papel == "medida" and not pd.api.types.is_numeric_dtype(serie):
        convertida = pd.to_numeric(serie, errors="coerce")
        preenchidos = int(serie.notna().sum())
        if preenchidos and int(convertida.notna().sum()) >= 0.9 * preenchidos:
            serie, armazenado_texto = convertida, True

    col: dict[str, Any] = {
        "nome": nome,
        "tipo": tipo_no_arquivo,
        "papel": papel,
        "unidade": unidade,
        "descricao": descricao,
        "nulos": nulos,
        "pct_nulos": round(100 * nulos / n, 2) if n else 0.0,
        "distintos": int(serie.nunique(dropna=True)),
    }
    if armazenado_texto:
        col["armazenado_como_texto"] = True

    if pd.api.types.is_numeric_dtype(serie) and papel != "data":
        limpa = serie.dropna()
        col.update({
            "min": _num(serie, "min"), "max": _num(serie, "max"),
            "media": _num(serie, "mean"), "mediana": _num(serie, "median"),
            "desvio": _num(serie, "std"),
            "p05": _py(limpa.quantile(0.05)) if not limpa.empty else None,
            "p95": _py(limpa.quantile(0.95)) if not limpa.empty else None,
            "zeros": int((limpa == 0).sum()),
            "negativos": int((limpa < 0).sum()),
        })
    elif papel == "data":
        # dropna antes do min/max: coluna de data com nulos vira object com str + NaN,
        # e comparar float com str estoura.
        limpa = serie.dropna()
        col.update({
            "min_data": _py(limpa.min()) if not limpa.empty else None,
            "max_data": _py(limpa.max()) if not limpa.empty else None,
        })
        contagem = serie.value_counts().head(TOP_VALORES)
        col["top_valores"] = [
            {"valor": _py(v), "n": int(q), "pct": round(100 * q / n, 2)}
            for v, q in contagem.items()
        ]
    else:
        contagem = serie.value_counts().head(TOP_VALORES)
        col["top_valores"] = [
            {"valor": _py(v), "n": int(q), "pct": round(100 * q / n, 2)}
            for v, q in contagem.items()
        ]
        texto = serie.dropna().astype(str)
        if not texto.empty:
            col["tamanho_min"] = int(texto.str.len().min())
            col["tamanho_max"] = int(texto.str.len().max())

    return col


# --- Amostra início + fim -----------------------------------------------------

def _amostra(df: pd.DataFrame, n: int = LINHAS_AMOSTRA) -> dict:
    def linhas(bloco: pd.DataFrame) -> list[list]:
        return [[_py(v) for v in reg] for reg in bloco.itertuples(index=False, name=None)]

    if len(df) <= 2 * n:
        return {"cabecalho": list(df.columns), "inicio": linhas(df), "fim": [], "omitidas": 0}
    return {
        "cabecalho": list(df.columns),
        "inicio": linhas(df.head(n)),
        "fim": linhas(df.tail(n)),
        "omitidas": len(df) - 2 * n,
    }


# --- Alertas automáticos ------------------------------------------------------

def _alertas(df: pd.DataFrame, colunas: list[dict], chave_ok: bool, dups: int) -> list[str]:
    saida: list[str] = []
    if not chave_ok:
        saida.append(f"chave primária declarada NÃO é única: {dups} combinações repetidas")
    for c in colunas:
        if c.get("armazenado_como_texto"):
            saida.append(f"coluna `{c['nome']}` é medida mas está guardada como texto "
                         f"({c['tipo']}) — a conversão para número acontece adiante no pipeline")
        if c["papel"] == "nao_declarado":
            saida.append(f"coluna `{c['nome']}` existe no arquivo mas não está na DECLARACAO")
        if c["pct_nulos"] == 100.0:
            saida.append(f"coluna `{c['nome']}` está 100% nula")
        elif c["pct_nulos"] > 0:
            saida.append(f"coluna `{c['nome']}`: {c['pct_nulos']}% de valores nulos")
        if c["distintos"] == 1 and len(df):
            saida.append(f"coluna `{c['nome']}` é constante (um único valor em toda a tabela)")
        zeros = c.get("zeros")
        if zeros and len(df) and zeros / len(df) > 0.3:
            pct = round(100 * zeros / len(df), 1)
            saida.append(f"coluna `{c['nome']}`: {pct}% dos valores são zero")
    return saida


# --- Perfil de tabela ---------------------------------------------------------

def perfilar_tabela(
    df: pd.DataFrame,
    *,
    id: str,
    camada: str,
    nome: str,
    arquivo: str,
    formato: str,
    origem: str,
    declaracao: dict,
    alertas_extra: list[str] | None = None,
) -> dict:
    """Perfila um DataFrame. `declaracao` traz granularidade, chave_primaria e colunas."""
    decl_cols: dict[str, tuple] = declaracao.get("colunas", {})
    chave: list[str] = declaracao.get("chave_primaria", [])

    colunas = [_perfilar_coluna(c, df[c], decl_cols.get(c)) for c in df.columns]

    dups = 0
    chave_ok = True
    if chave and all(c in df.columns for c in chave):
        dups = int(df.duplicated(subset=chave).sum())
        chave_ok = dups == 0
    elif chave:
        chave_ok = False

    faltando = [c for c in decl_cols if c not in df.columns]
    extras = list(alertas_extra or [])
    extras += [f"coluna `{c}` está declarada mas não existe no arquivo" for c in faltando]

    return {
        "id": id,
        "camada": camada,
        "nome": nome,
        "arquivo": arquivo,
        "formato": formato,
        "origem": origem,
        "n_linhas": int(len(df)),
        "n_colunas": int(len(df.columns)),
        "granularidade": declaracao.get("granularidade"),
        "chave_primaria": chave,
        "chave_primaria_valida": chave_ok,
        "duplicatas": dups,
        "colunas": colunas,
        "amostra": _amostra(df),
        "alertas": _alertas(df, colunas, chave_ok, dups) + extras,
    }


# --- Cobertura temporal -------------------------------------------------------

def cobertura_temporal(df: pd.DataFrame, coluna: str = "ano_mes") -> dict:
    """Detecta lacunas numa série mensal de strings 'YYYY-MM'."""
    meses = sorted(df[coluna].dropna().astype(str).unique())
    if not meses:
        return {"inicio": None, "fim": None, "meses_esperados": 0,
                "meses_presentes": 0, "lacunas": []}

    grade = pd.period_range(meses[0], meses[-1], freq="M").astype(str).tolist()
    presentes = set(meses)
    lacunas = [m for m in grade if m not in presentes]
    return {
        "inicio": meses[0],
        "fim": meses[-1],
        "meses_esperados": len(grade),
        "meses_presentes": len(presentes),
        "lacunas": lacunas,
    }


# --- Relacionamentos ----------------------------------------------------------

def relacionamento(
    df_de: pd.DataFrame, col_de: str,
    df_para: pd.DataFrame, col_para: str,
    *, cardinalidade: str, uso: str,
) -> dict:
    """Mede um join de fato: cobertura e órfãos, em vez de declará-lo no papel."""
    esq = df_de[col_de].dropna().astype(str)
    dir_ = set(df_para[col_para].dropna().astype(str))
    orfaos = int((~esq.isin(dir_)).sum())
    total = len(esq)
    return {
        "de": col_de,
        "para": col_para,
        "tabela_de": None,      # preenchido pelo módulo da fonte
        "tabela_para": None,
        "cardinalidade": cardinalidade,
        "cobertura_pct": round(100 * (total - orfaos) / total, 2) if total else 0.0,
        "orfaos": orfaos,
        "uso": uso,
    }


def liga(rel: dict, tabela_de: str, tabela_para: str) -> dict:
    rel["tabela_de"], rel["tabela_para"] = tabela_de, tabela_para
    return rel


# --- Escrita ------------------------------------------------------------------

def montar(slug: str, fonte_nome: str, tabelas: list[dict],
           relacionamentos: list[dict], cobertura: dict) -> dict:
    return {
        "meta": {
            "slug": slug,
            "fonte": fonte_nome,
            "gerado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "versao_perfil": VERSAO_PERFIL,
        },
        "tabelas": tabelas,
        "relacionamentos": relacionamentos,
        "cobertura_temporal": cobertura,
    }


def salvar(perfil: dict, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(perfil, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    kb = destino.stat().st_size / 1024
    print(f"[perfil] {len(perfil['tabelas'])} tabelas perfiladas -> {destino} ({kb:.0f} KB)")
    if kb > 300:
        print(f"[perfil] AVISO: {kb:.0f} KB acima do teto de 300 KB da Etapa E.")
    return destino
