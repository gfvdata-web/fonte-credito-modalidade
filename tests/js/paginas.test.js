// Testes das páginas sem navegador: node --test tests/js
// Carrega docs/js/*.js num contexto `vm` com um DOM falso e os JSON reais de docs/dados.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const DOCS = path.resolve(__dirname, "..", "..", "docs");
const SLUG = "credito_modalidade";
const lerJson = (rel) => JSON.parse(fs.readFileSync(path.join(DOCS, rel), "utf8"));
const lerTexto = (rel) => fs.readFileSync(path.join(DOCS, rel), "utf8");

// ---------- DOM falso ----------
function elemento() {
  return {
    hidden: false, innerHTML: "", textContent: "", value: "", dataset: {}, children: [], style: {},
    parentElement: { clientWidth: 1000 },
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener() {}, setAttribute() {}, getAttribute: () => null,
    querySelector: () => elemento(), querySelectorAll: () => [],
    closest: () => null,
  };
}
function idsOcultosNoHtml(pagina) {
  const ocultos = new Set();
  for (const tag of lerTexto(pagina).match(/<[^>]+>/g) || []) {
    const id = /\bid="([^"]+)"/.exec(tag);
    if (id && /\shidden(\s|>|=|\/)/.test(tag)) ocultos.add(id[1]);
  }
  return ocultos;
}
function documentoFalso(slug, ocultos = new Set()) {
  const porId = new Map();
  return {
    porId,
    body: { dataset: { slug } },
    documentElement: elemento(),
    getElementById(id) {
      if (!porId.has(id)) { const e = elemento(); e.hidden = ocultos.has(id); porId.set(id, e); }
      return porId.get(id);
    },
    querySelector: () => elemento(),
    querySelectorAll: () => [],
  };
}
const esperar = () => new Promise((r) => setTimeout(r, 20));

// ---------- app-v2.js (painel) ----------
function carregarPainel(largura = 1200) {
  const fonte = lerTexto("js/app-v2.js");
  const semInicio = fonte.replace(/\r?\niniciar\(\);\s*$/, "\n");
  assert.notEqual(semInicio, fonte, "app-v2.js deixou de terminar com iniciar(); ajuste o teste");
  const document = documentoFalso("");
  class Chart { constructor(_ctx, cfg) { this.config = cfg; } destroy() {} static register() {} }
  const ctx = vm.createContext({
    window: { innerWidth: largura, addEventListener() {}, matchMedia: () => ({ matches: false, addEventListener() {} }) },
    document, Chart, console, Intl, Date, Math, Number, String, Array, Object, JSON, clearTimeout, setTimeout,
    getComputedStyle: () => ({ getPropertyValue: () => "#123456" }),
  });
  vm.runInContext(semInicio, ctx, { filename: "app-v2.js" });
  const publicado = lerJson(`dados/${SLUG}.json`);
  ctx.__dados = publicado;
  ctx.__eventos = lerJson(`dados/eventos_${SLUG}.json`);
  vm.runInContext("dados = __dados; eventos = __eventos; focoModalidade = 'Cartão de crédito rotativo';", ctx);
  return { ctx, document, publicado, eventos: ctx.__eventos,
           rodar: (codigo) => JSON.parse(JSON.stringify(vm.runInContext(codigo, ctx) ?? null)) };
}

test("formatação de saldo, taxa, participação e meses", () => {
  const { rodar } = carregarPainel();
  assert.equal(rodar("fmtMesAno('2020-11')"), "nov/2020");
  assert.equal(rodar("fmtMesAno('2011-03')"), "mar/2011");
  assert.equal(rodar("fmtSaldo(null)"), "—");
  assert.match(rodar("fmtSaldo(8123456)"), /^R\$ 8,12 tri$/);
  assert.match(rodar("fmtSaldo(1759678)"), /^R\$ 1,76 tri$/);
  assert.match(rodar("fmtSaldo(29333.2)"), /^R\$ 29,3 bi$/);
  assert.match(rodar("fmtSaldo(500)"), /^R\$ 500 mi$/);
  assert.equal(rodar("fmtTaxa(null)"), "—");
  assert.equal(rodar("fmtTaxa(39.44)"), "39,4%");
  assert.equal(rodar("fmtPct(null)"), "—");
  assert.equal(rodar("fmtPct(95.04)"), "95,0%");
  assert.equal(rodar("fmtPP(null)"), "—");
  assert.match(rodar("fmtPP(2.5)"), /^\+2,5 p\.p\.$/);
  assert.match(rodar("fmtPP(-1.25, 2)"), /^-1,25 p\.p\.$/);
  assert.equal(rodar("fmtCampo('saldo', 500)"), "R$ 500 mi");
  assert.equal(rodar("fmtCampo('taxa', 10)"), "10,0%");
});

test("períodos 10A/5A/1A/tudo viram índices sobre as labels", () => {
  const { rodar, publicado } = carregarPainel();
  const ultimo = publicado.labels.length - 1;
  assert.deepEqual(rodar("periodoParaIndices('tudo')"), [0, ultimo]);
  assert.deepEqual(rodar("periodoParaIndices('10a')"), [ultimo - 119, ultimo]);
  assert.deepEqual(rodar("periodoParaIndices('5a')"), [ultimo - 59, ultimo]);
  assert.deepEqual(rodar("periodoParaIndices('1a')"), [ultimo - 11, ultimo]);
});

test("granularidade do gráfico de participação respeita o limite de colunas", () => {
  const { rodar } = carregarPainel();
  assert.equal(rodar("escolherGranularidade(12, 25).codigo"), "mensal");
  assert.equal(rodar("escolherGranularidade(60, 25).codigo"), "trimestral");
  assert.equal(rodar("escolherGranularidade(120, 25).codigo"), "semestral");
  const g = rodar("escolherGranularidade(184, 10)");           // tela pequena, série longa
  assert.ok(["anual", "multianual"].includes(g.codigo));
  for (const meses of [1, 7, 12, 36, 60, 120, 184, 400]) {
    for (const max of [10, 25]) {
      const o = rodar(`escolherGranularidade(${meses}, ${max})`);
      const passo = { mensal: 1, trimestral: 3, semestral: 6, anual: 12 }[o.codigo];
      const colunas = passo ? Math.ceil(meses / passo) : Math.ceil(Math.ceil(meses / 12) / o.anosPorBloco);
      assert.ok(colunas <= max, `${meses} meses / máx ${max} -> ${colunas} colunas (${o.codigo})`);
    }
  }
});

test("a largura da tela muda o limite de colunas (mobile 10, desktop 25)", () => {
  assert.equal(carregarPainel(1200).rodar("maxColunasTela()"), 25);
  assert.equal(carregarPainel(375).rodar("maxColunasTela()"), 10);
});

test("a participação soma 100% em cada período, granularidade e segmento", () => {
  const { rodar, publicado } = carregarPainel();
  const ultimo = publicado.labels.length - 1;
  for (const seg of ["PF", "PJ"]) {
    rodar(`segmento = '${seg}'`);
    const itens = rodar("listaParticipacao(segmento)");
    assert.equal(itens.length, 6, "top 5 + Outras modalidades");
    assert.equal(itens[5].nome, publicado.rotulo_residuo);
    for (const gran of ["{codigo:'mensal'}", "{codigo:'trimestral'}", "{codigo:'semestral'}", "{codigo:'anual'}",
                        "{codigo:'multianual',anosPorBloco:5}"]) {
      const r = rodar(`agregarParticipacaoPorPeriodo(${ultimo - 59}, ${ultimo}, listaParticipacao(segmento), ${gran})`);
      assert.ok(r.periodos.length >= 1);
      r.periodos.forEach((_, i) => {
        const soma = itens.reduce((s, it) => s + (r.share[it.nome][i] ?? 0), 0);
        assert.ok(Math.abs(soma - 100) < 1e-6, `${seg} ${gran} período ${i}: ${soma}`);
      });
    }
  }
  const tri = rodar(`agregarParticipacaoPorPeriodo(${ultimo - 59}, ${ultimo}, listaParticipacao('PF'), {codigo:'trimestral'})`);
  assert.ok([20, 21].includes(tri.periodos.length), `${tri.periodos.length} trimestres`);
});

test("participação usa o saldo do último mês do período (estoque), nunca a soma de meses", () => {
  const { rodar, publicado } = carregarPainel();
  const ultimo = publicado.labels.length - 1;
  const itens = rodar("listaParticipacao('PF')");
  const r = rodar(`agregarParticipacaoPorPeriodo(${ultimo}, ${ultimo}, listaParticipacao('PF'), {codigo:'mensal'})`);
  assert.deepEqual(r.periodos.length, 1);
  const total = itens.reduce((s, it) => s + (it.saldo[ultimo] ?? 0), 0);
  itens.forEach((it) => {
    assert.ok(Math.abs(r.share[it.nome][0] - ((it.saldo[ultimo] ?? 0) / total) * 100) < 1e-9, it.nome);
  });
  // "Outras modalidades" fecha o saldo do segmento: o total das fatias é o saldo Total do segmento
  assert.ok(Math.abs(total - publicado.series.PF.Total.saldo[ultimo]) < 1e-3 * total / 1000 + 1,
            `fatias ${total} x saldo PF ${publicado.series.PF.Total.saldo[ultimo]}`);
});

test("top 5 do painel bate com o ranking publicado em kpis.por_modalidade", () => {
  const { rodar, publicado } = carregarPainel();
  for (const seg of ["PF", "PJ"]) {
    const esperado = publicado.kpis.por_modalidade.filter((m) => m.segmento === seg)
      .sort((a, b) => b.saldo_ultimo - a.saldo_ultimo).slice(0, 5).map((m) => m.modalidade);
    assert.deepEqual(rodar(`topModalidades('${seg}')`), esperado);
  }
});

test("CAGR do JS bate com o cagr_saldo_aa_pct publicado pelo Python", () => {
  const { rodar, publicado } = carregarPainel();
  const ultimo = publicado.labels.length - 1;
  let comparados = 0;
  for (const p of publicado.kpis.por_modalidade) {
    const js = rodar(`cagrAA(dados.series['${p.segmento}']['${p.modalidade}'].saldo, 0, ${ultimo})`);
    if (p.cagr_saldo_aa_pct == null) assert.equal(js, null, p.modalidade);
    else { assert.ok(Math.abs(js - p.cagr_saldo_aa_pct) < 1e-6, `${p.modalidade}: js ${js} vs py ${p.cagr_saldo_aa_pct}`); comparados++; }
  }
  assert.ok(comparados >= 20);
  assert.equal(rodar("cagrAA([0, 0, 5, null], 0, 3)"), null);   // um único valor positivo
});

test("variação anual da taxa (p.p./ano) usa primeiro e último valor da janela", () => {
  const { rodar } = carregarPainel();
  const v = rodar("variacaoAnualPP([10, null, 12, 14, null, 22], 0, 5)");
  assert.equal(v.ini, 10);
  assert.equal(v.fim, 22);
  assert.ok(Math.abs(v.pp - (12 / (5 / 12))) < 1e-9);
  assert.equal(rodar("variacaoAnualPP([null, 5], 0, 1)"), null);
});

test("frase de abertura cita as modalidades mais cara e mais barata publicadas", () => {
  const { rodar, document, publicado } = carregarPainel();
  rodar("renderNarrativaAbertura()");
  const html = document.getElementById("txt-abertura").innerHTML;
  const t = publicado.kpis.totais;
  assert.ok(html.includes(`<strong>${t.mais_cara.modalidade}</strong>`));
  assert.ok(html.includes(`<strong>${t.mais_barata.modalidade}</strong>`));
  assert.ok(html.includes(rodar(`fmtSaldo(${t.saldo_total})`)));
  assert.match(html, /vezes mais que a mais barata/);
});

test("rodapé cita a fonte e o fim do período", () => {
  const { rodar, document, publicado } = carregarPainel();
  rodar("renderCabecalho()");
  const txt = document.getElementById("rodape-fonte-v2").textContent;
  assert.ok(txt.includes(publicado.meta.fonte));
  assert.ok(txt.includes(rodar(`fmtMesAno('${publicado.meta.periodo.fim}')`)));
});

test("narrativa do meio (participação) nunca fica vazia", () => {
  const { rodar, document, publicado } = carregarPainel();
  const ultimo = publicado.labels.length - 1;
  for (const seg of ["PF", "PJ"]) {
    for (const [i0, g] of [[ultimo - 119, "{codigo:'semestral'}"], [ultimo, "{codigo:'mensal'}"]]) {
      rodar(`segmento = '${seg}'; itensTeste = listaParticipacao(segmento);
             resTeste = agregarParticipacaoPorPeriodo(${i0}, ${ultimo}, itensTeste, ${g});
             renderNarrativaMeio(resTeste.periodos, resTeste.share, ${g}, itensTeste)`);
      const html = document.getElementById("txt-meio").innerHTML;
      assert.ok(html.length > 40, `${seg} ${g}: "${html}"`);
      assert.match(html, /<strong>/);
    }
  }
});

test("narrativa de fechamento calcula crescimento (saldo) e variação (taxa) do foco", () => {
  const { rodar, document, publicado } = carregarPainel();
  const ultimo = publicado.labels.length - 1;
  const foco = rodar("topModalidades('PF')[0]");
  rodar(`segmento = 'PF'; focoModalidade = '${foco}'; evoMetrica = 'saldo';
         renderNarrativaFechamento(${ultimo - 59}, ${ultimo}, listaEvolucao('PF'))`);
  assert.match(document.getElementById("txt-fechamento").innerHTML,
    new RegExp(`saldo de <strong>${foco}</strong> (cresceu|recuou) a uma taxa média`));
  rodar(`evoMetrica = 'taxa'; renderNarrativaFechamento(${ultimo - 59}, ${ultimo}, listaEvolucao('PF'))`);
  assert.match(document.getElementById("txt-fechamento").innerHTML,
    new RegExp(`taxa de juros de <strong>${foco}</strong> (subiu|caiu) .* p\.p\. ao ano`));
});

test("foco fora do top 5 cai para a primeira modalidade em vez de quebrar", () => {
  const { rodar } = carregarPainel();
  rodar("segmento = 'PF'; focoModalidade = 'Modalidade inexistente'; montarPilulasModalidade()");
  assert.equal(rodar("focoModalidade"), rodar("topModalidades('PF')[0]"));
});

test("renderiza os dois gráficos e as tabelas com os dados reais (Chart simulado)", () => {
  const { rodar } = carregarPainel();
  for (const seg of ["PF", "PJ"]) {
    for (const metrica of ["taxa", "saldo"]) {
      rodar(`segmento = '${seg}'; focoModalidade = null; evoMetrica = '${metrica}';
             montarPilulasModalidade(); renderGraficoParticipacao(); renderGraficoEvolucao();`);
      const ds = rodar("graficoParticipacao.config.data.datasets.length");
      assert.equal(ds, 6);
      assert.equal(rodar("graficoEvolucao.config.data.datasets.length"), 5);
    }
  }
});

// ---------- filtro de eventos ----------
test("eventos do gráfico respeitam segmento, modalidade em foco (ou Total) e janela", () => {
  const { rodar, publicado, eventos } = carregarPainel();
  const labels = publicado.labels;
  const todos = JSON.stringify(labels);
  const ids = (lista) => lista.map((e) => `${e.data}|${e.titulo}`);

  rodar("segmento = 'PF'; focoModalidade = 'Cartão de crédito rotativo'");
  const esperadoPF = eventos.filter((e) => e.segmentos.includes("PF")
    && (e.modalidades.includes("Cartão de crédito rotativo") || e.modalidades.includes("Total")))
    .sort((a, b) => a.data.localeCompare(b.data));
  assert.deepEqual(ids(rodar(`eventosEmFoco(${todos})`)), ids(esperadoPF));
  assert.ok(esperadoPF.length >= 3);

  // evento só de PJ não aparece em PF
  const soPJ = eventos.find((e) => e.segmentos.length === 1 && e.segmentos[0] === "PJ");
  assert.ok(soPJ);
  assert.ok(!ids(rodar(`eventosEmFoco(${todos})`)).includes(`${soPJ.data}|${soPJ.titulo}`));
  rodar("segmento = 'PJ'; focoModalidade = 'Capital de giro'");
  assert.ok(ids(rodar(`eventosEmFoco(${todos})`)).includes(`${soPJ.data}|${soPJ.titulo}`) || !soPJ.modalidades.includes("Capital de giro") && !soPJ.modalidades.includes("Total"));

  // modalidade específica de outra modalidade não aparece
  rodar("segmento = 'PF'; focoModalidade = 'Cheque especial'");
  const cheque = ids(rodar(`eventosEmFoco(${todos})`));
  const soConsignado = eventos.find((e) => e.segmentos.includes("PF") && !e.modalidades.includes("Total")
    && !e.modalidades.includes("Cheque especial"));
  if (soConsignado) assert.ok(!cheque.includes(`${soConsignado.data}|${soConsignado.titulo}`));

  // janela: só os rótulos visíveis
  rodar("segmento = 'PF'; focoModalidade = 'Cartão de crédito rotativo'");
  const janela = JSON.stringify(labels.slice(-12));
  for (const e of rodar(`eventosEmFoco(${janela})`)) assert.ok(labels.slice(-12).includes(e.data));
  assert.deepEqual(rodar("eventosEmFoco([])"), []);
});

test("lista de eventos renderiza com fonte e mostra aviso quando a janela é vazia", () => {
  const { rodar, document, publicado } = carregarPainel();
  rodar("segmento = 'PF'; focoModalidade = 'Cartão de crédito rotativo'");
  rodar(`renderNarrativaEventos(${JSON.stringify(publicado.labels)})`);
  const html = document.getElementById("eventos-linha-tempo").innerHTML;
  assert.match(html, /class="evento-item"/);
  assert.match(html, /Fonte ↗/);
  assert.match(html, /O que pode explicar a trajetória de Cartão de crédito rotativo/);
  rodar("renderNarrativaEventos([])");
  assert.match(document.getElementById("eventos-linha-tempo").innerHTML, /Nenhum evento catalogado/);
});

test("anotações do gráfico: uma linha por evento visível, com rótulo curto", () => {
  const { rodar, publicado } = carregarPainel();
  rodar("segmento = 'PF'; focoModalidade = 'Cartão de crédito rotativo'");
  const labels = JSON.stringify(publicado.labels);
  const n = rodar(`eventosEmFoco(${labels}).length`);
  const anot = rodar(`construirAnotacoesEventos(${labels})`);
  assert.equal(Object.keys(anot).length, n);
  for (const a of Object.values(anot)) assert.ok(a.label.content.length <= 28);
  assert.equal(rodar("rotuloCurto('abc', 28)"), "abc");
  assert.equal(rodar("rotuloCurto('x'.repeat(40), 28)").length, 28);
});

test("textos vindos do JSON são escapados antes de entrar em innerHTML", () => {
  const { rodar } = carregarPainel();
  assert.equal(rodar("esc('<b>&\"')"), "&lt;b&gt;&amp;&quot;");
  assert.equal(rodar("esc(null)"), "");
});

// ---------- explorar.js (exploração) ----------
async function rodarExploracao({ semPerfil = false, semNotas = false } = {}) {
  const document = documentoFalso(SLUG, idsOcultosNoHtml("explorar.html"));
  const pedidos = [];
  const fetch = async (url) => {
    pedidos.push(url);
    const ausente = (semPerfil && url.includes("perfil_")) || (semNotas && url.includes("notas_"));
    if (ausente || !fs.existsSync(path.join(DOCS, url))) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => lerJson(url) };
  };
  const ctx = vm.createContext({ document, fetch, console, Intl, Number, String, Object, Array, JSON, Set });
  vm.runInContext(lerTexto("js/explorar.js"), ctx, { filename: "explorar.js" });
  for (let i = 0; i < 5; i++) await esperar();
  return { document, pedidos, el: (id) => document.getElementById(id) };
}

test("exploração renderiza perfil e notas reais", async () => {
  const { el, pedidos } = await rodarExploracao();
  const perfil = lerJson(`dados/perfil_${SLUG}.json`);
  const notas = lerJson(`dados/notas_${SLUG}.json`);
  assert.deepEqual(pedidos, [`dados/perfil_${SLUG}.json`, `dados/notas_${SLUG}.json`]);
  assert.match(el("resumo").innerHTML, /Tabelas perfiladas/);
  assert.match(el("resumo").innerHTML, new RegExp(`${perfil.cobertura_temporal.inicio} → ${perfil.cobertura_temporal.fim}`));
  assert.equal(el("erro").hidden, true, "o aviso de erro não deve aparecer quando o perfil carrega");
  for (const sec of ["sec-mapa", "sec-cobertura", "sec-armadilhas", "sec-comparativos", "sec-contexto",
                     "sec-cruzamentos", "sec-pauta", "sec-perguntas"]) {
    assert.equal(el(sec).hidden, false, `${sec} deveria ter sido exibida`);
  }
  assert.equal((el("tabelas").innerHTML.match(/<details class="bloco-tabela"/g) || []).length, perfil.tabelas.length);
  assert.equal((el("armadilhas").innerHTML.match(/class="mini-cartao"/g) || []).length, notas.armadilhas.length);
  assert.equal((el("perguntas").innerHTML.match(/<li>/g) || []).length, notas.perguntas_abertas.length);
  assert.match(el("meta-info").textContent, /perfil gerado em/);
  assert.match(el("rodape-perfil").textContent, new RegExp(`perfil_${SLUG}\\.json`));
});

test("exploração sem perfil mostra o aviso de erro", async () => {
  const { el } = await rodarExploracao({ semPerfil: true });
  assert.equal(el("erro").hidden, false);
  assert.match(el("meta-info").textContent, /Falha ao carregar/);
});

test("exploração sem notas funciona só com a metade medida", async () => {
  const { el } = await rodarExploracao({ semNotas: true });
  assert.match(el("resumo").innerHTML, /sem notas curadas/);
  assert.equal(el("sec-mapa").hidden, false);
  assert.equal(el("sec-pauta").hidden, true, "sem notas, a pauta continua oculta");
  assert.equal(el("sec-armadilhas").hidden, true);
});
