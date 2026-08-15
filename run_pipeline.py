"""Orquestrador do pipeline — executa as Etapas 2 → E → 5 da fonte deste repositório.

Uso:
    python run_pipeline.py                # pipeline completo
    python run_pipeline.py --sem-coleta   # reusa o bruto já baixado
"""
from __future__ import annotations

import argparse

from src import config
from src.coleta import credito_modalidade as coleta
from src.tratamento import credito_modalidade as tratamento
from src.perfil import credito_modalidade as perfil
from src.publicacao import credito_modalidade as publicacao


def rodar(sem_coleta: bool = False, sem_perfil: bool = False) -> None:
    print(f"=== Pipeline: {config.fonte()['nome']} ===")

    if sem_coleta:
        print("[pipeline] Etapa 2 (coleta) pulada — reusando bruto existente.")
    else:
        coleta.coletar(config.SLUG)

    tratamento.tratar(config.SLUG)

    # Etapa E — perfil das tabelas. Sobrescreve só perfil_<slug>.json;
    # notas_<slug>.json é escrito à mão e nenhum código toca nele.
    if sem_perfil:
        print("[pipeline] Etapa E (perfil) pulada.")
    else:
        perfil.perfilar(config.SLUG)

    publicacao.publicar(config.SLUG)
    print("=== Pipeline concluído com sucesso ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline da fonte credito_modalidade.")
    parser.add_argument("--sem-coleta", action="store_true",
                        help="Não consulta a API do SGS; reusa o bruto já salvo.")
    parser.add_argument("--sem-perfil", action="store_true",
                        help="Pula a Etapa E (perfil das tabelas).")
    args = parser.parse_args()
    rodar(sem_coleta=args.sem_coleta, sem_perfil=args.sem_perfil)


if __name__ == "__main__":
    main()
