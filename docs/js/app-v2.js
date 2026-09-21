/* ===== Crédito por modalidade — v2 (experimental) =====
   Consome o mesmo dados/credito_modalidade.json da v1, mas com layout,
   narrativa e gráficos próprios. Nada aqui é compartilhado com js/app.js.

   Cuidado que a v1 e as notas da fonte (dados/notas_credito_modalidade.json,
   armadilha "Estoque e fluxo na mesma linha") já documentam: saldo é estoque
   (posição de fim de mês), não flui. Nunca somar saldo de meses diferentes —
   por isso toda agregação por período aqui usa o valor do último mês do
   bucket (saldo) ou a média simples (taxa), nunca soma. */

const ARQUIVO_DADOS = "dados/credito_modalidade.json";
const ARQUIVO_NOTAS = "dados/notas_credito_modalidade.json";

const SERIE_VAR = ["--s1", "--s2", "--s3", "--s4", "--s5"];
const N_TOP = 5;
const PERIODOS = [
  { codigo: "tudo", rotulo: "Desde sempre" },
  { codigo: "10a", rotulo: "10A" },
  { codigo: "5a", rotulo: "5A" },
  { codigo: "1a", rotulo: "1A" },
];

let dados = null;
let contextoExterno = [];
let graficoParticipacao = null;
let graficoEvolucao = null;

let segmento = "PF";          // "PF" | "PJ"
let participPeriodo = "10a";
let evoMetrica = "taxa";      // "taxa" | "saldo"
let evoPeriodo = "5a";
let focoModalidade = null;

// ---------- Formatação (mesmas convenções da v1, ver js/app.js) ----------
const nf = (casas = 1) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const fmtMesAno = (anoMes) => { const [a, m] = anoMes.split("-"); return `${MESES[Number(m) - 1]}/${a}`; };
const fmtPct = (x, casas = 1) => (x == null ? "—" : `${nf(casas).format(x)}%`);
const fmtTaxa = (x) => (x == null ? "—" : `${nf(1).format(x)}%`);
function fmtSaldo(x) {
  if (x == null) return "—";
  const abs = Math.abs(x);
  if (abs >= 1e6) return `R$ ${nf(2).format(x / 1e6)} tri`;
  if (abs >= 1e3) return `R$ ${nf(1).format(x / 1e3)} bi`;
  return `R$ ${nf(0).format(x)} mi`;
}
function fmtPP(x, casas = 1) {
  if (x == null) return "—";
  return `${x > 0 ? "+" : ""}${nf(casas).format(x)} p.p.`;
}
function fmtCampo(campo, x) { return campo === "saldo" ? fmtSaldo(x) : fmtTaxa(x); }
const rotuloMetrica = (campo) => (campo === "saldo" ? "saldo" : "taxa de juros");
const rotuloSegmento = (seg) => dados.rotulos_segmento[seg];
const cssVar = (nome) => getComputedStyle(document.body).getPropertyValue(nome).trim();
const num = (x) => (x == null ? 0 : x);

function corSerie(idx) { return idx < N_TOP ? cssVar(SERIE_VAR[idx]) : cssVar("--s-outras"); }

function pilulaModalidade(nome, cor) {
  return `<span class="pilula-forma"><span class="ponto-v2" style="background:${cor}"></span>${nome}</span>`;
}

/** Top 5 modalidades do segmento por saldo mais recente (dados.kpis.por_modalidade). */
function topModalidades(seg) {
  return dados.kpis.por_modalidade
    .filter((r) => r.segmento === seg)
    .sort((a, b) => b.saldo_ultimo - a.saldo_ultimo)
    .slice(0, N_TOP)
    .map((r) => r.modalidade);
}

/** Soma, mês a mês, o saldo das modalidades fora do top 5 + o resíduo publicado pelo BCB
 *  (dados.residuos[seg], que é Total do segmento menos a soma das modalidades nomeadas —
 *  ver dados/notas_credito_modalidade.json). Somar saldo *entre modalidades no mesmo mês*
 *  é válido (não há dupla contagem); a armadilha é somar entre meses. */
function serieSaldoOutras(seg, topo) {
  const n = dados.labels.length;
  const soma = dados.residuos[seg].saldo.slice();
  Object.keys(dados.series[seg]).forEach((mod) => {
    if (mod === "Total" || topo.includes(mod)) return;
    const s = dados.series[seg][mod].saldo;
    for (let i = 0; i < n; i++) soma[i] = num(soma[i]) + num(s[i]);
  });
  return soma;
}

/** Lista para o gráfico de participação: top 5 + "Outras modalidades" (só saldo, sempre existe). */
function listaParticipacao(seg) {
  const topo = topModalidades(seg);
  const itens = topo.map((mod, i) => ({ nome: mod, cor: corSerie(i), saldo: dados.series[seg][mod].saldo }));
  itens.push({ nome: dados.rotulo_residuo, cor: corSerie(N_TOP), saldo: serieSaldoOutras(seg, topo) });
  return itens;
}

/** Lista para a linha do tempo: só o top 5 (a taxa de juros não existe para o resíduo). */
function listaEvolucao(seg) {
  return topModalidades(seg).map((mod, i) => ({
    nome: mod, cor: corSerie(i),
    saldo: dados.series[seg][mod].saldo, taxa: dados.series[seg][mod].taxa,
  }));
}

/** Converte um código de período em índices [i0, i1] sobre dados.labels. */
function periodoParaIndices(codigo) {
  const last = dados.labels.length - 1;
  if (codigo === "10a") return [Math.max(0, last - 119), last];
  if (codigo === "5a") return [Math.max(0, last - 59), last];
  if (codigo === "1a") return [Math.max(0, last - 11), last];
  return [0, last]; // "tudo"
}

/** CAGR anual (%) entre o 1º e o último valor positivo da série dentro de [i0, i1]. Só faz
 *  sentido para saldo (estoque comparável ponta a ponta), nunca para taxa. */
function cagrAA(serie, i0, i1) {
  let iPrim = -1, iUlt = -1;
  for (let k = i0; k <= i1; k++) {
    if (serie[k] != null && serie[k] > 0) { if (iPrim < 0) iPrim = k; iUlt = k; }
  }
  if (iPrim < 0 || iUlt === iPrim) return null;
  const v0 = serie[iPrim], vn = serie[iUlt];
  const anos = (iUlt - iPrim) / 12;
  if (anos <= 0 || v0 <= 0) return null;
  return ((vn / v0) ** (1 / anos) - 1) * 100;
}

/** Variação média anual (p.p./ano) entre o 1º e o último valor da série em [i0, i1].
 *  Usada para taxa: uma taxa não "cresce" como um estoque, ela sobe ou desce em pontos. */
function variacaoAnualPP(serie, i0, i1) {
  let iPrim = -1, iUlt = -1;
  for (let k = i0; k <= i1; k++) {
    if (serie[k] != null) { if (iPrim < 0) iPrim = k; iUlt = k; }
  }
  if (iPrim < 0 || iUlt === iPrim) return null;
  const anos = (iUlt - iPrim) / 12;
  if (anos <= 0) return null;
  return { pp: (serie[iUlt] - serie[iPrim]) / anos, ini: serie[iPrim], fim: serie[iUlt] };
}

/** Nº máximo de colunas legíveis na tela atual (mobile: 10, desktop: 25). */
function maxColunasTela() {
  return window.innerWidth < 760 ? 10 : 25;
}

const ROTULO_GRANULARIDADE = {
  mensal: "mês", trimestral: "trimestre", semestral: "semestre",
  anual: "ano", multianual: "período",
};

/** Escolhe a granularidade (mensal/trimestral/semestral/anual/blocos de N anos) mais próxima de
 *  ~20 colunas — o "ponto ideal" de leitura — sem nunca estourar o limite de colunas da tela. */
function escolherGranularidade(qtdMeses, maxColunas) {
  const ALVO_COLUNAS = 20;
  const ESCADA = [
    { codigo: "mensal", meses: 1 },
    { codigo: "trimestral", meses: 3 },
    { codigo: "semestral", meses: 6 },
    { codigo: "anual", meses: 12 },
  ];
  const bucketIdeal = qtdMeses / ALVO_COLUNAS;

  let escolha = ESCADA.reduce((melhor, o) =>
    Math.abs(o.meses - bucketIdeal) < Math.abs(melhor.meses - bucketIdeal) ? o : melhor, ESCADA[0]);
  if (Math.ceil(qtdMeses / escolha.meses) <= maxColunas) return escolha;

  const maisGrossa = ESCADA.filter((o) => o.meses > escolha.meses)
    .find((o) => Math.ceil(qtdMeses / o.meses) <= maxColunas);
  if (maisGrossa) return maisGrossa;

  const anos = Math.ceil(qtdMeses / 12);
  const anosPorBloco = Math.ceil(anos / maxColunas);
  return { codigo: "multianual", anosPorBloco };
}

/** Participação (%) de cada modalidade no saldo do segmento, por período. Como saldo é estoque,
 *  cada bucket usa o saldo do ÚLTIMO mês do bucket (uma "foto"), nunca a soma dos meses. */
function agregarParticipacaoPorPeriodo(i0, i1, itens, granularidade) {
  const anoAncora = Number(dados.labels[i0].slice(0, 4));
  const periodos = [];
  const rotulos = {};
  const ultimoIndicePorPeriodo = {};
  for (let k = i0; k <= i1; k++) {
    const label = dados.labels[k];
    const ano = Number(label.slice(0, 4));
    const mes = Number(label.slice(5, 7));
    let chave, rotulo;
    if (granularidade.codigo === "mensal") {
      chave = `${ano}-${mes}`; rotulo = fmtMesAno(label);
    } else if (granularidade.codigo === "trimestral") {
      const t = Math.floor((mes - 1) / 3) + 1;
      chave = `${ano}-T${t}`; rotulo = `${t}º/${String(ano).slice(2)}`;
    } else if (granularidade.codigo === "semestral") {
      const s = Math.floor((mes - 1) / 6) + 1;
      chave = `${ano}-S${s}`; rotulo = `S${s}/${String(ano).slice(2)}`;
    } else if (granularidade.codigo === "anual") {
      chave = `${ano}`; rotulo = `${ano}`;
    } else {
      const bloco = Math.floor((ano - anoAncora) / granularidade.anosPorBloco);
      const anoIni = anoAncora + bloco * granularidade.anosPorBloco;
      const anoFim = anoIni + granularidade.anosPorBloco - 1;
      chave = `B${bloco}`; rotulo = granularidade.anosPorBloco > 1 ? `${anoIni}–${anoFim}` : `${anoIni}`;
    }
    if (!(chave in ultimoIndicePorPeriodo)) { periodos.push(chave); rotulos[chave] = rotulo; }
    ultimoIndicePorPeriodo[chave] = k; // sempre sobrescreve: fica o último mês do bucket
  }
  const rotulosOrdenados = periodos.map((p) => rotulos[p]);
  const share = {};
  itens.forEach((it) => { share[it.nome] = []; });
  periodos.forEach((p) => {
    const k = ultimoIndicePorPeriodo[p];
    const total = itens.reduce((s, it) => s + num(it.saldo[k]), 0);
    itens.forEach((it) => {
      share[it.nome].push(total ? (num(it.saldo[k]) / total) * 100 : null);
    });
  });
  return { periodos: rotulosOrdenados, share };
}

// ---------- Renderização: cabeçalho ----------
function renderCabecalho() {
  const meta = dados.meta;
  document.getElementById("rodape-fonte-v2").textContent =
    `Fonte: ${meta.fonte}. Atualizado em ${new Date(meta.gerado_em).toLocaleDateString("pt-BR")}.`;
}

// ---------- Narrativa ----------
function renderNarrativaAbertura() {
  const t = dados.kpis.totais;
  const razao = t.mais_barata.taxa_ultima > 0 ? Math.round(t.mais_cara.taxa_ultima / t.mais_barata.taxa_ultima) : null;
  document.getElementById("txt-abertura").innerHTML =
    `O crédito no Brasil soma <strong>${fmtSaldo(t.saldo_total)}</strong> em ${fmtMesAno(t.mes_ref)}. `
    + `A modalidade mais cara do sistema, <strong>${t.mais_cara.modalidade}</strong> (${rotuloSegmento(t.mais_cara.segmento)}), `
    + `custa <strong>${fmtTaxa(t.mais_cara.taxa_ultima)}</strong> ao ano`
    + (razao ? ` — ${razao} vezes mais que a mais barata, <strong>${t.mais_barata.modalidade}</strong> `
      + `(${rotuloSegmento(t.mais_barata.segmento)}, ${fmtTaxa(t.mais_barata.taxa_ultima)}).` : ".");
}

function renderNarrativaMeio(periodos, share, granularidade, itens) {
  const alvo = document.getElementById("txt-meio");
  if (periodos.length < 2) {
    const ultimos = itens
      .map((it) => ({ nome: it.nome, pct: share[it.nome][share[it.nome].length - 1] }))
      .filter((x) => x.pct != null)
      .sort((a, b) => b.pct - a.pct);
    const [top1, top2] = ultimos;
    alvo.innerHTML = top1
      ? `No(a) ${ROTULO_GRANULARIDADE[granularidade.codigo]} ${periodos[0] || "—"}, o saldo de <strong>${top1.nome}</strong> `
        + `liderava a carteira ${rotuloSegmento(segmento).toLowerCase()} com ${fmtPct(top1.pct)}`
        + (top2 ? `, seguido por <strong>${top2.nome}</strong> (${fmtPct(top2.pct)})` : "") + "."
      : "Sem dados suficientes no período selecionado.";
    return;
  }
  const iIni = 0, iFim = periodos.length - 1;
  let maiorGanho = null, maiorPerda = null;
  itens.forEach((it) => {
    const ini = share[it.nome][iIni], fim = share[it.nome][iFim];
    if (ini == null || fim == null) return;
    const delta = fim - ini;
    if (!maiorGanho || delta > maiorGanho.delta) maiorGanho = { nome: it.nome, ini, fim, delta };
    if (!maiorPerda || delta < maiorPerda.delta) maiorPerda = { nome: it.nome, ini, fim, delta };
  });
  if (!maiorGanho) { alvo.textContent = "Sem dados suficientes no período selecionado."; return; }
  alvo.innerHTML =
    `Entre ${periodos[iIni]} e ${periodos[iFim]}, a participação de <strong>${maiorGanho.nome}</strong> `
    + `no saldo ${rotuloSegmento(segmento).toLowerCase()} passou de ${fmtPct(maiorGanho.ini)} para ${fmtPct(maiorGanho.fim)}`
    + (maiorPerda && maiorPerda.nome !== maiorGanho.nome
      ? `, enquanto <strong>${maiorPerda.nome}</strong> perdeu espaço: de ${fmtPct(maiorPerda.ini)} para ${fmtPct(maiorPerda.fim)}.`
      : ".");
}

function renderNarrativaFechamento(i0, i1, itens) {
  const alvo = document.getElementById("txt-fechamento");
  const periodo = `de ${fmtMesAno(dados.labels[i0])} a ${fmtMesAno(dados.labels[i1])}`;

  if (evoMetrica === "saldo") {
    const ranking = itens
      .map((it) => ({ nome: it.nome, cagr: cagrAA(it.saldo, i0, i1) }))
      .filter((x) => x.cagr != null);
    const foco = ranking.find((x) => x.nome === focoModalidade);
    if (!foco) { alvo.textContent = `Não há variação suficiente no período selecionado para calcular o crescimento de ${focoModalidade}.`; return; }
    const contraste = ranking.find((x) => x.nome !== foco.nome);
    alvo.innerHTML =
      `No período ${periodo}, o saldo de <strong>${foco.nome}</strong> `
      + `${foco.cagr >= 0 ? "cresceu" : "recuou"} a uma taxa média de ${fmtPct(Math.abs(foco.cagr), 1)} ao ano`
      + (contraste
        ? `, enquanto <strong>${contraste.nome}</strong> ${contraste.cagr >= 0 ? "avançou" : "recuou"} `
          + `${fmtPct(Math.abs(contraste.cagr), 1)} ao ano no mesmo período.`
        : ".");
    return;
  }

  const ranking = itens
    .map((it) => ({ nome: it.nome, v: variacaoAnualPP(it.taxa, i0, i1) }))
    .filter((x) => x.v != null);
  const foco = ranking.find((x) => x.nome === focoModalidade);
  if (!foco) { alvo.textContent = `Não há variação suficiente no período selecionado para calcular a taxa de ${focoModalidade}.`; return; }
  const contraste = ranking.find((x) => x.nome !== foco.nome);
  alvo.innerHTML =
    `No período ${periodo}, a taxa de juros de <strong>${foco.nome}</strong> `
    + `${foco.v.pp >= 0 ? "subiu" : "caiu"} ${fmtPP(Math.abs(foco.v.pp))} ao ano `
    + `(de ${fmtTaxa(foco.v.ini)} para ${fmtTaxa(foco.v.fim)})`
    + (contraste
      ? `, enquanto <strong>${contraste.nome}</strong> ${contraste.v.pp >= 0 ? "subiu" : "caiu"} `
        + `${fmtPP(Math.abs(contraste.v.pp))} ao ano no mesmo período.`
      : ".");
}

// ---------- Gráfico 1: participação por período, granularidade automática (colunas empilhadas) ----------
function renderGraficoParticipacao() {
  const itens = listaParticipacao(segmento);
  const [i0, i1] = periodoParaIndices(participPeriodo);
  const granularidade = escolherGranularidade(i1 - i0 + 1, maxColunasTela());
  const { periodos, share } = agregarParticipacaoPorPeriodo(i0, i1, itens, granularidade);

  document.getElementById("desc-participacao").textContent =
    `Fatia de cada modalidade no saldo da carteira ${rotuloSegmento(segmento).toLowerCase()}, `
    + `no fim de cada ${ROTULO_GRANULARIDADE[granularidade.codigo]} `
    + `(${periodos[0] || "—"} a ${periodos[periodos.length - 1] || "—"}).`;

  const ctx = document.getElementById("gParticipacaoAno");
  const datasets = itens.map((it) => ({
    label: it.nome,
    data: share[it.nome],
    backgroundColor: it.cor,
    maxBarThickness: 46,
  }));

  const PX_POR_GRUPO = 34;
  const wrapper = document.getElementById("participacaoScrollInner");
  const larguraMinima = periodos.length * PX_POR_GRUPO;
  const larguraContainer = wrapper.parentElement.clientWidth;
  wrapper.style.width = larguraMinima > larguraContainer ? `${larguraMinima}px` : "100%";

  if (graficoParticipacao) graficoParticipacao.destroy();
  graficoParticipacao = new Chart(ctx, {
    type: "bar",
    data: { labels: periodos, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: cssVar("--texto"), usePointStyle: true, boxWidth: 8, font: { family: "IBM Plex Sans" } } },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: {
            title: (items) => items[0]?.label ?? "",
            label: (i) => `${i.dataset.label}: ${fmtPct(i.parsed.y)}`,
          },
        },
      },
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, ticks: { color: cssVar("--texto-suave"), autoSkip: true, maxRotation: 0 }, grid: { display: false } },
        y: {
          stacked: true, beginAtZero: true, max: 100,
          ticks: { color: cssVar("--texto-suave"), callback: (v) => `${v}%` },
          grid: { color: cssVar("--borda") },
        },
      },
    },
  });

  renderTabelaParticipacao(periodos, share, itens);
  renderNarrativaMeio(periodos, share, granularidade, itens);
}

function renderTabelaParticipacao(periodos, share, itens) {
  const thead = document.querySelector("#tabela-participacao thead");
  const tbody = document.querySelector("#tabela-participacao tbody");
  thead.innerHTML = `<tr><th>Modalidade</th>${periodos.map((p) => `<th>${p}</th>`).join("")}</tr>`;
  tbody.innerHTML = itens.map((it) => `
    <tr><td>${pilulaModalidade(it.nome, it.cor)}</td>${share[it.nome].map((v) => `<td>${fmtPct(v)}</td>`).join("")}</tr>
  `).join("");
}

/** #rrggbb -> "rgba(r,g,b,alpha)", para esmaecer as modalidades que não estão em foco. */
function comAlpha(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ---------- Gráfico 2: linha do tempo ----------
function renderGraficoEvolucao() {
  const itens = listaEvolucao(segmento);
  const [i0, i1] = periodoParaIndices(evoPeriodo);
  const campo = evoMetrica;
  const labelsPeriodo = dados.labels.slice(i0, i1 + 1).map(fmtMesAno);

  document.getElementById("desc-evolucao").textContent =
    `Série mensal de ${rotuloMetrica(evoMetrica)} por modalidade (${rotuloSegmento(segmento).toLowerCase()}), `
    + `de ${fmtMesAno(dados.labels[i0])} a ${fmtMesAno(dados.labels[i1])}. Em foco: ${focoModalidade}.`;

  const ctx = document.getElementById("gEvolucaoV2");
  const ordemDesenho = [...itens.filter((it) => it.nome !== focoModalidade), ...itens.filter((it) => it.nome === focoModalidade)];
  const datasets = ordemDesenho.map((it) => {
    const emFoco = it.nome === focoModalidade;
    return {
      label: it.nome,
      data: it[campo].slice(i0, i1 + 1),
      borderColor: emFoco ? it.cor : comAlpha(it.cor, 0.25),
      backgroundColor: it.cor,
      borderWidth: emFoco ? 3 : 1.5,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.25,
      order: emFoco ? 0 : 1,
    };
  });

  if (graficoEvolucao) graficoEvolucao.destroy();
  graficoEvolucao = new Chart(ctx, {
    type: "line",
    data: { labels: labelsPeriodo, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: cssVar("--texto"), usePointStyle: true, boxWidth: 8, font: { family: "IBM Plex Sans" } } },
        tooltip: { callbacks: { label: (i) => `${i.dataset.label}: ${fmtCampo(campo, i.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { color: cssVar("--texto-suave"), maxTicksLimit: 12, autoSkip: true }, grid: { display: false } },
        y: { ticks: { color: cssVar("--texto-suave"), callback: (v) => fmtCampo(campo, v) }, grid: { color: cssVar("--borda") } },
      },
    },
  });

  renderTabelaEvolucao(i0, i1, campo, itens);
  renderNarrativaFechamento(i0, i1, itens);
}

/** Tabela-resumo por ano (média — nunca soma, saldo e taxa são "fotos" mensais, não fluxos). */
function renderTabelaEvolucao(i0, i1, campo, itens) {
  const anos = [];
  const agregPorAno = {};
  for (let k = i0; k <= i1; k++) {
    const ano = dados.labels[k].slice(0, 4);
    if (!agregPorAno[ano]) { agregPorAno[ano] = {}; anos.push(ano); }
    itens.forEach((it) => {
      const v = it[campo][k];
      if (!agregPorAno[ano][it.nome]) agregPorAno[ano][it.nome] = { soma: 0, n: 0 };
      if (v != null) { agregPorAno[ano][it.nome].soma += v; agregPorAno[ano][it.nome].n += 1; }
    });
  }
  const thead = document.querySelector("#tabela-evolucao thead");
  const tbody = document.querySelector("#tabela-evolucao tbody");
  thead.innerHTML = `<tr><th>Modalidade</th>${anos.map((a) => `<th>${a}</th>`).join("")}</tr>`;
  tbody.innerHTML = itens.map((it) => `
    <tr><td>${pilulaModalidade(it.nome, it.cor)}</td>${anos.map((a) => {
      const c = agregPorAno[a][it.nome];
      const val = c.n ? c.soma / c.n : null;
      return `<td>${fmtCampo(campo, val)}</td>`;
    }).join("")}</tr>
  `).join("");
}

// ---------- Contexto externo (fixo, ver dados/notas_credito_modalidade.json) ----------
function renderContextoExterno() {
  const alvo = document.getElementById("contexto-externo");
  if (!contextoExterno.length) { alvo.innerHTML = ""; return; }
  const titulo = `<p class="eventos-titulo">O que também estava em jogo</p>`;
  alvo.innerHTML = titulo + contextoExterno.map((e) => `
    <div class="evento-item">
      <div class="evento-data">${e.numero || ""}</div>
      <div class="evento-corpo">
        <h4>${e.titulo}</h4>
        <p>${e.resumo} <a href="${e.url}" target="_blank" rel="noopener">Fonte ↗</a></p>
      </div>
    </div>`).join("");
}

// ---------- Filtros / interação ----------
function montarPilulasPeriodo(container, estadoAtual, aoClicar) {
  container.innerHTML = PERIODOS.map((p) => `
    <button class="pilula-btn ${p.codigo === estadoAtual ? "ativo" : ""}" data-periodo="${p.codigo}">${p.rotulo}</button>
  `).join("");
  container.querySelectorAll(".pilula-btn").forEach((btn) => {
    btn.addEventListener("click", () => aoClicar(btn.dataset.periodo, container));
  });
}

/** Pílulas de "contar a história de <modalidade>" — troca o foco de destaque da linha do tempo. */
function montarPilulasModalidade() {
  const cont = document.getElementById("foco-forma");
  const itens = listaEvolucao(segmento);
  if (!itens.some((it) => it.nome === focoModalidade)) focoModalidade = itens[0].nome;
  cont.innerHTML = itens.map((it) => `
    <button class="pilula-btn pilula-btn-forma ${it.nome === focoModalidade ? "ativo" : ""}" data-forma="${it.nome}">
      <span class="ponto-v2" style="background:${it.cor}"></span>${it.nome}
    </button>
  `).join("");
  cont.querySelectorAll(".pilula-btn-forma").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.forma === focoModalidade) return;
      focoModalidade = btn.dataset.forma;
      cont.querySelectorAll(".pilula-btn-forma").forEach((b) => b.classList.toggle("ativo", b.dataset.forma === focoModalidade));
      renderGraficoEvolucao();
    });
  });
}

function montarPilulasSegmento() {
  const cont = document.getElementById("seletor-segmento");
  cont.innerHTML = dados.segmentos.filter((s) => s !== "Total").map((s) => `
    <button class="pilula-btn ${s === segmento ? "ativo" : ""}" data-segmento="${s}">${dados.rotulos_segmento[s]}</button>
  `).join("");
  cont.querySelectorAll(".pilula-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.segmento === segmento) return;
      segmento = btn.dataset.segmento;
      cont.querySelectorAll(".pilula-btn").forEach((b) => b.classList.toggle("ativo", b.dataset.segmento === segmento));
      focoModalidade = null; // recalculado em montarPilulasModalidade() para o novo segmento
      montarPilulasModalidade();
      renderGraficoParticipacao();
      renderGraficoEvolucao();
    });
  });
}

function ligarFiltros() {
  document.querySelectorAll("[data-metrica-evo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.metricaEvo === evoMetrica) return;
      document.querySelectorAll("[data-metrica-evo]").forEach((b) => b.classList.remove("ativo"));
      btn.classList.add("ativo");
      evoMetrica = btn.dataset.metricaEvo;
      renderGraficoEvolucao();
    });
  });

  const contPart = document.getElementById("periodo-participacao");
  montarPilulasPeriodo(contPart, participPeriodo, (codigo, cont) => {
    participPeriodo = codigo;
    cont.querySelectorAll(".pilula-btn").forEach((b) => b.classList.toggle("ativo", b.dataset.periodo === codigo));
    renderGraficoParticipacao();
  });

  const contEvo = document.getElementById("periodo-evolucao");
  montarPilulasPeriodo(contEvo, evoPeriodo, (codigo, cont) => {
    evoPeriodo = codigo;
    cont.querySelectorAll(".pilula-btn").forEach((b) => b.classList.toggle("ativo", b.dataset.periodo === codigo));
    renderGraficoEvolucao();
  });

  montarPilulasSegmento();

  // Recalcula a granularidade do gráfico de participação ao cruzar o breakpoint mobile/desktop.
  let larguraAnterior = maxColunasTela();
  window.addEventListener("resize", () => {
    clearTimeout(window.__resizeParticipacaoTimer);
    window.__resizeParticipacaoTimer = setTimeout(() => {
      const atual = maxColunasTela();
      if (atual !== larguraAnterior) { larguraAnterior = atual; renderGraficoParticipacao(); }
    }, 200);
  });
}

// ---------- Tema claro/escuro ----------
function temaEfetivoV2() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function sincronizarSwitchTemaV2() {
  const efetivo = temaEfetivoV2();
  document.querySelectorAll("#tema-switch-v2 .tema-switch-v2__btn").forEach((botao) => {
    const ativo = botao.dataset.tema === efetivo;
    botao.classList.toggle("tema-switch-v2__btn--ativo", ativo);
    botao.setAttribute("aria-pressed", ativo ? "true" : "false");
  });
}

/** Canvas (Chart.js) não reage sozinho à troca de tema — CSS puro sim. Redesenha os gráficos e as pílulas com ponto colorido. */
function rerenderizarAposTrocaTema() {
  if (!dados) return;
  montarPilulasModalidade();
  renderGraficoParticipacao();
  renderGraficoEvolucao();
}

function aplicarTemaV2(tema) {
  document.documentElement.setAttribute("data-theme", tema);
  try { localStorage.setItem("tema-v2", tema); } catch (e) { /* modo privado / storage bloqueado */ }
  sincronizarSwitchTemaV2();
  rerenderizarAposTrocaTema();
}

function configurarTemaV2() {
  sincronizarSwitchTemaV2();
  document.querySelectorAll("#tema-switch-v2 .tema-switch-v2__btn").forEach((botao) => {
    botao.addEventListener("click", () => aplicarTemaV2(botao.dataset.tema));
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!document.documentElement.getAttribute("data-theme")) {
      sincronizarSwitchTemaV2();
      rerenderizarAposTrocaTema();
    }
  });
}

async function iniciar() {
  configurarTemaV2();
  try {
    const resp = await fetch(ARQUIVO_DADOS);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    dados = await resp.json();
  } catch (erro) {
    document.getElementById("txt-abertura").textContent =
      "Não foi possível carregar os dados. Rode o pipeline (python run_pipeline.py) para gerar "
      + `${ARQUIVO_DADOS}.`;
    console.error(erro);
    return;
  }

  try {
    const respNotas = await fetch(ARQUIVO_NOTAS);
    contextoExterno = respNotas.ok ? (await respNotas.json()).contexto_externo || [] : [];
  } catch (erro) {
    contextoExterno = [];
    console.warn("Contexto externo não carregado:", erro);
  }

  focoModalidade = "Cartão de crédito rotativo"; // maior contraste de taxa — ver kpis.totais.mais_cara

  renderCabecalho();
  renderNarrativaAbertura();
  ligarFiltros();
  montarPilulasModalidade();
  renderGraficoParticipacao();
  renderGraficoEvolucao();
  renderContextoExterno();
}

iniciar();
