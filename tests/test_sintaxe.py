"""Sintaxe: Python compila, JSON/CSV parseiam e todo JS (arquivos e <script> inline) passa no `node --check`."""
from __future__ import annotations

import csv
import json
import py_compile
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import DOCS, RAIZ

NODE = shutil.which("node")
RE_SCRIPT = re.compile(r"<script(?P<attrs>[^>]*)>(?P<corpo>.*?)</script>", re.S | re.I)


def _arquivos(base: str, padrao: str) -> list[Path]:
    return sorted((RAIZ / base).rglob(padrao))


class TestSintaxe(unittest.TestCase):
    def test_python_compila(self):
        alvos = [RAIZ / "run_pipeline.py", *_arquivos("src", "*.py"), *_arquivos("tests", "*.py"),
                 *_arquivos("skill", "*.py")]
        self.assertGreater(len(alvos), 10)
        with tempfile.TemporaryDirectory() as tmp:
            for i, arq in enumerate(alvos):
                try:
                    py_compile.compile(str(arq), cfile=str(Path(tmp) / f"{i}.pyc"), doraise=True)
                except py_compile.PyCompileError as exc:
                    self.fail(f"{arq.relative_to(RAIZ)}: {exc.msg}")

    def test_json_valido(self):
        alvos = _arquivos("docs/dados", "*.json") + _arquivos("tests/fixtures", "*.json")
        self.assertGreaterEqual(len(alvos), 5)
        for arq in alvos:
            try:
                json.loads(arq.read_text(encoding="utf-8"))
            except ValueError as exc:
                self.fail(f"JSON inválido {arq.relative_to(RAIZ)}: {exc}")

    def test_csv_com_colunas_consistentes(self):
        alvos = [RAIZ / "dados" / "processados" / "credito_modalidade.csv",
                 DOCS / "dados" / "credito_modalidade.csv"]
        alvos = [a for a in alvos if a.exists()]        # o público só existe depois da publicação
        self.assertTrue(alvos)
        for arq in alvos:
            with arq.open(encoding="utf-8", newline="") as f:
                linhas = list(csv.reader(f))
            self.assertGreater(len(linhas), 100, arq.name)
            self.assertTrue(all(len(l) == len(linhas[0]) for l in linhas), arq.name)

    @unittest.skipIf(NODE is None, "node não instalado")
    def test_js_dos_arquivos(self):
        alvos = _arquivos("docs/js", "*.js") + _arquivos("tests/js", "*.js")
        self.assertGreaterEqual(len(alvos), 2)
        for arq in alvos:
            r = subprocess.run([NODE, "--check", str(arq)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{arq.relative_to(RAIZ)}:\n{r.stderr.strip()}")

    @unittest.skipIf(NODE is None, "node não instalado")
    def test_js_inline_das_paginas(self):
        with tempfile.TemporaryDirectory() as tmp:
            for html in sorted(DOCS.glob("*.html")):
                texto = html.read_text(encoding="utf-8")
                for i, m in enumerate(RE_SCRIPT.finditer(texto)):
                    if "src=" in m["attrs"] or "json" in m["attrs"].lower() or not m["corpo"].strip():
                        continue
                    tmp_js = Path(tmp) / f"{html.name}.{i}.js"
                    tmp_js.write_text(m["corpo"], encoding="utf-8")
                    r = subprocess.run([NODE, "--check", str(tmp_js)], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, f"<script> #{i} de docs/{html.name}:\n{r.stderr.strip()}")


if __name__ == "__main__":
    unittest.main()
