"""Contrato entre os arquivos publicados em docs/dados/ e os campos que o JS das páginas lê.

Campos extraídos de docs/js/app-v2.js (painel) e docs/js/explorar.js (exploração).
Cada teste confere também que o JS ainda menciona o campo: se o JS passar a ler outra coisa,
o teste avisa que o contrato mudou.
"""
from __future__ import annotations

import csv
import re
import unittest
from datetime import datetime

from src import config

from tests.helpers import DADOS_PUB, DOCS, RAIZ, SLUG, ler_json, ler_texto

JS_PAINEL = "\n".join((DOCS / "js" / n).read_text(encoding="utf-8") for n in ("app-v2.js",))
JS_EXPLORAR = (DOCS / "js" / "explorar.js").read_text(encoding="utf-8")
RE_ANO_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CFG = config.fonte()
SEGMENTOS = list(CFG["series"])
MODALIDADES = {s: [m for m in mods if m != "Total"] for s, mods in CFG["series"].items()}


def _meses_seguidos(a: str, b: str) -> bool:
    (ya, ma), (yb, mb) = map(int, a.split("-")), map(int, b.split("-"))
    return (ya * 12 + ma) + 1 == (yb * 12 + mb)


class TestSerieDoPainel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = ler_json(DADOS_PUB / f"{SLUG}.json")

    def test_chaves_de_topo(self):
        self.assertEqual(set(self.d), {"meta", "labels", "segmentos", "rotulos_segmento", "modalidades",
                                       "rotulo_residuo", "series", "residuos", "kpis", "estatisticas"})

    def test_o_js_le_estes_campos(self):
        for trecho in ("dados.meta", "meta.fonte", "meta.gerado_em", "meta.periodo.fim",
                       "dados.kpis.totais", "dados.kpis.por_modalidade", "dados.labels",
                       "dados.rotulos_segmento", "dados.rotulo_residuo",
                       "dados.residuos", "dados.series"):
            self.assertIn(trecho, JS_PAINEL, f"o JS do painel deixou de ler {trecho}; revise o contrato")

    def test_meta(self):
        meta = self.d["meta"]
        for campo in ("fonte", "descricao", "url", "unidades", "periodicidade", "licenca", "gerado_em",
                      "periodo", "series_sgs"):
            self.assertIn(campo, meta)
        datetime.fromisoformat(meta["gerado_em"])      # o JS faz new Date(gerado_em)
        self.assertEqual(set(meta["unidades"]), {"saldo", "taxa_juros_aa", "spread_pp"})
        self.assertEqual(meta["url"], CFG["url_portal"])
        self.assertEqual(meta["series_sgs"], len(config.series_sgs(CFG)))

    def test_labels_mensais_sem_buraco(self):
        labels = self.d["labels"]
        self.assertGreater(len(labels), 24)
        for l in labels:
            self.assertRegex(l, RE_ANO_MES)
        for a, b in zip(labels, labels[1:]):
            self.assertTrue(_meses_seguidos(a, b), f"buraco/ordem entre {a} e {b}")
        self.assertEqual(labels[0], "2011-03")          # data_inicial da config
        self.assertEqual(self.d["meta"]["periodo"], {"inicio": labels[0], "fim": labels[-1]})
        self.assertEqual(self.d["kpis"]["totais"]["mes_ref"], labels[-1])
        self.assertEqual(self.d["kpis"]["totais"]["meses_cobertos"], len(labels))

    def test_segmentos_modalidades_e_series_alinhadas(self):
        self.assertEqual(self.d["segmentos"], SEGMENTOS)
        self.assertEqual(set(self.d["rotulos_segmento"]), set(SEGMENTOS))
        self.assertEqual(self.d["modalidades"], MODALIDADES)
        n = len(self.d["labels"])
        for seg in SEGMENTOS:
            self.assertEqual(set(self.d["series"][seg]), set(CFG["series"][seg]), seg)
            for mod, s in self.d["series"][seg].items():
                campos = {"saldo", "taxa", "spread"} if mod == "Total" else {"saldo", "taxa"}
                self.assertEqual(set(s), campos, (seg, mod))
                for campo in campos:
                    self.assertEqual(len(s[campo]), n, (seg, mod, campo))
                    for v in s[campo]:
                        self.assertTrue(v is None or (isinstance(v, (int, float)) and v >= 0), (seg, mod, campo, v))

    def test_agregados_completos_no_ultimo_mes(self):
        for seg in SEGMENTOS:
            tot = self.d["series"][seg]["Total"]
            self.assertTrue(all(tot[c][-1] is not None for c in ("saldo", "taxa", "spread")), seg)
            self.assertGreater(tot["saldo"][-1], 0)

    def test_residuo_so_nos_segmentos_com_modalidades(self):
        n = len(self.d["labels"])
        self.assertEqual(set(self.d["residuos"]), {s for s in SEGMENTOS if MODALIDADES[s]})
        for seg, r in self.d["residuos"].items():
            self.assertEqual(set(r), {"saldo", "saldo_ultimo", "part_saldo_segmento_pct"})
            self.assertEqual(len(r["saldo"]), n)
            self.assertAlmostEqual(r["saldo_ultimo"], r["saldo"][-1])

    def test_kpis_totais(self):
        t = self.d["kpis"]["totais"]
        self.assertEqual(set(t), {"mes_ref", "meses_cobertos", "saldo_total", "taxa_media_aa", "spread_medio_pp",
                                  "saldo_pf", "saldo_pj", "yoy_saldo_total_pct", "maior_saldo", "mais_cara",
                                  "mais_barata"})
        self.assertAlmostEqual(t["saldo_total"], self.d["series"]["Total"]["Total"]["saldo"][-1])
        for k in ("maior_saldo", "mais_cara", "mais_barata"):
            self.assertIn("modalidade", t[k], k)
            self.assertIn("segmento", t[k], k)

    def test_kpis_por_modalidade(self):
        campos = {"segmento", "modalidade", "saldo_ultimo", "part_saldo_segmento_pct", "taxa_ultima",
                  "taxa_media_periodo", "var_taxa_12m_pp", "yoy_saldo_pct", "cagr_saldo_aa_pct"}
        pm = self.d["kpis"]["por_modalidade"]
        self.assertEqual({(p["segmento"], p["modalidade"]) for p in pm},
                         {(s, m) for s in SEGMENTOS for m in MODALIDADES[s]})
        for p in pm:
            self.assertEqual(set(p), campos)

    def test_estatisticas(self):
        stats = {"media", "mediana", "desvio_padrao", "coef_variacao_pct", "minimo", "maximo"}
        self.assertEqual(set(self.d["estatisticas"]), set(SEGMENTOS))
        for seg in SEGMENTOS:
            self.assertEqual(set(self.d["estatisticas"][seg]), set(CFG["series"][seg]))
            for mod, e in self.d["estatisticas"][seg].items():
                self.assertEqual(set(e), {"saldo", "taxa"}, (seg, mod))
                for medida in ("saldo", "taxa"):
                    self.assertEqual(set(e[medida]), stats)


class TestCsvPublico(unittest.TestCase):
    def test_colunas_tipos_e_chave(self):
        with (DADOS_PUB / f"{SLUG}.csv").open(encoding="utf-8", newline="") as f:
            leitor = csv.DictReader(f)
            self.assertEqual(leitor.fieldnames,
                             ["ano_mes", "segmento", "modalidade_credito", "saldo", "taxa_juros_aa", "spread_pp"])
            linhas = list(leitor)
        chaves = [(l["ano_mes"], l["segmento"], l["modalidade_credito"]) for l in linhas]
        self.assertEqual(len(chaves), len(set(chaves)), "chave ano_mes+segmento+modalidade duplicada")
        self.assertEqual({(l["segmento"], l["modalidade_credito"]) for l in linhas},
                         {(s, m) for s, mods in CFG["series"].items() for m in mods})
        for l in linhas:
            self.assertRegex(l["ano_mes"], RE_ANO_MES)
            float(l["saldo"]), float(l["taxa_juros_aa"])
            if l["spread_pp"]:
                self.assertEqual(l["modalidade_credito"], "Total", "spread so existe nos agregados")
        labels = ler_json(DADOS_PUB / f"{SLUG}.json")["labels"]
        self.assertEqual(len(linhas), len(labels) * sum(len(m) for m in CFG["series"].values()))

    def test_json_e_csv_dizem_a_mesma_coisa(self):
        d = ler_json(DADOS_PUB / f"{SLUG}.json")
        with (DADOS_PUB / f"{SLUG}.csv").open(encoding="utf-8", newline="") as f:
            tidy = {(l["ano_mes"], l["segmento"], l["modalidade_credito"]): l for l in csv.DictReader(f)}
        for seg, mods in d["series"].items():
            for mod, s in mods.items():
                for i, mes in enumerate(d["labels"]):
                    lin = tidy[(mes, seg, mod)]
                    self.assertAlmostEqual(float(lin["saldo"]), s["saldo"][i], places=6)
                    self.assertAlmostEqual(float(lin["taxa_juros_aa"]), s["taxa"][i], places=6)
                    if "spread" in s:
                        self.assertAlmostEqual(float(lin["spread_pp"]), s["spread"][i], places=6)

    def test_csv_publico_igual_ao_processado(self):
        pub = ler_texto(DADOS_PUB / f"{SLUG}.csv")
        proc = ler_texto(RAIZ / "dados" / "processados" / f"{SLUG}.csv")
        self.assertEqual(pub, proc)


class TestEventos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eventos = ler_json(DADOS_PUB / f"eventos_{SLUG}.json")
        cls.labels = ler_json(DADOS_PUB / f"{SLUG}.json")["labels"]

    def test_o_js_le_estes_campos(self):
        for trecho in ("e.segmentos", "e.modalidades", "e.data", "e.titulo", "e.descricao", "e.fonte"):
            self.assertIn(trecho, JS_PAINEL)

    def test_campos_e_tipos(self):
        self.assertGreater(len(self.eventos), 5)
        for e in self.eventos:
            self.assertEqual(set(e), {"data", "titulo", "descricao", "segmentos", "modalidades", "fonte"},
                             e.get("titulo"))
            self.assertRegex(e["data"], RE_ANO_MES)
            self.assertTrue(e["titulo"].strip() and e["descricao"].strip())
            self.assertTrue(e["segmentos"] and e["modalidades"], e["titulo"])
            self.assertLessEqual(set(e["segmentos"]), {"PF", "PJ"}, e["titulo"])
            self.assertRegex(e["fonte"], r"^https?://\S+$", e["titulo"])

    def test_modalidades_existem_no_segmento_ou_sao_total(self):
        for e in self.eventos:
            for m in e["modalidades"]:
                if m == "Total":
                    continue
                self.assertTrue(all(m in MODALIDADES[s] for s in e["segmentos"]),
                                f"{e['titulo']}: {m} nao existe em {e['segmentos']}")

    def test_sem_evento_duplicado_e_em_ordem(self):
        chaves = [(e["data"], e["titulo"]) for e in self.eventos]
        self.assertEqual(len(chaves), len(set(chaves)))
        datas = [e["data"] for e in self.eventos]
        self.assertEqual(datas, sorted(datas), "eventos fora de ordem cronologica")

    def test_eventos_dentro_da_serie(self):
        # O painel mostra "Nenhum evento catalogado" quando a janela nao tem nenhum.
        dentro = [e for e in self.eventos if e["data"] in set(self.labels)]
        self.assertTrue(dentro)
        fora = [e["titulo"] for e in self.eventos if not (self.labels[0] <= e["data"] <= self.labels[-1])]
        self.assertEqual(fora, [], "evento fora do periodo da serie nunca aparece no grafico")

    def test_cada_segmento_tem_evento_para_o_foco_inicial_do_painel(self):
        foco = re.search(r'focoModalidade = "([^"]+)"', JS_PAINEL).group(1)
        rel = [e for e in self.eventos if "PF" in e["segmentos"] and (foco in e["modalidades"] or "Total" in e["modalidades"])]
        self.assertTrue(rel, f"nenhum evento para o foco inicial ({foco}) em PF")


class TestPerfilLidoPelaExploracao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = ler_json(DADOS_PUB / f"perfil_{SLUG}.json")

    def test_o_js_le_estes_campos(self):
        for trecho in ("perfil.tabelas", "perfil.relacionamentos", "perfil.cobertura_temporal",
                       "perfil.meta.fonte", "perfil.meta.gerado_em", "t.chave_primaria_valida",
                       "t.amostra", "c.pct_nulos", "r.cobertura_pct", "r.orfaos"):
            self.assertIn(trecho, JS_EXPLORAR)

    def test_meta(self):
        self.assertEqual(self.p["meta"]["slug"], SLUG)
        self.assertTrue(self.p["meta"]["fonte"])
        datetime.fromisoformat(self.p["meta"]["gerado_em"])

    def test_tabelas(self):
        tabelas = self.p["tabelas"]
        self.assertEqual([t["camada"] for t in tabelas].count("tidy"), 1)   # o resumo procura a camada tidy
        campos = {"id", "camada", "nome", "arquivo", "formato", "origem", "n_linhas", "n_colunas",
                  "granularidade", "chave_primaria", "chave_primaria_valida", "duplicatas",
                  "colunas", "amostra", "alertas"}
        for t in tabelas:
            self.assertEqual(set(t), campos, t["id"])
            self.assertEqual(len(t["colunas"]), t["n_colunas"], t["id"])
            a = t["amostra"]
            self.assertEqual(set(a), {"cabecalho", "inicio", "fim", "omitidas"})
            self.assertEqual(a["cabecalho"], [c["nome"] for c in t["colunas"]])
            for linha in a["inicio"] + a["fim"]:
                self.assertEqual(len(linha), len(a["cabecalho"]))
            for c in t["colunas"]:
                for campo in ("nome", "papel", "tipo", "unidade", "pct_nulos", "distintos"):
                    self.assertIn(campo, c, f"{t['id']}.{c['nome']}")

    def test_papeis_tem_estilo_de_selo(self):
        css = (DOCS / "css" / "estilo.css").read_text(encoding="utf-8")
        usados = {c["papel"] for t in self.p["tabelas"] for c in t["colunas"]}
        for papel in usados:
            self.assertIn(f".selo-{papel}", css, f"falta .selo-{papel} em estilo.css")

    def test_relacionamentos_e_cobertura(self):
        ids = {t["id"] for t in self.p["tabelas"]}
        for r in self.p["relacionamentos"]:
            self.assertEqual(set(r), {"de", "para", "tabela_de", "tabela_para", "cardinalidade",
                                      "cobertura_pct", "orfaos", "uso"})
            self.assertLessEqual({r["tabela_de"], r["tabela_para"]}, ids)
        cob = self.p["cobertura_temporal"]
        self.assertEqual(set(cob), {"inicio", "fim", "meses_esperados", "meses_presentes", "lacunas"})
        self.assertIsInstance(cob["lacunas"], list)
        labels = ler_json(DADOS_PUB / f"{SLUG}.json")["labels"]
        self.assertEqual((cob["inicio"], cob["fim"]), (labels[0], labels[-1]),
                         "perfil e série publicada cobrem períodos diferentes")

    def test_inventario_das_series(self):
        aux = next(t for t in self.p["tabelas"] if t["id"] == "aux_series")
        self.assertEqual(aux["n_linhas"], len(config.series_sgs(CFG)))

    def test_perfil_cabe_no_teto_da_etapa_e(self):
        self.assertLess((DADOS_PUB / f"perfil_{SLUG}.json").stat().st_size / 1024, 300)


class TestNotasLidasPelaExploracao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n = ler_json(DADOS_PUB / f"notas_{SLUG}.json")
        cls.p = ler_json(DADOS_PUB / f"perfil_{SLUG}.json")
        cls.css = (DOCS / "css" / "estilo.css").read_text(encoding="utf-8")

    def test_o_js_le_estas_secoes(self):
        for sec in ("leitura", "armadilhas", "comparativos", "contexto_externo", "cruzamentos", "pauta",
                    "perguntas_abertas"):
            self.assertRegex(JS_EXPLORAR, rf"notas\??\.{sec}", f"explorar.js deixou de ler notas.{sec}")

    def test_secoes_e_campos(self):
        n = self.n
        self.assertTrue(n["meta"]["atualizado_em"])
        for sec, campos in {
            "leitura": {"tabela_id", "texto"},
            "armadilhas": {"titulo", "texto", "impacto"},
            "comparativos": {"id", "titulo", "pergunta", "colunas", "o_que_esperar"},
            "contexto_externo": {"titulo", "resumo", "fonte", "url", "consultado_em", "por_que_importa"},
            "cruzamentos": {"com_fonte", "chave", "pergunta", "cuidado"},
            "pauta": {"id", "titulo", "pergunta", "tabela", "colunas", "tipo_grafico", "por_que_esse_tipo",
                      "status", "prioridade", "esforco"},
        }.items():
            self.assertTrue(n[sec], f"seção {sec} vazia")
            for item in n[sec]:
                self.assertLessEqual(campos, set(item), f"{sec}: {item.get('titulo') or item.get('id')}")
        self.assertTrue(all(isinstance(p, str) and p for p in n["perguntas_abertas"]))

    def test_leitura_aponta_para_tabelas_do_perfil(self):
        ids = {t["id"] for t in self.p["tabelas"]}
        self.assertLessEqual({l["tabela_id"] for l in self.n["leitura"]}, ids)

    def test_colunas_citadas_existem_na_tabela(self):
        cols = {t["id"]: {c["nome"] for c in t["colunas"]} for t in self.p["tabelas"]}
        for item in self.n["pauta"]:
            self.assertIn(item["tabela"], cols, item["id"])
            self.assertLessEqual(set(item["colunas"]), cols[item["tabela"]], item["id"])
        todas = set().union(*cols.values())
        for item in self.n["comparativos"]:
            self.assertLessEqual(set(item["colunas"]), todas, item["id"])

    def test_vocabulario_que_o_js_ordena_e_filtra(self):
        for a in self.n["armadilhas"]:
            self.assertIn(a["impacto"], {"alto", "medio", "baixo"})
        html = (DOCS / "explorar.html").read_text(encoding="utf-8")
        filtros = set(re.findall(r'class="alt-btn[^"]*" data-status="(\w+)"', html))
        ids = [p["id"] for p in self.n["pauta"]]
        self.assertEqual(len(ids), len(set(ids)), "ids de pauta repetidos")
        for p in self.n["pauta"]:
            self.assertIn(p["status"], filtros, f"{p['id']}: status sem botão de filtro")
            for campo in ("esforco", "status"):
                self.assertIn(f".selo-{p[campo]}", self.css, f"{p['id']}: {campo} sem estilo de selo")

    def test_prioridade_tem_estilo_de_selo(self):
        for p in self.n["pauta"]:
            self.assertIn(f".selo-{p['prioridade']}", self.css, f"{p['id']}: prioridade sem estilo de selo")

    def test_contexto_externo_com_url_http(self):
        for c in self.n["contexto_externo"]:
            self.assertRegex(c["url"], r"^https?://\S+$", c["titulo"])
            datetime.fromisoformat(c["consultado_em"])


if __name__ == "__main__":
    unittest.main()
