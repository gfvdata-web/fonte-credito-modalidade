"""Skill do Claude (skill/credito-modalidade-bcb): estrutura, script de carga offline e zip publicado."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src import config
from src.publicacao import skill as empacotador

from tests import helpers
from tests.helpers import DADOS_PUB, RAIZ, SLUG

DIR_SKILL = RAIZ / "skill" / "credito-modalidade-bcb"
ZIP_PUBLICO = RAIZ / "docs" / "skill" / "credito-modalidade-bcb.zip"

_spec = importlib.util.spec_from_file_location("carregar_dados_cm", DIR_SKILL / "scripts" / "carregar_dados.py")
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)

CFG = config.fonte()


def _csv_publico() -> str:
    return (DADOS_PUB / f"{SLUG}.csv").read_text(encoding="utf-8")


def _corpo_sgs(codigo: int) -> list[dict]:
    """Resposta do SGS para o código, vinda da fixture do projeto (2 meses basta)."""
    return helpers.corpo_do_codigo(codigo)[:3]


def _baixar_falso(url: str, timeout: int = 60) -> bytes:
    m = helpers.RE_CODIGO.search(url)
    if m is None:
        raise OSError(f"URL inesperada: {url}")
    return json.dumps(_corpo_sgs(int(m.group(1)))).encode("utf-8")


class TestEstruturaDaSkill(unittest.TestCase):
    def test_frontmatter(self):
        texto = helpers.ler_texto(DIR_SKILL / "SKILL.md")
        m = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", texto)
        self.assertIsNotNone(m, "SKILL.md sem frontmatter name/description")
        self.assertEqual(m.group(1).strip(), DIR_SKILL.name)
        self.assertEqual(m.group(1).strip(), empacotador.NOME_SKILL)
        self.assertGreater(len(m.group(2)), 80)
        self.assertLessEqual(len(m.group(2)), 1024)

    def test_referencias_citadas_no_skill_md_existem(self):
        texto = (DIR_SKILL / "SKILL.md").read_text(encoding="utf-8")
        citadas = set(re.findall(r"`?((?:references|scripts)/[\w.-]+)`?", texto))
        self.assertTrue(citadas)
        for ref in citadas:
            self.assertTrue((DIR_SKILL / ref).is_file(), f"SKILL.md cita {ref}, que não existe")

    def test_urls_do_script_batem_com_o_projeto(self):
        self.assertEqual(cd.URL_SGS, config.BCB_SGS_URL + "&dataInicial=" + CFG["data_inicial"])
        self.assertTrue(cd.URL_SITE.startswith("https://creditomodalidade.gfvdata.com/"))
        self.assertTrue(cd.URL_SITE.endswith(f"/dados/{SLUG}.csv"))
        self.assertTrue((DADOS_PUB / f"{SLUG}.csv").is_file())
        self.assertIn(cd.URL_SITE, (DIR_SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("sgs.433", cd.URL_IPCA)

    def test_mapa_de_series_igual_ao_config(self):
        self.assertEqual(cd.SERIES, CFG["series"], "a cópia do mapa SGS na skill divergiu de src/config.py")

    def test_script_compila_e_so_usa_biblioteca_padrao(self):
        fonte = (DIR_SKILL / "scripts" / "carregar_dados.py").read_text(encoding="utf-8")
        compile(fonte, "carregar_dados.py", "exec")
        importados = set(re.findall(r"^(?:import|from) (\w+)", fonte, re.M)) - {"__future__"}
        self.assertLessEqual(importados, set(sys.stdlib_module_names), "a skill roda em ambientes sem pip")


class TestCarregarDados(unittest.TestCase):
    def test_de_csv_aceita_tidy_do_projeto(self):
        linhas = cd._de_csv(_csv_publico())
        self.assertEqual({(l["segmento"], l["modalidade_credito"]) for l in linhas},
                         {(s, m) for s, mods in CFG["series"].items() for m in mods})
        self.assertIsInstance(linhas[0]["saldo"], float)
        total = next(l for l in linhas if l["modalidade_credito"] == "Total")
        self.assertIsNotNone(total["spread_pp"])
        det = next(l for l in linhas if l["modalidade_credito"] != "Total")
        self.assertIsNone(det["spread_pp"], "spread ausente deve ser None, nunca zero")

    def test_de_csv_aceita_bom_utf8(self):
        self.assertTrue(cd._de_csv("﻿" + _csv_publico()))

    def test_de_csv_rejeita_vazio_e_formato_desconhecido(self):
        with self.assertRaises(ValueError):
            cd._de_csv("")
        with self.assertRaises(ValueError):
            cd._de_csv("a,b\n1,2\n")

    def test_montar_junta_as_medidas_numa_linha(self):
        linhas = cd._montar([("2025-01", "PF", "Cheque especial", "saldo", 10.0),
                             ("2025-01", "PF", "Cheque especial", "taxa_juros_aa", 99.5)])
        self.assertEqual(linhas, [{"ano_mes": "2025-01", "segmento": "PF", "modalidade_credito": "Cheque especial",
                                   "saldo": 10.0, "taxa_juros_aa": 99.5, "spread_pp": None}])

    def test_de_bruto_converte_registros_do_pipeline(self):
        regs = [{"segmento": "Total", "modalidade": "Total", "medida": "saldo", "codigo_sgs": 20539,
                 "data": "01/03/2011", "valor": "1759678"},
                {"segmento": "Total", "modalidade": "Total", "medida": "taxa", "codigo_sgs": 20714,
                 "data": "01/03/2011", "valor": "27.35"}]
        for corpo in ({"registros": regs}, regs):
            linhas = cd._de_bruto(corpo)
            self.assertEqual(len(linhas), 1)
            self.assertEqual((linhas[0]["ano_mes"], linhas[0]["saldo"], linhas[0]["taxa_juros_aa"]),
                             ("2011-03", 1759678.0, 27.35))

    def test_numero_vazio_vira_none(self):
        self.assertIsNone(cd._numero(""))
        self.assertIsNone(cd._numero(None))
        self.assertEqual(cd._numero("1.5"), 1.5)

    def test_arquivo_csv_do_usuario(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "anexo.csv"
            arq.write_text(_csv_publico(), encoding="utf-8")
            linhas, origem = cd.carregar("auto", str(arq))
        self.assertTrue(linhas)
        self.assertIn("anexo.csv", origem)

    def test_arquivo_json_bruto_do_pipeline(self):
        regs = [{"segmento": "PF", "modalidade": "Total", "medida": "saldo", "codigo_sgs": 20541,
                 "data": "01/01/2025", "valor": "5"}]
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "bruto.json"
            arq.write_text(json.dumps({"registros": regs}), encoding="utf-8")
            linhas, _ = cd.carregar("auto", str(arq))
        self.assertEqual(len(linhas), 1)

    def test_arquivo_inexistente_sai_com_codigo_1(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            cd.carregar("auto", "nao_existe.csv")
        self.assertEqual(ctx.exception.code, 1)

    def test_origem_auto_cai_para_o_site_quando_a_api_falha(self):
        def baixar(url, timeout=60):
            if url == cd.URL_SITE:
                return _csv_publico().encode("utf-8")
            raise OSError("sem rede")
        with mock.patch.object(cd, "_baixar", side_effect=baixar), mock.patch.object(cd.time, "sleep"), \
                contextlib.redirect_stderr(io.StringIO()):
            linhas, origem = cd.carregar("auto", None)
        self.assertTrue(linhas)
        self.assertIn("site", origem)

    def test_origem_bcb_baixa_as_61_series(self):
        with mock.patch.object(cd, "_baixar", side_effect=_baixar_falso) as baixar, \
                mock.patch.object(cd.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            linhas, origem = cd.carregar("bcb", None)
        self.assertEqual(baixar.call_count, len(config.series_sgs(CFG)))
        self.assertIn("SGS", origem)
        self.assertEqual(len({(l["segmento"], l["modalidade_credito"]) for l in linhas}),
                         sum(len(m) for m in CFG["series"].values()))
        pf = next(l for l in linhas if l["segmento"] == "PF" and l["modalidade_credito"] == "Cheque especial")
        self.assertIsNone(pf["spread_pp"])

    def test_bloqueio_html_do_gateway_tenta_de_novo(self):
        respostas = iter([b"<html>Requisicao invalida</html>", json.dumps(_corpo_sgs(20539)).encode()])
        with mock.patch.object(cd, "_baixar", side_effect=lambda *a, **k: next(respostas)), \
                mock.patch.object(cd.time, "sleep") as dorme:
            serie = cd._baixar_json("https://x/sgs.20539/")
        self.assertEqual(len(serie), 3)
        dorme.assert_called_once_with(2)

    def test_sem_nenhuma_origem_sai_com_codigo_2_e_orienta(self):
        err = io.StringIO()
        with mock.patch.object(cd, "_baixar", side_effect=OSError("bloqueado")), \
                mock.patch.object(cd.time, "sleep"), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            cd.carregar("auto", None)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("--arquivo", err.getvalue())

    def test_deflacionar_com_ipca_simulado(self):
        linhas = [{"ano_mes": "2024-01", "saldo": 100.0}, {"ano_mes": "2024-03", "saldo": 100.0},
                  {"ano_mes": "2024-02", "saldo": None}]
        ipca = [{"data": "01/01/2024", "valor": "1.0"}, {"data": "01/02/2024", "valor": "1.0"},
                {"data": "01/03/2024", "valor": "1.0"}]
        with mock.patch.object(cd, "_baixar", return_value=json.dumps(ipca).encode()):
            base = cd.deflacionar(linhas)
        self.assertEqual(base, "2024-03")
        self.assertEqual(linhas[1]["saldo_real"], 100.0)                 # mês-base não muda
        self.assertAlmostEqual(linhas[0]["saldo_real"], 100 * 1.01 ** 2, places=2)
        self.assertIsNone(linhas[2]["saldo_real"])

    def test_deflacionar_sem_rede_segue_sem_saldo_real(self):
        linhas = [{"ano_mes": "2024-01", "saldo": 1.0}]
        with mock.patch.object(cd, "_baixar", side_effect=OSError), mock.patch.object(cd.time, "sleep"), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(cd.deflacionar(linhas))
        self.assertNotIn("saldo_real", linhas[0])

    def _rodar_main(self, argv: list[str]) -> str:
        buf = io.StringIO()
        buf.reconfigure = lambda **_: None
        err = mock.MagicMock()
        with mock.patch("sys.argv", ["carregar_dados.py", *argv]), contextlib.redirect_stdout(buf), \
                mock.patch.object(sys, "stderr", err):
            cd.main()
        return buf.getvalue()

    def test_main_de_ponta_a_ponta_com_arquivo_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            entrada, saida = Path(tmp) / "entrada.csv", Path(tmp) / "saida.csv"
            entrada.write_text(_csv_publico(), encoding="utf-8")
            texto = self._rodar_main(["--arquivo", str(entrada), "--saida", str(saida)])
            cabecalho = saida.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(cabecalho, "ano_mes,segmento,modalidade_credito,saldo,taxa_juros_aa,spread_pp")
        self.assertIn("Agregados no último mês", texto)
        self.assertIn("Spread: só nas linhas", texto)

    def test_main_com_ipca_mockado_acrescenta_saldo_real(self):
        ipca = [{"data": f"01/{m:02d}/2025", "valor": "0.5"} for m in range(1, 13)]
        ipca += [{"data": f"01/{m:02d}/2026", "valor": "0.5"} for m in range(1, 3)]
        with tempfile.TemporaryDirectory() as tmp:
            entrada, saida = Path(tmp) / "entrada.csv", Path(tmp) / "saida.csv"
            entrada.write_text(_csv_publico(), encoding="utf-8")
            with mock.patch.object(cd, "_baixar", return_value=json.dumps(ipca).encode()):
                texto = self._rodar_main(["--arquivo", str(entrada), "--ipca", "--saida", str(saida)])
            cabecalho = saida.read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(cabecalho.endswith(",saldo_real"))
        self.assertIn("saldo_real: R$ milhões a preços de", texto)

    def test_main_via_subprocesso_com_rede_falhando_sai_com_2(self):
        # Rede bloqueada de verdade: o proxy inválido faz toda requisição falhar sem sair da máquina.
        import os
        import subprocess
        env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
               "NO_PROXY": ""}
        with tempfile.TemporaryDirectory() as tmp:
            codigo = ("import sys, importlib.util as u;"
                      f"s=u.spec_from_file_location('c', r'{DIR_SKILL / 'scripts' / 'carregar_dados.py'}');"
                      "m=u.module_from_spec(s); s.loader.exec_module(m);"
                      "m.TENTATIVAS=1; m.PAUSA_ENTRE_SERIES=0;"
                      "m._baixar=lambda *a, **k: (_ for _ in ()).throw(OSError('sem rede'));"
                      "sys.argv=['x','--saida','out.csv']; m.main()")
            r = subprocess.run([sys.executable, "-I", "-c", codigo], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stderr[-400:])
        self.assertIn("--arquivo", r.stderr)


class TestZipPublicadoEmDia(unittest.TestCase):
    """O zip servido pelo site precisa refletir a pasta skill/ (o pipeline o regenera)."""

    def test_zip_tem_os_mesmos_arquivos_e_conteudo_da_pasta(self):
        fontes = {p.relative_to(DIR_SKILL.parent).as_posix(): p for p in DIR_SKILL.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts}
        with zipfile.ZipFile(ZIP_PUBLICO) as zf:
            self.assertEqual(sorted(zf.namelist()), sorted(fontes), "arquivos do zip diferem de skill/")
            velhos = [n for n, p in fontes.items()
                      if zf.read(n).replace(b"\r\n", b"\n") != p.read_bytes().replace(b"\r\n", b"\n")]
        self.assertEqual(velhos, [], "zip desatualizado: rode `python -m src.publicacao.skill`")

    def test_eventos_md_da_skill_acompanha_o_catalogo_do_painel(self):
        with helpers.ambiente_isolado(), helpers.sem_saida():
            empacotador.gerar_eventos_md()
            gerado = helpers.ler_texto(empacotador.DIR_SKILL / "references" / "eventos.md")
        atual = helpers.ler_texto(DIR_SKILL / "references" / "eventos.md")
        self.assertEqual(gerado, atual, f"references/eventos.md diverge de eventos_{SLUG}.json")

    def test_empacotar_gera_zip_valido_na_pasta_temporaria(self):
        with helpers.ambiente_isolado() as raiz, helpers.sem_saida():
            empacotador.empacotar()
            zip_tmp = raiz / "docs" / "skill" / f"{empacotador.NOME_SKILL}.zip"
            self.assertTrue(zip_tmp.is_file())
            with zipfile.ZipFile(zip_tmp) as zf:
                self.assertIsNone(zf.testzip())
                self.assertIn(f"{empacotador.NOME_SKILL}/SKILL.md", zf.namelist())

    def test_zip_sem_lixo(self):
        with zipfile.ZipFile(ZIP_PUBLICO) as zf:
            self.assertIsNone(zf.testzip())
            self.assertFalse([n for n in zf.namelist() if "__pycache__" in n or n.endswith(".pyc")])


if __name__ == "__main__":
    unittest.main()
