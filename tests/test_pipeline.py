"""Pipeline Etapas 2 -> 3 -> E -> 5 contra a fixture do SGS (rede trocada por mock)."""
from __future__ import annotations

import unittest

import pandas as pd

import run_pipeline
from src import config
from src.analise import credito_modalidade as analise
from src.coleta import credito_modalidade as coleta
from src.perfil import credito_modalidade as perfil
from src.publicacao import credito_modalidade as publicacao
from src.tratamento import credito_modalidade as tratamento

from tests import helpers
from tests.helpers import SLUG, RespostaFalsa, ambiente_isolado, api_falsa, sem_saida

SERIES = config.series_sgs(config.fonte())
N_COMBINACOES = sum(len(m) for m in config.fonte()["series"].values())   # segmento x modalidade
N_MESES = 14
MES_INI, MES_FIM = "2025-01", "2026-02"


def _coletar_e_tratar():
    with sem_saida(), api_falsa():
        coleta.coletar()
    with sem_saida():
        return tratamento.tratar()


class TestColeta(unittest.TestCase):
    def test_uma_requisicao_por_serie_com_url_e_data_inicial(self):
        with ambiente_isolado(), api_falsa() as falso, sem_saida():
            registros = coleta.coletar()
            envelope = helpers.ler_json(config.DIR_BRUTOS / f"{SLUG}.json")
        self.assertEqual(len(falso.chamadas), len(SERIES))
        codigos = {int(helpers.RE_CODIGO.search(u).group(1)) for u in falso.chamadas}
        self.assertEqual(codigos, {c for *_, c in SERIES})
        for u in falso.chamadas:
            self.assertTrue(u.startswith("https://api.bcb.gov.br/dados/serie/bcdata.sgs."))
            self.assertIn("formato=json&dataInicial=01/03/2011", u)
        self.assertEqual(len(registros), len(SERIES) * N_MESES)
        self.assertEqual(envelope["total_registros"], len(registros))
        self.assertEqual(envelope["fonte"], config.fonte()["nome"])
        self.assertTrue(envelope["coletado_em"])

    def test_registros_anotados_com_segmento_modalidade_medida(self):
        with ambiente_isolado(), api_falsa(), sem_saida():
            registros = coleta.coletar()
        r = next(x for x in registros if x["codigo_sgs"] == 20539)
        self.assertEqual((r["segmento"], r["modalidade"], r["medida"]), ("Total", "Total", "saldo"))
        self.assertEqual(set(r), {"segmento", "modalidade", "medida", "codigo_sgs", "data", "valor"})
        self.assertEqual(r["data"], "01/01/2025")
        self.assertEqual(r["valor"], "1000000")

    def test_bloqueio_html_tenta_de_novo_e_recupera(self):
        falhas = {20539: lambda n: RespostaFalsa(None, json_invalido=True) if n < 3
                  else RespostaFalsa(helpers.corpo_do_codigo(20539))}
        with ambiente_isolado(), api_falsa(falhas_por_codigo=falhas) as falso, sem_saida():
            registros = coleta.coletar()
        self.assertEqual(len(registros), len(SERIES) * N_MESES)
        self.assertEqual(sum(1 for u in falso.chamadas if "sgs.20539/" in u), 3)

    def test_falha_persistente_levanta_e_nao_sobrescreve_o_bruto(self):
        with ambiente_isolado(), sem_saida():
            with api_falsa():
                coleta.coletar()
            antes = (config.DIR_BRUTOS / f"{SLUG}.json").read_text(encoding="utf-8")
            with api_falsa(falhas_por_codigo={20541: lambda n: RespostaFalsa({}, status=503)}) as falso:
                with self.assertRaises(RuntimeError) as ctx:
                    coleta.coletar()
                self.assertIn("20541", str(ctx.exception))
                self.assertEqual(sum(1 for u in falso.chamadas if "sgs.20541/" in u), coleta.TENTATIVAS)
            depois = (config.DIR_BRUTOS / f"{SLUG}.json").read_text(encoding="utf-8")
        self.assertEqual(antes, depois)


class TestTratamento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._amb = ambiente_isolado()
        cls._amb.__enter__()
        cls.tidy = _coletar_e_tratar()
        cls.csv = (config.DIR_PROCESSADOS / f"{SLUG}.csv").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._amb.__exit__(None, None, None)

    def test_colunas_e_forma(self):
        self.assertEqual(list(self.tidy.columns), tratamento.COLUNAS)
        self.assertEqual(len(self.tidy), N_MESES * N_COMBINACOES)
        self.assertFalse(self.tidy.duplicated(["ano_mes", "segmento", "modalidade_credito"]).any())
        self.assertEqual(self.tidy["ano_mes"].min(), MES_INI)
        self.assertEqual(self.tidy["ano_mes"].max(), MES_FIM)

    def test_valores_viram_numero(self):
        linha = self.tidy[(self.tidy.ano_mes == MES_INI) & (self.tidy.segmento == "Total")].iloc[0]
        self.assertEqual(linha["saldo"], 1000000.0)
        self.assertAlmostEqual(linha["taxa_juros_aa"], 20.0)
        self.assertAlmostEqual(linha["spread_pp"], 10.0)

    def test_spread_so_nas_linhas_total(self):
        com_spread = self.tidy[self.tidy["spread_pp"].notna()]
        self.assertEqual(set(com_spread["modalidade_credito"]), {"Total"})
        det = self.tidy[self.tidy["modalidade_credito"] != "Total"]
        self.assertTrue(det["spread_pp"].isna().all())

    def test_ordem_segue_o_config(self):
        mes = self.tidy[self.tidy.ano_mes == MES_INI]
        esperado = [(s, m) for s, mods in config.fonte()["series"].items() for m in mods]
        self.assertEqual(list(zip(mes["segmento"], mes["modalidade_credito"])), esperado)
        self.assertEqual(list(self.tidy["ano_mes"]), sorted(self.tidy["ano_mes"]))

    def test_csv_gravado_em_utf8_com_cabecalho(self):
        self.assertEqual(self.csv.splitlines()[0], ",".join(tratamento.COLUNAS))
        self.assertIn("Crédito pessoal consignado", self.csv)


class TestTratamentoBordas(unittest.TestCase):
    def test_sem_bruto_pede_a_coleta(self):
        with ambiente_isolado(), sem_saida():
            with self.assertRaises(FileNotFoundError) as ctx:
                tratamento.tratar()
        self.assertIn("coleta", str(ctx.exception))

    def test_valor_nao_numerico_vira_nulo(self):
        fx = helpers.fixture_sgs()
        fx["por_codigo"]["20539"][3]["valor"] = ""
        with ambiente_isolado(), sem_saida():
            with api_falsa(fx):
                coleta.coletar()
            tidy = tratamento.tratar()
        linha = tidy[(tidy.ano_mes == "2025-04") & (tidy.segmento == "Total")].iloc[0]
        self.assertTrue(pd.isna(linha["saldo"]))
        self.assertEqual(len(tidy), N_MESES * N_COMBINACOES)

    def test_serie_de_spread_vazia_nao_derruba_o_tratamento(self):
        fx = helpers.fixture_sgs()
        fx["padrao"]["spread"] = []
        for cod in ("20783",):
            fx["por_codigo"][cod] = []
        with ambiente_isolado(), sem_saida():
            with api_falsa(fx):
                coleta.coletar()
            tidy = tratamento.tratar()
        self.assertIn("spread_pp", tidy.columns)
        total = tidy[(tidy.segmento == "Total")]
        self.assertTrue(total["spread_pp"].isna().all())
        self.assertTrue(total["saldo"].notna().all())


class TestAnalise(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._amb = ambiente_isolado()
        cls._amb.__enter__()
        _coletar_e_tratar()
        cls.r = analise.analisar()

    @classmethod
    def tearDownClass(cls):
        cls._amb.__exit__(None, None, None)

    def test_estrutura_e_alinhamento(self):
        r = self.r
        self.assertEqual(r["labels"][0], MES_INI)
        self.assertEqual(len(r["labels"]), N_MESES)
        self.assertEqual(r["segmentos"], list(config.fonte()["series"]))
        for seg in r["segmentos"]:
            self.assertEqual(set(r["series"][seg]), set(config.fonte()["series"][seg]))
            for mod, s in r["series"][seg].items():
                self.assertEqual(len(s["saldo"]), N_MESES, (seg, mod))
                self.assertEqual(len(s["taxa"]), N_MESES, (seg, mod))
        self.assertEqual(len(r["series"]["Total"]["Total"]["spread"]), N_MESES)
        self.assertEqual(r["rotulo_residuo"], "Outras modalidades")

    def test_yoy_do_saldo_total(self):
        # saldo Total: 1.000.000 + 10.000*i  ->  i=13 (1.130.000) contra i=1 (1.010.000)
        esperado = (1130000 / 1010000 - 1) * 100
        self.assertAlmostEqual(self.r["kpis"]["totais"]["yoy_saldo_total_pct"], esperado, places=6)

    def test_cagr_e_yoy_por_modalidade(self):
        # modalidades usam o padrão: saldo 10.000 + 100*i ; taxa 30 + 0,5*i
        m = next(x for x in self.r["kpis"]["por_modalidade"]
                 if x["segmento"] == "PF" and x["modalidade"] == "Cheque especial")
        self.assertAlmostEqual(m["yoy_saldo_pct"], (11300 / 10100 - 1) * 100, places=6)
        anos = 13 / 12
        self.assertAlmostEqual(m["cagr_saldo_aa_pct"], ((11300 / 10000) ** (1 / anos) - 1) * 100, places=6)
        self.assertAlmostEqual(m["var_taxa_12m_pp"], 36.5 - 30.5, places=6)
        self.assertAlmostEqual(m["taxa_ultima"], 36.5)
        self.assertAlmostEqual(m["part_saldo_segmento_pct"], 11300 / 665000 * 100, places=6)

    def test_funcoes_puras(self):
        s = pd.Series([100.0, 110.0, 121.0])
        self.assertAlmostEqual(analise._cagr_aa(s, meses_por_ano=1), 10.0)
        self.assertIsNone(analise._cagr_aa(pd.Series([5.0])))
        self.assertIsNone(analise._cagr_aa(pd.Series([0.0, 0.0, 3.0])))
        self.assertIsNone(analise._yoy_pct(pd.Series(range(1, 13), dtype=float)))
        doze = pd.Series([50.0] + [0.0] * 11 + [100.0])
        self.assertAlmostEqual(analise._yoy_pct(doze), 100.0)
        self.assertIsNone(analise._yoy_pct(pd.Series([0.0] + [1.0] * 12)))
        self.assertAlmostEqual(analise._var_12m_pp(pd.Series([1.0] * 12 + [3.5])), 2.5)
        d = analise._desc(pd.Series([1.0, 2.0, 3.0, None]))
        self.assertEqual((d["media"], d["mediana"], d["minimo"], d["maximo"]), (2.0, 2.0, 1.0, 3.0))
        self.assertAlmostEqual(d["desvio_padrao"], 1.0)
        self.assertIsNone(analise._desc(pd.Series([], dtype=float))["media"])

    def test_residuo_fecha_com_o_saldo_do_segmento(self):
        for seg in ("PF", "PJ"):
            res = self.r["residuos"][seg]["saldo"]
            total = self.r["series"][seg]["Total"]["saldo"]
            det = [sum(self.r["series"][seg][m]["saldo"][i] for m in self.r["modalidades"][seg])
                   for i in range(N_MESES)]
            for i in range(N_MESES):
                self.assertAlmostEqual(res[i] + det[i], total[i], places=6)
        self.assertNotIn("Total", self.r["residuos"])

    def test_rankings_e_totais(self):
        t = self.r["kpis"]["totais"]
        self.assertEqual(t["mes_ref"], MES_FIM)
        self.assertEqual(t["meses_cobertos"], N_MESES)
        self.assertEqual(t["saldo_total"], 1130000.0)
        self.assertEqual(t["saldo_pf"], 665000.0)
        self.assertEqual(t["saldo_pj"], 465000.0)
        self.assertAlmostEqual(t["taxa_media_aa"], 21.3)
        self.assertAlmostEqual(t["spread_medio_pp"], 10.65)
        saldos = [m["saldo_ultimo"] for m in self.r["kpis"]["por_modalidade"]]
        self.assertEqual(saldos, sorted(saldos, reverse=True))
        self.assertEqual(len(saldos), N_COMBINACOES - 3)       # sem as 3 linhas Total
        self.assertLessEqual(t["mais_barata"]["taxa_ultima"], t["mais_cara"]["taxa_ultima"])

    def test_sem_processado_pede_o_tratamento(self):
        with ambiente_isolado():
            with self.assertRaises(FileNotFoundError) as ctx:
                analise.analisar()
        self.assertIn("tratamento", str(ctx.exception))


class TestPipelineCompleto(unittest.TestCase):
    def test_ponta_a_ponta_em_pasta_temporaria(self):
        antes = sorted(p.name for p in helpers.DADOS_PUB.iterdir())
        with ambiente_isolado() as raiz, api_falsa() as falso, sem_saida():
            run_pipeline.rodar()
            pub = raiz / "docs" / "dados"
            self.assertEqual(len(falso.chamadas), len(SERIES))
            nomes = {p.name for p in pub.iterdir()}
            self.assertLessEqual({f"{SLUG}.json", f"perfil_{SLUG}.json"}, nomes)
            pacote = helpers.ler_json(pub / f"{SLUG}.json")
            perf = helpers.ler_json(pub / f"perfil_{SLUG}.json")
            self.assertTrue((raiz / "dados" / "brutos" / f"{SLUG}.json").exists())
            self.assertTrue((raiz / "dados" / "processados" / f"{SLUG}.csv").exists())
        self.assertEqual(pacote["meta"]["periodo"], {"inicio": MES_INI, "fim": MES_FIM})
        self.assertEqual(pacote["meta"]["series_sgs"], len(SERIES))
        self.assertEqual(pacote["meta"]["url"], config.fonte()["url_portal"])
        self.assertEqual([t["id"] for t in perf["tabelas"]], ["bruto", "tidy", "aux_series", "aux_modalidades"])
        self.assertTrue(all(t["chave_primaria_valida"] for t in perf["tabelas"]))
        self.assertTrue(all(r["orfaos"] == 0 for r in perf["relacionamentos"]))
        self.assertEqual(perf["cobertura_temporal"]["lacunas"], [])
        # o repo real não foi tocado
        self.assertEqual(antes, sorted(p.name for p in helpers.DADOS_PUB.iterdir()))

    def test_flag_sem_coleta_nao_chama_a_api(self):
        with ambiente_isolado() as raiz, sem_saida():
            with api_falsa():
                run_pipeline.rodar()
            with api_falsa() as falso:
                run_pipeline.rodar(sem_coleta=True)
                self.assertEqual(falso.chamadas, [])
            self.assertTrue((raiz / "docs" / "dados" / f"{SLUG}.json").exists())

    def test_flag_sem_perfil_nao_gera_perfil(self):
        with ambiente_isolado() as raiz, api_falsa(), sem_saida():
            run_pipeline.rodar(sem_perfil=True)
            nomes = {p.name for p in (raiz / "docs" / "dados").iterdir()}
        self.assertIn(f"{SLUG}.json", nomes)
        self.assertNotIn(f"perfil_{SLUG}.json", nomes)

    def test_perfil_declara_as_colunas_do_tidy_e_do_bruto(self):
        self.assertEqual(set(perfil.DECLARACAO["tidy"]["colunas"]), set(tratamento.COLUNAS))
        self.assertEqual(set(perfil.DECLARACAO["bruto"]["colunas"]),
                         {"segmento", "modalidade", "medida", "codigo_sgs", "data", "valor"})

    def test_publicar_sem_dados_pede_as_etapas_anteriores(self):
        with ambiente_isolado():
            with self.assertRaises(FileNotFoundError):
                publicacao.publicar()


if __name__ == "__main__":
    unittest.main()
