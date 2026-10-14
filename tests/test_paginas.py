"""Páginas de docs/: links locais, ids, abas, navegação, tema, rastreio e instalação da skill.

Sem navegador: o HTML é lido com html.parser e o JS com expressões regulares.
"""
from __future__ import annotations

import re
import unittest
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

from src.publicacao import skill

from tests.helpers import DOCS, SLUG

PAGINAS = ["index.html", "explorar.html", "skill.html"]
JS_DA_PAGINA = {"index.html": "js/app-v2.js", "explorar.html": "js/explorar.js"}
SEGMENTOS = {"PF", "PJ"}


class Pagina(HTMLParser):
    def __init__(self, texto: str):
        super().__init__()
        self.ids: list[str] = []
        self.links: list[tuple[str, str, dict]] = []   # (tag, url, atributos)
        self.atributos: list[tuple[str, dict]] = []
        self.scripts_inline: list[str] = []
        self.titulo = ""
        self._em_titulo = self._em_script = False
        self._buf: list[str] = []
        self.feed(texto)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.atributos.append((tag, a))
        if "id" in a:
            self.ids.append(a["id"])
        if tag in ("a", "link") and a.get("href"):
            self.links.append((tag, a["href"], a))
        if tag in ("script", "img", "source") and a.get("src"):
            self.links.append((tag, a["src"], a))
        self._em_titulo = tag == "title"
        self._em_script = tag == "script" and "src" not in a
        self._buf = []

    def handle_data(self, data):
        if self._em_titulo:
            self.titulo += data
        if self._em_script:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._em_script:
            self.scripts_inline.append("".join(self._buf))
        self._em_titulo = self._em_script = False


def _pagina(nome: str) -> Pagina:
    return Pagina((DOCS / nome).read_text(encoding="utf-8"))


def _eh_local(url: str) -> bool:
    p = urlparse(url)
    return not (p.scheme or p.netloc or url.startswith(("//", "#", "mailto:", "javascript:")))


class TestLinksLocais(unittest.TestCase):
    def test_todo_href_e_src_local_existe(self):
        quebrados = []
        for nome in PAGINAS:
            for tag, url, _ in _pagina(nome).links:
                if not _eh_local(url):
                    continue
                alvo = DOCS / unquote(urlparse(url).path)
                if not alvo.is_file():
                    quebrados.append(f"docs/{nome}: <{tag}> {url}")
        self.assertEqual(quebrados, [])

    def test_ancoras_internas_apontam_para_id_existente(self):
        for nome in PAGINAS:
            pg = _pagina(nome)
            for _, url, _ in pg.links:
                if url.startswith("#") and len(url) > 1:
                    self.assertIn(url[1:], pg.ids, f"{nome}: {url}")

    def test_refs_dos_js_a_arquivos_do_site_existem(self):
        for js in JS_DA_PAGINA.values():
            fonte = (DOCS / js).read_text(encoding="utf-8")
            for ref in re.findall(r'"((?:dados|css|js|skill)/[\w./-]+\.(?:json|csv|zip|css|js))"', fonte):
                self.assertTrue((DOCS / ref).is_file(), f"{js} referencia {ref}, que não existe")

    def test_paginas_tem_titulo_idioma_e_viewport(self):
        for nome in PAGINAS:
            pg = _pagina(nome)
            self.assertTrue(pg.titulo.strip(), nome)
            html = next(a for t, a in pg.atributos if t == "html")
            self.assertEqual(html.get("lang"), "pt-BR", nome)
            self.assertTrue(any(t == "meta" and a.get("name") == "viewport" for t, a in pg.atributos), nome)

    def test_ids_unicos_por_pagina(self):
        for nome in PAGINAS:
            ids = _pagina(nome).ids
            repetidos = {i for i in ids if ids.count(i) > 1}
            self.assertEqual(repetidos, set(), nome)


class TestRastreioEUrls(unittest.TestCase):
    def test_goatcounter_em_todas_as_paginas(self):
        for nome in PAGINAS:
            tags = [a for t, a in _pagina(nome).atributos if t == "script" and "data-goatcounter" in a]
            self.assertEqual(len(tags), 1, f"{nome}: esperado 1 script do GoatCounter")
            self.assertEqual(tags[0]["data-goatcounter"], "https://gfvdata.goatcounter.com/count", nome)
            self.assertEqual(tags[0].get("src"), "//gc.zgo.at/count.js", nome)

    def test_nenhuma_url_do_github_pages_deste_repo_no_site(self):
        achados = [str(p.relative_to(DOCS)) for p in DOCS.rglob("*")
                   if p.is_file() and p.suffix in {".html", ".js", ".css", ".json", ".csv"}
                   and "gfvdata-web.github.io/fonte-credito-modalidade" in p.read_text(encoding="utf-8")]
        self.assertEqual(achados, [], "o site agora vive em creditomodalidade.gfvdata.com")

    def test_explorar_html_nao_liga_para_outras_fontes(self):
        for _, url, _ in _pagina("explorar.html").links:
            if _eh_local(url):
                continue
            host = urlparse(url if not url.startswith("//") else "https:" + url).netloc
            self.assertFalse(host.endswith("github.io"), f"explorar.html linka {url}")
            self.assertNotIn("gfvdata.com", host, f"explorar.html linka outra fonte: {url}")


class TestJsReferenciaIdsDoHtml(unittest.TestCase):
    def _ids_usados(self, js: str) -> set[str]:
        fonte = (DOCS / js).read_text(encoding="utf-8")
        ids = set(re.findall(r'getElementById\(\s*"([\w-]+)"\s*\)', fonte))
        ids |= set(re.findall(r'\$\(\s*"([\w-]+)"\s*\)', fonte))             # helper $ do explorar.js
        ids |= set(re.findall(r'querySelector(?:All)?\(\s*"#([\w-]+)', fonte))
        return ids

    def test_painel(self):
        ids = _pagina("index.html").ids
        usados = self._ids_usados("js/app-v2.js")
        self.assertGreater(len(usados), 8)
        self.assertEqual(sorted(usados - set(ids)), [], "ids lidos pelo app-v2.js ausentes no index.html")

    def test_exploracao(self):
        ids = _pagina("explorar.html").ids
        usados = self._ids_usados("js/explorar.js")
        self.assertGreater(len(usados), 15)
        self.assertEqual(sorted(usados - set(ids)), [], "ids lidos pelo explorar.js ausentes no explorar.html")

    def test_secoes_que_o_js_mostra_comecam_ocultas(self):
        pg = _pagina("explorar.html")
        ocultas = {a["id"] for t, a in pg.atributos if t == "section" and "hidden" in a and "id" in a}
        fonte = (DOCS / "js/explorar.js").read_text(encoding="utf-8")
        for sec in set(re.findall(r'mostrar\("(sec-[\w-]+)"\)', fonte)):
            self.assertIn(sec, ocultas, f"{sec} deveria nascer hidden (o JS a revela)")

    def test_switch_de_tema_claro_escuro_no_painel_e_na_skill(self):
        for nome in ("index.html", "skill.html"):
            pg = _pagina(nome)
            self.assertIn("tema-switch-v2", pg.ids, nome)
            botoes = {a.get("data-tema") for t, a in pg.atributos if t == "button" and "data-tema" in a}
            self.assertEqual(botoes, {"light", "dark"}, nome)

    def test_tema_inicial_lido_do_localstorage_antes_do_css_pintar(self):
        for nome in ("index.html", "skill.html"):
            self.assertTrue(any('localStorage.getItem("tema-v2")' in s for s in _pagina(nome).scripts_inline), nome)


class TestAbasESubabas(unittest.TestCase):
    """Pílulas/abas do painel: cada botão tem um valor que o JS sabe tratar."""

    @classmethod
    def setUpClass(cls):
        cls.pg = _pagina("index.html")
        cls.js = (DOCS / "js/app-v2.js").read_text(encoding="utf-8")

    def _valores(self, atributo: str) -> list[str]:
        return [a[atributo] for t, a in self.pg.atributos if t == "button" and atributo in a]

    def test_metrica_da_linha_do_tempo(self):
        self.assertEqual(self._valores("data-metrica-evo"), ["taxa", "saldo"])
        self.assertIn('evoMetrica = btn.dataset.metricaEvo', self.js)
        self.assertIn('evoMetrica === "saldo"', self.js)

    def test_so_um_botao_ativo_por_grupo(self):
        ativos = [a for t, a in self.pg.atributos
                  if t == "button" and "data-metrica-evo" in a and "ativo" in a.get("class", "").split()]
        self.assertEqual(len(ativos), 1)
        self.assertEqual(ativos[0]["data-metrica-evo"], re.search(r'let evoMetrica = "(\w+)"', self.js).group(1))

    def test_periodos_gerados_pelo_js_sao_todos_tratados(self):
        codigos = re.findall(r'\{ codigo: "(\w+)", rotulo', self.js.split("const PERIODOS")[1].split("];")[0])
        self.assertEqual(codigos, ["tudo", "10a", "5a", "1a"])
        corpo = self.js.split("function periodoParaIndices")[1].split("\n}\n")[0]
        for c in codigos:
            if c != "tudo":   # "tudo" é o retorno final padrão
                self.assertIn(f'"{c}"', corpo, f"periodoParaIndices não trata {c}")
        for cont in ("seletor-segmento", "periodo-participacao", "periodo-evolucao", "foco-forma"):
            self.assertIn(cont, self.pg.ids)

    def test_estado_inicial_do_js_e_valido(self):
        validos = {"tudo", "10a", "5a", "1a"}
        self.assertIn(re.search(r'let participPeriodo = "(\w+)"', self.js).group(1), validos)
        self.assertIn(re.search(r'let evoPeriodo = "(\w+)"', self.js).group(1), validos)
        self.assertIn(re.search(r'let segmento = "(\w+)"', self.js).group(1), SEGMENTOS)
        self.assertIn(re.search(r'let evoMetrica = "(\w+)"', self.js).group(1), {"taxa", "saldo"})

    def test_abas_tem_papel_acessivel(self):
        for t, a in self.pg.atributos:
            if t == "button" and "data-metrica-evo" in a:
                self.assertEqual(a.get("role"), "tab")

    def test_filtros_da_pauta_em_explorar(self):
        pg = _pagina("explorar.html")
        filtros = [a["data-status"] for t, a in pg.atributos if t == "button" and "data-status" in a]
        self.assertEqual(filtros[0], "todos")
        self.assertEqual(set(filtros), {"todos", "proposto", "aprovado", "descartado", "no_painel"})

    def test_exploracao_aponta_para_o_slug_certo(self):
        body = next(a for t, a in _pagina("explorar.html").atributos if t == "body")
        self.assertEqual(body.get("data-slug"), SLUG)
        for arq in (f"perfil_{SLUG}.json", f"notas_{SLUG}.json"):
            self.assertTrue((DOCS / "dados" / arq).is_file(), arq)

    def test_arquivos_lidos_pelo_painel(self):
        self.assertIn(f'"dados/{SLUG}.json"', self.js)
        self.assertIn(f'"dados/eventos_{SLUG}.json"', self.js)


class TestNavegacao(unittest.TestCase):
    def test_cabecalho_tem_exatamente_painel_e_skill_e_marca_a_pagina_atual(self):
        for nome in ("index.html", "skill.html"):
            pg = _pagina(nome)
            iniciou = False
            itens = []
            for t, a in pg.atributos:
                if t == "nav" and "nav-paineis" in a.get("class", ""):
                    iniciou = True
                elif iniciou and t == "a":
                    itens.append((a["href"], a.get("aria-current")))
                elif iniciou and t in ("header", "main"):
                    break
            self.assertEqual([h for h, _ in itens], ["index.html", "skill.html"], nome)
            self.assertEqual([h for h, c in itens if c == "page"], [nome], f"{nome} deve marcar só a si mesma")

    def test_textos_do_menu(self):
        for nome in ("index.html", "skill.html"):
            nav = re.search(r'<nav class="nav-paineis".*?</nav>', (DOCS / nome).read_text(encoding="utf-8"), re.S).group(0)
            self.assertEqual(re.findall(r">([^<]+)</a>", nav), ["Painel", "Skill Claude"], nome)

    def test_exploracao_volta_ao_painel(self):
        hrefs = [u for _, u, _ in _pagina("explorar.html").links]
        self.assertIn("index.html", hrefs)
        self.assertIn("skill.html", hrefs)

    def test_painel_leva_a_skill_e_ao_csv(self):
        hrefs = [u for _, u, _ in _pagina("index.html").links]
        self.assertIn("skill.html", hrefs)
        self.assertIn(f"dados/{SLUG}.csv", hrefs)

    def test_links_externos_usam_https(self):
        for nome in PAGINAS:
            for _, url, _ in _pagina(nome).links:
                if not _eh_local(url) and not url.startswith("#"):
                    self.assertTrue(url.startswith(("https://", "//")), f"{nome}: {url}")


class TestPaginaDeInstalacaoDaSkill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = (DOCS / "skill.html").read_text(encoding="utf-8")
        cls.pg = _pagina("skill.html")
        cls.zip = DOCS / "skill" / f"{skill.NOME_SKILL}.zip"

    def test_tres_passos(self):
        ol = re.search(r'<ol class="passos-skill">(.*?)</ol>', self.texto, re.S).group(1)
        passos = re.findall(r"<li>\s*<h3>(.*?)</h3>", ol, re.S)
        self.assertEqual(len(passos), 3, passos)

    def test_botao_de_download_aponta_para_o_zip_da_skill(self):
        botao = next(a for t, a in self.pg.atributos if t == "a" and "botao-download" in a.get("class", ""))
        self.assertEqual(botao["href"], f"skill/{skill.NOME_SKILL}.zip")
        self.assertEqual(botao["href"], "skill/credito-modalidade-bcb.zip")
        self.assertIn("download", botao)
        self.assertTrue(self.zip.is_file())
        self.assertTrue(zipfile.is_zipfile(self.zip))

    def test_tamanho_anunciado_bate_com_o_zip(self):
        anunciado = int(re.search(r"\.zip, (\d+) KB", self.texto).group(1))
        real = self.zip.stat().st_size / 1024
        self.assertLessEqual(abs(anunciado - real), 1.5, f"página diz {anunciado} KB, zip tem {real:.1f} KB")

    def test_pasta_citada_na_instalacao_e_o_nome_da_skill(self):
        self.assertIn(f"<code>{skill.NOME_SKILL}</code>", self.texto)
        self.assertIn("~/.claude/skills/", self.texto)
        with zipfile.ZipFile(self.zip) as zf:
            self.assertIn(f"{skill.NOME_SKILL}/SKILL.md", zf.namelist())

    def test_csv_alternativo_existe(self):
        self.assertIn(f'href="dados/{SLUG}.csv"', self.texto)
        self.assertTrue((DOCS / "dados" / f"{SLUG}.csv").is_file())

    def test_script_inline_do_tema_so_usa_ids_da_pagina(self):
        ids = set(self.pg.ids)
        for script in self.pg.scripts_inline:
            for i in re.findall(r'getElementById\("([\w-]+)"\)', script):
                self.assertIn(i, ids)


if __name__ == "__main__":
    unittest.main()
