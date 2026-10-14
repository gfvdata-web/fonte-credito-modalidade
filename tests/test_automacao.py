"""Etapa 7: workflow de atualização mensal, script que descarta mudanças cosméticas e dependências."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src import config
from src.publicacao import skill

from tests.helpers import RAIZ, SLUG, ler_texto

WORKFLOW = ler_texto(RAIZ / ".github" / "workflows" / "atualizacao-mensal.yml")
SCRIPT = RAIZ / ".github" / "scripts" / "descartar_mudancas_cosmeticas.py"

_spec = importlib.util.spec_from_file_location("descartar_cm", SCRIPT)
descartar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(descartar)


def _lista_do_env(nome: str) -> list[str]:
    bloco = re.search(rf"^  {nome}: >-\n((?:    \S.*\n)+)", WORKFLOW, re.M).group(1)
    return bloco.split()


class TestWorkflow(unittest.TestCase):
    def test_agenda_mensal_e_disparo_manual(self):
        cron = re.search(r'cron: "([^"]+)"', WORKFLOW).group(1)
        minuto, hora, dia, mes, dow = cron.split()
        self.assertEqual((mes, dow), ("*", "*"))
        self.assertTrue(1 <= int(dia) <= 28, "dia do mês precisa existir em todos os meses")
        self.assertTrue(0 <= int(minuto) < 60 and 0 <= int(hora) < 24)
        self.assertIn("workflow_dispatch:", WORKFLOW)

    def test_arquivos_gerados_existem_e_sao_os_que_o_pipeline_escreve(self):
        gerados = _lista_do_env("ARQUIVOS_GERADOS")
        for arq in gerados:
            self.assertTrue((RAIZ / arq).is_file(), arq)
        esperados = {
            (config.DIR_PUBLICADOS / f"{SLUG}.json").relative_to(RAIZ).as_posix(),
            (config.DIR_PUBLICADOS / f"{SLUG}.csv").relative_to(RAIZ).as_posix(),
            (config.DIR_PUBLICADOS / f"perfil_{SLUG}.json").relative_to(RAIZ).as_posix(),
            (config.DIR_PROCESSADOS / f"{SLUG}.csv").relative_to(RAIZ).as_posix(),
            skill.DESTINO_ZIP.relative_to(RAIZ).as_posix(),
        }
        self.assertEqual(set(gerados), esperados)

    def test_arquivos_escritos_a_mao_ficam_de_fora(self):
        a_mao = _lista_do_env("ARQUIVOS_A_MAO")
        self.assertEqual(set(a_mao), {f"docs/dados/notas_{SLUG}.json", f"docs/dados/eventos_{SLUG}.json"})
        self.assertFalse(set(a_mao) & set(_lista_do_env("ARQUIVOS_GERADOS")))
        for arq in a_mao:
            self.assertTrue((RAIZ / arq).is_file(), arq)

    def test_passos_usam_scripts_que_existem(self):
        self.assertIn("python run_pipeline.py", WORKFLOW)
        self.assertTrue((RAIZ / "run_pipeline.py").is_file())
        self.assertIn(".github/scripts/descartar_mudancas_cosmeticas.py", WORKFLOW)
        self.assertTrue(SCRIPT.is_file())
        self.assertIn("pip install -r requirements.txt", WORKFLOW)
        self.assertRegex(WORKFLOW, r'python-version: "3\.13"')

    def test_commit_so_quando_mudou_e_sem_sobrescrever_historico(self):
        self.assertIn("steps.mudancas.outputs.mudou == 'true'", WORKFLOW)
        self.assertIn("git pull --rebase", WORKFLOW)
        self.assertNotIn("--force", WORKFLOW)
        self.assertIn("contents: write", WORKFLOW)

    def test_mensagem_de_commit_le_o_periodo_do_json_publicado(self):
        m = re.search(r"json\.load\(open\('([^']+)'", WORKFLOW)
        self.assertEqual(m.group(1), f"docs/dados/{SLUG}.json")
        self.assertIn("['meta']['periodo']['fim']", WORKFLOW)

    def test_workflow_nao_faz_deploy_nem_usa_segredos(self):
        self.assertNotIn("wrangler", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)

    def test_protege_os_arquivos_a_mao_antes_de_comparar(self):
        self.assertLess(WORKFLOW.index("Proteger arquivos escritos"), WORKFLOW.index("Descartar mudanças"))
        self.assertIn("git checkout HEAD -- $ARQUIVOS_A_MAO", WORKFLOW)


class TestDependencias(unittest.TestCase):
    def test_requirements_cobre_os_imports_de_terceiros(self):
        reqs = {re.split(r"[<>=!~ ]", l.strip())[0].lower()
                for l in ler_texto(RAIZ / "requirements.txt").splitlines() if l.strip() and not l.startswith("#")}
        usados = set()
        for py in list((RAIZ / "src").rglob("*.py")) + [RAIZ / "run_pipeline.py"]:
            usados |= set(re.findall(r"^(?:import|from) (\w+)", py.read_text(encoding="utf-8"), re.M))
        terceiros = {m for m in usados if m not in sys.stdlib_module_names and m not in {"src", "__future__"}}
        self.assertLessEqual(terceiros, reqs, f"imports sem entrada em requirements.txt: {terceiros - reqs}")


class TestDescartarMudancasCosmeticas(unittest.TestCase):
    def _zip(self, membros: dict[str, bytes], data=(2026, 1, 1, 0, 0, 0)) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for nome, conteudo in membros.items():
                zf.writestr(zipfile.ZipInfo(nome, data), conteudo)
        return buf.getvalue()

    def test_json_so_com_carimbo_diferente_e_cosmetico(self):
        a = json.dumps({"meta": {"gerado_em": "2026-01-01", "x": 1}, "d": [1]}).encode()
        b = json.dumps({"meta": {"gerado_em": "2026-02-01", "x": 1}, "d": [1]}).encode()
        self.assertTrue(descartar.so_cosmetica("a.json", a, b))

    def test_json_com_dado_novo_nao_e_cosmetico(self):
        a = json.dumps({"meta": {"gerado_em": "1"}, "d": [1]}).encode()
        b = json.dumps({"meta": {"gerado_em": "2"}, "d": [1, 2]}).encode()
        self.assertFalse(descartar.so_cosmetica("a.json", a, b))

    def test_alerta_coletado_em_do_perfil_e_cosmetico(self):
        a = json.dumps({"alertas": ["coletado em 2026-01-01T00:00:00+00:00", "outro"]}).encode()
        b = json.dumps({"alertas": ["coletado em 2026-02-02T09:09:09+00:00", "outro"]}).encode()
        c = json.dumps({"alertas": ["coletado em 2026-02-02T09:09:09+00:00", "OUTRO"]}).encode()
        self.assertTrue(descartar.so_cosmetica("perfil.json", a, b))
        self.assertFalse(descartar.so_cosmetica("perfil.json", a, c))

    def test_zip_com_mesmo_conteudo_e_data_diferente_e_cosmetico(self):
        a = self._zip({"s/SKILL.md": b"x"}, (2026, 1, 1, 0, 0, 0))
        b = self._zip({"s/SKILL.md": b"x"}, (2026, 5, 5, 1, 1, 0))
        c = self._zip({"s/SKILL.md": b"y"})
        self.assertNotEqual(a, b)
        self.assertTrue(descartar.so_cosmetica("s.zip", a, b))
        self.assertFalse(descartar.so_cosmetica("s.zip", a, c))

    def test_csv_so_com_quebra_de_linha_e_cosmetico(self):
        self.assertTrue(descartar.so_cosmetica("a.csv", b"a,b\n1,2\n", b"a,b\r\n1,2\r\n"))
        self.assertFalse(descartar.so_cosmetica("a.csv", b"a,b\n1,2\n", b"a,b\n1,3\n"))

    def test_main_restaura_cosmetico_e_mantem_mudanca_real(self):
        """Roda o script de verdade num repositório git descartável (pasta temporária)."""
        def git(*args):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                                   *args], check=True, capture_output=True, text=True)

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="cm-git-") as tmp:
            os.chdir(tmp)
            try:
                git("init", "-q")
                Path("d.json").write_text(json.dumps({"meta": {"gerado_em": "1"}, "v": 1}), encoding="utf-8")
                Path("n.json").write_text(json.dumps({"meta": {"gerado_em": "1"}, "v": 1}), encoding="utf-8")
                git("add", "."), git("commit", "-q", "-m", "base")

                Path("d.json").write_text(json.dumps({"meta": {"gerado_em": "2"}, "v": 1}), encoding="utf-8")
                Path("n.json").write_text(json.dumps({"meta": {"gerado_em": "2"}, "v": 2}), encoding="utf-8")
                with mock.patch("builtins.print"):
                    mudou_real = descartar.main(["d.json", "n.json"])
                self.assertTrue(mudou_real)
                self.assertEqual(json.loads(Path("d.json").read_text())["meta"]["gerado_em"], "1")   # restaurado
                self.assertEqual(json.loads(Path("n.json").read_text())["v"], 2)                     # mantido

                git("checkout", "HEAD", "--", "n.json")
                Path("d.json").write_text(json.dumps({"meta": {"gerado_em": "3"}, "v": 1}), encoding="utf-8")
                with mock.patch("builtins.print"):
                    self.assertFalse(descartar.main(["d.json", "n.json", "inexistente.json"]))
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
