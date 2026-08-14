"""Etapa 4 — Análise estatística da fonte Crédito por modalidade (SGS).

Consome o CSV tidy da Etapa 3 e produz:

- séries mensais de saldo e taxa por segmento×modalidade (e spread nas linhas "Total");
- participação (%) de cada modalidade no saldo do segmento, com o resíduo das
  modalidades não coletadas explicitado como "Outras modalidades";
- crescimento interanual (YoY) e CAGR do saldo, variação da taxa em 12 meses;
- rankings por volume (saldo) e por custo (taxa);
- estatística descritiva das séries.

Retorna um dicionário serializável, usado pela Etapa 5 (publicação).
"""
from __future__ import annotations

import pandas as pd

from src import config

SLUG = "credito_modalidade"

# Linha agregada de cada segmento (é ela que traz o spread publicado pelo BCB).
AGREGADO = "Total"
# Rótulo do resíduo: saldo do segmento menos as modalidades detalhadas aqui.
RESIDUO = "Outras modalidades"


def _carregar_tidy(slug: str) -> pd.DataFrame:
    caminho = config.DIR_PROCESSADOS / f"{slug}.csv"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Processado ausente: {caminho}. Rode a Etapa 3 (tratamento) antes da análise."
        )
    return pd.read_csv(caminho, dtype={"ano_mes": str})


def _lista(serie: pd.Series) -> list[float | None]:
    """Série -> lista JSON-serializável (NaN vira None)."""
    return [None if pd.isna(v) else float(v) for v in serie]


def _num(valor) -> float | None:
    return None if pd.isna(valor) else float(valor)


def _cagr_aa(serie: pd.Series, meses_por_ano: int = 12) -> float | None:
    """CAGR anual entre o primeiro e o último valor positivo da série (ordenada asc)."""
    positivos = serie[serie > 0]
    if len(positivos) < 2:
        return None
    v0, vn = positivos.iloc[0], positivos.iloc[-1]
    anos = (positivos.index[-1] - positivos.index[0]) / meses_por_ano
    if anos <= 0 or v0 <= 0:
        return None
    return ((vn / v0) ** (1 / anos) - 1) * 100


def _yoy_pct(serie: pd.Series) -> float | None:
    """Variação percentual do último mês contra o mesmo mês do ano anterior."""
    if len(serie) < 13:
        return None
    atual, anterior = serie.iloc[-1], serie.iloc[-13]
    if pd.isna(atual) or pd.isna(anterior) or anterior == 0:
        return None
    return (atual / anterior - 1) * 100


def _var_12m_pp(serie: pd.Series) -> float | None:
    """Variação da taxa em pontos percentuais no último mês vs. 12 meses antes."""
    if len(serie) < 13:
        return None
    atual, anterior = serie.iloc[-1], serie.iloc[-13]
    if pd.isna(atual) or pd.isna(anterior):
        return None
    return float(atual - anterior)


def _desc(serie: pd.Series) -> dict:
    """Estatística descritiva básica de uma série."""
    s = serie.dropna()
    media = float(s.mean()) if len(s) else None
    desvio = float(s.std()) if len(s) > 1 else None
    return {
        "media": media,
        "mediana": float(s.median()) if len(s) else None,
        "desvio_padrao": desvio,
        "coef_variacao_pct": (desvio / media * 100) if (media and desvio) else None,
        "minimo": float(s.min()) if len(s) else None,
        "maximo": float(s.max()) if len(s) else None,
    }


def analisar(slug: str = SLUG) -> dict:
    """Calcula todas as métricas e devolve um dicionário serializável."""
    cfg = config.fonte(slug)
    df = _carregar_tidy(slug)

    meses = sorted(df["ano_mes"].unique())
    # Ordem declarada em config.py (não alfabética).
    segmentos = list(cfg["series"])
    modalidades = {
        seg: [m for m in cfg["series"][seg] if m != AGREGADO] for seg in segmentos
    }

    series: dict[str, dict] = {}
    estatisticas: dict[str, dict] = {}
    por_modalidade: list[dict] = []
    residuos: dict[str, dict] = {}

    for seg in segmentos:
        series[seg] = {}
        estatisticas[seg] = {}
        # Reindexa pelos meses para que todas as séries tenham o mesmo comprimento
        # (e o mesmo alinhamento) que `meses` — o front consome tudo por índice.
        do_seg = df[df["segmento"] == seg]
        por_mod = {
            mod: g.set_index("ano_mes").reindex(meses).reset_index()
            for mod, g in do_seg.groupby("modalidade_credito", sort=False)
        }

        agregado = por_mod[AGREGADO]
        saldo_seg = agregado["saldo"]
        series[seg][AGREGADO] = {
            "saldo": _lista(saldo_seg),
            "taxa": _lista(agregado["taxa_juros_aa"]),
            "spread": _lista(agregado["spread_pp"]),
        }
        estatisticas[seg][AGREGADO] = {
            "saldo": _desc(saldo_seg),
            "taxa": _desc(agregado["taxa_juros_aa"]),
        }

        saldo_detalhado = pd.Series(0.0, index=range(len(meses)))
        for mod in modalidades[seg]:
            g = por_mod[mod]
            saldo, taxa = g["saldo"], g["taxa_juros_aa"]
            saldo_detalhado += saldo.fillna(0)

            saldo_ult, saldo_seg_ult = saldo.iloc[-1], saldo_seg.iloc[-1]
            por_modalidade.append({
                "segmento": seg,
                "modalidade": mod,
                "saldo_ultimo": _num(saldo_ult),
                "part_saldo_segmento_pct": (
                    float(saldo_ult / saldo_seg_ult * 100)
                    if not pd.isna(saldo_ult) and saldo_seg_ult else None
                ),
                "taxa_ultima": _num(taxa.iloc[-1]),
                "taxa_media_periodo": _desc(taxa)["media"],
                "var_taxa_12m_pp": _var_12m_pp(taxa),
                "yoy_saldo_pct": _yoy_pct(saldo),
                "cagr_saldo_aa_pct": _cagr_aa(saldo),
            })
            series[seg][mod] = {"saldo": _lista(saldo), "taxa": _lista(taxa)}
            estatisticas[seg][mod] = {"saldo": _desc(saldo), "taxa": _desc(taxa)}

        # Resíduo: modalidades do segmento que não estão detalhadas nesta fonte.
        if modalidades[seg]:
            residuo = saldo_seg.reset_index(drop=True) - saldo_detalhado
            residuos[seg] = {
                "saldo": _lista(residuo),
                "saldo_ultimo": _num(residuo.iloc[-1]),
                "part_saldo_segmento_pct": (
                    float(residuo.iloc[-1] / saldo_seg.iloc[-1] * 100)
                    if saldo_seg.iloc[-1] else None
                ),
            }

    total = series["Total"][AGREGADO]
    detalhadas = [m for m in por_modalidade if m["saldo_ultimo"] is not None]
    maior_saldo = max(detalhadas, key=lambda m: m["saldo_ultimo"])
    com_taxa = [m for m in detalhadas if m["taxa_ultima"] is not None]
    mais_cara = max(com_taxa, key=lambda m: m["taxa_ultima"])
    mais_barata = min(com_taxa, key=lambda m: m["taxa_ultima"])

    # Ranking por saldo do último mês (desc), estável para a tabela do dashboard.
    por_modalidade.sort(key=lambda m: (m["saldo_ultimo"] or 0), reverse=True)

    return {
        "labels": meses,
        "segmentos": segmentos,
        "rotulos_segmento": cfg["segmentos"],
        "modalidades": modalidades,
        "rotulo_residuo": RESIDUO,
        "series": series,
        "residuos": residuos,
        "kpis": {
            "por_modalidade": por_modalidade,
            "totais": {
                "mes_ref": meses[-1],
                "meses_cobertos": len(meses),
                "saldo_total": total["saldo"][-1],
                "taxa_media_aa": total["taxa"][-1],
                "spread_medio_pp": total["spread"][-1],
                "saldo_pf": series["PF"][AGREGADO]["saldo"][-1],
                "saldo_pj": series["PJ"][AGREGADO]["saldo"][-1],
                "yoy_saldo_total_pct": _yoy_pct(
                    pd.Series(total["saldo"], dtype="float64")
                ),
                "maior_saldo": maior_saldo,
                "mais_cara": mais_cara,
                "mais_barata": mais_barata,
            },
        },
        "estatisticas": estatisticas,
    }


if __name__ == "__main__":
    import json

    resultado = analisar()
    print(json.dumps(resultado["kpis"]["totais"], ensure_ascii=False, indent=2))
