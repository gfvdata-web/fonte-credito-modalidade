"""Catálogo de séries: registro em src/config.py x dicionário em catalogo/fonte.md x declarações do perfil."""
from __future__ import annotations

import re
import unittest
from urllib.parse import urlparse

from src import config
from src.perfil import credito_modalidade as perfil

from tests.helpers import RAIZ, SLUG, ler_texto

FONTE_MD = ler_texto(RAIZ / "catalogo" / "fonte.md")
CFG = config.fonte()
SERIES = config.series_sgs(CFG)


class TestRegistroDaFonte(unittest.TestCase):
    def test_slug_registrado(self):
        self.assertIn(config.SLUG, config.FONTES)
        self.assertEqual(config.SLUG, SLUG)
        self.assertRegex(config.SLUG, r"^[a-z0-9_]+$")

    def test_campos_obrigatorios(self):
        for campo in ("nome", "descricao", "url", "url_portal", "data_inicial", "segmentos", "series",
                      "unidades", "periodicidade", "licenca"):
            self.assertTrue(CFG.get(campo), f"falta {campo}")
        self.assertEqual(set(CFG["unidades"]), {"saldo", "taxa_juros_aa", "spread_pp"})
        self.assertEqual(CFG["periodicidade"], "mensal")

    def test_url_do_sgs_bem_formada(self):
        u = urlparse(CFG["url"].format(codigo=20539))
        self.assertEqual((u.scheme, u.netloc), ("https", "api.bcb.gov.br"))
        self.assertEqual(u.path, "/dados/serie/bcdata.sgs.20539/dados")
        self.assertEqual(CFG["url"], config.BCB_SGS_URL)
        self.assertEqual(urlparse(CFG["url_portal"]).scheme, "https")

    def test_data_inicial_dd_mm_aaaa(self):
        self.assertRegex(CFG["data_inicial"], r"^01/\d{2}/\d{4}$")

    def test_segmentos_e_series_coerentes(self):
        self.assertEqual(set(CFG["segmentos"]), set(CFG["series"]))
        self.assertEqual(list(CFG["series"]), ["Total", "PF", "PJ"])
        for seg, mods in CFG["series"].items():
            self.assertIn("Total", mods, seg)
            for mod, medidas in mods.items():
                self.assertLessEqual({"saldo", "taxa"}, set(medidas), (seg, mod))
                self.assertLessEqual(set(medidas), {"saldo", "taxa", "spread"}, (seg, mod))
                if mod != "Total":
                    self.assertNotIn("spread", medidas, f"{seg}/{mod}: o BCB não publica spread por modalidade")
                else:
                    self.assertIn("spread", medidas, seg)

    def test_codigos_sgs_inteiros_e_unicos(self):
        codigos = [c for *_, c in SERIES]
        self.assertEqual(len(codigos), 61)
        self.assertEqual(len(codigos), len(set(codigos)), "código SGS repetido")
        self.assertTrue(all(isinstance(c, int) and 1000 < c < 99999 for c in codigos))

    def test_series_sgs_achata_na_ordem_do_config(self):
        self.assertEqual(SERIES[0], ("Total", "Total", "saldo", 20539))
        self.assertEqual(len({(s, m, me) for s, m, me, _ in SERIES}), len(SERIES))

    def test_pastas_de_dados_ficam_dentro_do_repo(self):
        for pasta in (config.DIR_BRUTOS, config.DIR_PROCESSADOS, config.DIR_PUBLICADOS):
            self.assertTrue(pasta.is_relative_to(config.RAIZ))
        self.assertEqual(config.DIR_PUBLICADOS, RAIZ / "docs" / "dados")

    def test_erro_de_slug_lista_os_disponiveis(self):
        with self.assertRaises(KeyError) as ctx:
            config.fonte("outra")
        self.assertIn(SLUG, str(ctx.exception))

    def test_modulos_das_etapas_usam_o_mesmo_slug(self):
        from src.analise import credito_modalidade as an
        from src.coleta import credito_modalidade as co
        from src.publicacao import credito_modalidade as pu
        from src.tratamento import credito_modalidade as tr
        for m in (an, co, pu, tr, perfil):
            self.assertEqual(m.SLUG, SLUG, m.__name__)


class TestDicionarioDeDados(unittest.TestCase):
    """catalogo/fonte.md (Etapa 1) deve descrever o que o código realmente usa."""

    def test_menciona_slug_endpoint_e_licenca(self):
        self.assertIn(f"`{SLUG}`", FONTE_MD)
        self.assertIn("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json", FONTE_MD)
        self.assertIn("dataInicial=" + CFG["data_inicial"], FONTE_MD)
        self.assertIn(CFG["url_portal"], FONTE_MD)
        self.assertIn("ODbL", FONTE_MD)
        self.assertIn("ODbL", CFG["licenca"])

    def test_numero_de_series_bate_com_o_config(self):
        self.assertIn(f"{len(SERIES)} códigos", FONTE_MD)

    def test_codigos_dos_agregados_documentados(self):
        secao = FONTE_MD.split("Agregados (linha `Total` de cada segmento):")[1].split("Modalidades detalhadas")[0]
        linhas = [l for l in secao.splitlines() if l.startswith("|") and re.search(r"\d{5}", l)]
        self.assertEqual(len(linhas), 3)
        for linha, seg in zip(linhas, ("Total", "PF", "PJ")):
            doc = list(map(int, re.findall(r"\b(\d{5})\b", linha)))
            cfg = CFG["series"][seg]["Total"]
            self.assertEqual(doc, [cfg["saldo"], cfg["taxa"], cfg["spread"]], seg)

    def test_contagem_de_modalidades_documentada(self):
        pf = len(CFG["series"]["PF"]) - 1
        pj = len(CFG["series"]["PJ"]) - 1
        self.assertIn(f"**{pf} em PF**", FONTE_MD)
        self.assertIn(f"**{pj} em PJ**", FONTE_MD)

    def test_corte_temporal_documentado(self):
        self.assertIn(CFG["data_inicial"], FONTE_MD)
        self.assertIn("mar/2011", FONTE_MD)

    def test_medidas_e_unidades_documentadas(self):
        for medida in ("saldo", "taxa", "spread"):
            self.assertRegex(FONTE_MD, rf"\| `{medida}` \|")
        self.assertIn("R$ milhões", FONTE_MD)
        self.assertIn("R$ milhões", CFG["unidades"]["saldo"])
        self.assertIn("% ao ano", FONTE_MD)
        self.assertIn("p.p. ao ano", FONTE_MD)

    def test_colunas_do_tidy_documentadas(self):
        secao = FONTE_MD.split("## Formato tidy")[1]
        for col in ("ano_mes", "segmento", "modalidade_credito", "saldo", "taxa_juros_aa", "spread_pp"):
            self.assertIn(f"`{col}`", secao)


class TestDeclaracaoDoPerfil(unittest.TestCase):
    def test_colunas_do_bruto(self):
        self.assertEqual(set(perfil.DECLARACAO["bruto"]["colunas"]),
                         {"segmento", "modalidade", "medida", "codigo_sgs", "data", "valor"})
        self.assertEqual(perfil.DECLARACAO["bruto"]["chave_primaria"], ["codigo_sgs", "data"])

    def test_colunas_do_tidy_batem_com_o_csv_processado(self):
        cab = (RAIZ / "dados" / "processados" / f"{SLUG}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        self.assertEqual(set(perfil.DECLARACAO["tidy"]["colunas"]), set(cab))
        self.assertEqual(perfil.DECLARACAO["tidy"]["chave_primaria"], ["ano_mes", "segmento", "modalidade_credito"])

    def test_papeis_declarados_sao_conhecidos(self):
        conhecidos = {"data", "medida", "dimensao", "chave", "texto"}
        for camada, decl in perfil.DECLARACAO.items():
            for nome, (papel, _, desc) in decl["colunas"].items():
                self.assertIn(papel, conhecidos, f"{camada}.{nome}")
                self.assertTrue(desc, f"{camada}.{nome} sem descrição")

    def test_medidas_tem_unidade(self):
        for camada, decl in perfil.DECLARACAO.items():
            for nome, (papel, unidade, _) in decl["colunas"].items():
                if papel == "medida":
                    self.assertTrue(unidade, f"{camada}.{nome} é medida sem unidade")

    def test_unidades_do_tidy_batem_com_o_config(self):
        col = perfil.DECLARACAO["tidy"]["colunas"]
        for nome in ("saldo", "taxa_juros_aa", "spread_pp"):
            self.assertEqual(col[nome][1], CFG["unidades"][nome], nome)


if __name__ == "__main__":
    unittest.main()
