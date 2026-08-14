/* ===== Painel Crédito por modalidade — Etapa 6 =====
   Consome docs/dados/credito_modalidade.json (gerado pela Etapa 5).
   Nada é hardcoded: modalidades, cores e períodos saem do próprio JSON. */

const ARQUIVO_DADOS = "dados/credito_modalidade.json";

// Paleta categórica — atribuída por posição da modalidade dentro do segmento.
const PALETA = [
  "#2563eb", "#0ea5a4", "#f59e0b", "#8b5cf6", "#ec4899", "#10b981",
  "#ef4444", "#06b6d4", "#a855f7", "#84cc16", "#f97316", "#3b82f6",
  "#14b8a6", "#d946ef", "#eab308", "#22c55e", "#6366f1",
];
const COR_RESIDUO = "#94a3b8";
const COR_SPREAD = "#f59e0b";

let dados = null;
let segmento = "PF";     // "PF" | "PJ"
let metrica = "saldo";   // "saldo" | "taxa"
let cores = {};          // cores[segmento][modalidade]

let graficoEvolucao = null;
let graficoParticipacao = null;
let graficoTaxas = null;
let graficoSpread = null;

// Índices (em dados.labels) dos filtros de período de cada cartão.
let rankInicio = 0, rankFim = 0;
let estInicio = 0, estFim = 0;

// ---------- Formatação ----------
const nf = (casas = 1) => new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: casas, maximumFractionDigits: casas,
});

/** saldo em R$ milhões -> texto compacto. */
function fmtSaldo(x) {
  if (x == null) return "—";
  const abs = Math.abs(x);
  if (abs >= 1e6) return `R$ ${nf(2).format(x / 1e6)} tri`;
  if (abs >= 1e3) return `R$ ${nf(1).format(x / 1e3)} bi`;
  return `R$ ${nf(0).format(x)} mi`;
}

/** taxa em % ao ano. */
const fmtTaxa = (x) => (x == null ? "—" : `${nf(1).format(x)}%`);

/** variação em pontos percentuais (sempre com sinal). */
function fmtPP(x) {
  if (x == null) return "—";
  return `${x > 0 ? "+" : ""}${nf(1).format(x)} p.p.`;
}

function fmtPct(x, comSinal = false) {
  if (x == null) return "—";
  const s = comSinal && x > 0 ? "+" : "";
  return `${s}${nf(1).format(x)}%`;
}

const fmtMetrica = (x) => (metrica === "taxa" ? fmtTaxa(x) : fmtSaldo(x));

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** "2026-05" -> "mai/2026" */
function fmtMesAno(anoMes) {
  const [a, m] = anoMes.split("-");
  return `${MESES[Number(m) - 1]}/${a}`;
}

/** "2026-05" -> "mai/26" (formato mmm/aa, usado nos filtros). */
function fmtMesAnoCurto(anoMes) {
  const [a, m] = anoMes.split("-");
  return `${MESES[Number(m) - 1]}/${a.slice(2)}`;
}

const cssVar = (nome) => getComputedStyle(document.body).getPropertyValue(nome).trim();

// ---------- Acesso aos dados ----------
const modalidades = () => dados.modalidades[segmento];
const serieDe = (mod, medida) => dados.series[segmento][mod][medida];
const rotuloSegmento = () => dados.rotulos_segmento[segmento];
const rotuloMetrica = () => (metrica === "taxa" ? "taxa de juros (% a.a.)" : "saldo (R$)");

/** Monta cores[segmento][modalidade] a partir da ordem publicada no JSON. */
function prepararCores() {
  dados.segmentos.forEach((seg) => {
    cores[seg] = {};
    (dados.modalidades[seg] || []).forEach((mod, i) => {
      cores[seg][mod] = PALETA[i % PALETA.length];
    });
  });
}

// ---------- Cálculos por período (recalculados no cliente conforme os filtros) ----------
/** Variação % de uma série entre os índices i0 e i1. */
function variacaoPct(serie, i0, i1) {
  const v0 = serie[i0], v1 = serie[i1];
  if (v0 == null || v1 == null || v0 === 0) return null;
  return (v1 / v0 - 1) * 100;
}

/** Variação em p.p. de uma série de taxa entre os índices i0 e i1. */
function variacaoPP(serie, i0, i1) {
  const v0 = serie[i0], v1 = serie[i1];
  if (v0 == null || v1 == null) return null;
  return v1 - v0;
}

/** CAGR anual (%) entre o 1º e o último valor positivo dentro do intervalo [i0, i1]. */
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

/** Estatística descritiva da série `medida` da `modalidade` no intervalo [i0, i1]. */
function calcularEstatistica(mod, medida, i0, i1) {
  const serie = serieDe(mod, medida);
  const arr = [];
  for (let k = i0; k <= i1; k++) { if (serie[k] != null) arr.push(serie[k]); }
  const n = arr.length;
  const vazio = { media: null, mediana: null, desvio_padrao: null, coef_variacao_pct: null, minimo: null, maximo: null };
  if (!n) return vazio;

  const media = arr.reduce((s, x) => s + x, 0) / n;
  const ord = [...arr].sort((a, b) => a - b);
  const mediana = n % 2 ? ord[(n - 1) / 2] : (ord[n / 2 - 1] + ord[n / 2]) / 2;
  let desvio = null;
  if (n > 1) {
    const soma2 = arr.reduce((s, x) => s + (x - media) ** 2, 0);
    desvio = Math.sqrt(soma2 / (n - 1)); // amostral (ddof=1), igual ao pandas
  }
  return {
    media,
    mediana,
    desvio_padrao: desvio,
    coef_variacao_pct: (media && desvio) ? desvio / media * 100 : null,
    minimo: Math.min(...arr),
    maximo: Math.max(...arr),
  };
}

/** Ranking das modalidades do segmento no intervalo [i0, i1]. Mês final = i1. */
function calcularRanking(i0, i1) {
  const saldoSegmento = dados.series[segmento].Total.saldo[i1];
  const linhas = modalidades().map((mod) => {
    const saldo = serieDe(mod, "saldo"), taxa = serieDe(mod, "taxa");
    const saldoFim = saldo[i1];
    return {
      modalidade: mod,
      saldo_fim: saldoFim,
      part_saldo_pct: (saldoFim != null && saldoSegmento) ? saldoFim / saldoSegmento * 100 : null,
      var_saldo_pct: variacaoPct(saldo, i0, i1),
      cagr_saldo_aa_pct: cagrAA(saldo, i0, i1),
      taxa_fim: taxa[i1],
      var_taxa_pp: variacaoPP(taxa, i0, i1),
    };
  });
  linhas.sort((a, b) => (b.saldo_fim ?? 0) - (a.saldo_fim ?? 0));
  return linhas;
}

// ---------- Renderização ----------
function renderCabecalho() {
  const meta = dados.meta;
  document.getElementById("descricao-fonte").textContent = meta.descricao;
  document.getElementById("meta-info").textContent =
    `Período: ${fmtMesAno(meta.periodo.inicio)} – ${fmtMesAno(meta.periodo.fim)} · `
    + `${dados.kpis.totais.meses_cobertos} meses · ${meta.series_sgs} séries do SGS · `
    + `Atualizado em ${new Date(meta.gerado_em).toLocaleDateString("pt-BR")}`;
  document.getElementById("rodape-fonte").textContent = `Fonte: ${meta.fonte}. ${meta.licenca}.`;
}

function renderKpis() {
  const t = dados.kpis.totais;
  const mesRef = fmtMesAno(t.mes_ref);
  const maior = t.maior_saldo, cara = t.mais_cara;
  const cartoes = [
    {
      rotulo: `Saldo total de crédito — ${mesRef}`,
      valor: fmtSaldo(t.saldo_total),
      apoio: `${fmtPct(t.yoy_saldo_total_pct, true)} em 12 meses · PF ${fmtSaldo(t.saldo_pf)} · PJ ${fmtSaldo(t.saldo_pj)}`,
      classe: t.yoy_saldo_total_pct == null ? "" : (t.yoy_saldo_total_pct >= 0 ? "pos" : "neg"),
    },
    {
      rotulo: "Taxa média de juros",
      valor: fmtTaxa(t.taxa_media_aa),
      apoio: `Média ponderada do crédito total, ao ano (${mesRef})`,
    },
    {
      rotulo: "Spread médio",
      valor: `${nf(1).format(t.spread_medio_pp)} p.p.`,
      apoio: `Diferença entre a taxa cobrada e o custo de captação (${mesRef})`,
    },
    {
      rotulo: "Maior saldo",
      valor: maior.modalidade,
      apoio: `${maior.segmento} · ${fmtSaldo(maior.saldo_ultimo)} · ${fmtPct(maior.part_saldo_segmento_pct)} do segmento`,
    },
    {
      rotulo: "Modalidade mais cara",
      valor: cara.modalidade,
      apoio: `${cara.segmento} · ${fmtTaxa(cara.taxa_ultima)} ao ano em ${mesRef}`,
    },
  ];
  document.getElementById("kpis").innerHTML = cartoes.map((c) => `
    <div class="kpi">
      <p class="rotulo">${c.rotulo}</p>
      <p class="valor">${c.valor}</p>
      <p class="apoio ${c.classe || ""}">${c.apoio}</p>
    </div>`).join("");
}

function renderEvolucao() {
  const datasets = modalidades().map((mod) => ({
    label: mod,
    data: serieDe(mod, metrica),
    borderColor: cores[segmento][mod],
    backgroundColor: cores[segmento][mod],
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.3,
  }));

  document.getElementById("titulo-evolucao").textContent =
    metrica === "taxa"
      ? `Taxa média de juros (% a.a.) por modalidade — ${rotuloSegmento()}.`
      : `Saldo da carteira (R$) por modalidade — ${rotuloSegmento()}.`;

  if (graficoEvolucao) graficoEvolucao.destroy();
  graficoEvolucao = new Chart(document.getElementById("gEvolucao"), {
    type: "line",
    data: { labels: dados.labels.map(fmtMesAno), datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: cssVar("--texto"), usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: (i) => `${i.dataset.label}: ${fmtMetrica(i.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { color: cssVar("--texto-suave"), maxTicksLimit: 12, autoSkip: true }, grid: { display: false } },
        y: {
          ticks: { color: cssVar("--texto-suave"), callback: (v) => fmtMetrica(v) },
          grid: { color: cssVar("--borda") },
        },
      },
    },
  });
}

function renderParticipacao() {
  const i = dados.labels.length - 1;
  const itens = modalidades()
    .map((mod) => ({ rotulo: mod, valor: serieDe(mod, "saldo")[i] ?? 0, cor: cores[segmento][mod] }))
    .sort((a, b) => b.valor - a.valor);
  // Resíduo: modalidades do segmento que esta fonte não detalha — explicitado para que
  // as fatias somem o saldo real do segmento, e não só o das modalidades coletadas.
  const residuo = dados.residuos[segmento];
  if (residuo && residuo.saldo_ultimo > 0) {
    itens.push({ rotulo: dados.rotulo_residuo, valor: residuo.saldo_ultimo, cor: COR_RESIDUO });
  }
  const total = itens.reduce((s, x) => s + x.valor, 0);

  document.getElementById("titulo-participacao").textContent =
    `Saldo por modalidade em ${fmtMesAno(dados.labels[i])} — ${rotuloSegmento()}.`;

  if (graficoParticipacao) graficoParticipacao.destroy();
  graficoParticipacao = new Chart(document.getElementById("gParticipacao"), {
    type: "doughnut",
    data: {
      labels: itens.map((x) => x.rotulo),
      datasets: [{
        data: itens.map((x) => x.valor),
        backgroundColor: itens.map((x) => x.cor),
        borderColor: cssVar("--superficie"),
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "58%",
      plugins: {
        legend: { position: "bottom", labels: { color: cssVar("--texto"), usePointStyle: true, boxWidth: 8 } },
        tooltip: {
          callbacks: {
            label: (i2) => {
              const pct = total ? (i2.parsed / total) * 100 : 0;
              return `${i2.label}: ${fmtSaldo(i2.parsed)} (${fmtPct(pct)})`;
            },
          },
        },
      },
    },
  });
}

function renderTaxas() {
  const i = dados.labels.length - 1;
  const itens = modalidades()
    .map((mod) => ({ rotulo: mod, valor: serieDe(mod, "taxa")[i], cor: cores[segmento][mod] }))
    .filter((x) => x.valor != null)
    .sort((a, b) => b.valor - a.valor);

  document.getElementById("titulo-taxas").textContent =
    `Taxa média de juros ao ano em ${fmtMesAno(dados.labels[i])}, por modalidade — ${rotuloSegmento()}. `
    + `Da mais cara para a mais barata.`;

  if (graficoTaxas) graficoTaxas.destroy();
  graficoTaxas = new Chart(document.getElementById("gTaxas"), {
    type: "bar",
    data: {
      labels: itens.map((x) => x.rotulo),
      datasets: [{
        label: "Taxa (% a.a.)",
        data: itens.map((x) => x.valor),
        backgroundColor: itens.map((x) => x.cor),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (i2) => `${fmtTaxa(i2.parsed.x)} ao ano` } },
      },
      scales: {
        x: {
          ticks: { color: cssVar("--texto-suave"), callback: (v) => fmtTaxa(v) },
          grid: { color: cssVar("--borda") },
        },
        y: { ticks: { color: cssVar("--texto-suave") }, grid: { display: false } },
      },
    },
  });
}

function renderSpread() {
  const agregado = dados.series[segmento].Total;
  document.getElementById("titulo-spread").textContent =
    `Taxa média de juros e spread do crédito a ${rotuloSegmento().toLowerCase()}, por mês. `
    + `O spread é a parcela da taxa que não vem do custo de captação.`;

  if (graficoSpread) graficoSpread.destroy();
  graficoSpread = new Chart(document.getElementById("gSpread"), {
    type: "line",
    data: {
      labels: dados.labels.map(fmtMesAno),
      datasets: [
        {
          label: "Taxa média (% a.a.)",
          data: agregado.taxa,
          borderColor: cssVar("--acento"), backgroundColor: cssVar("--acento"),
          borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.3,
        },
        {
          label: "Spread (p.p. a.a.)",
          data: agregado.spread,
          borderColor: COR_SPREAD, backgroundColor: COR_SPREAD,
          borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: cssVar("--texto"), usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: (i) => `${i.dataset.label}: ${nf(2).format(i.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { color: cssVar("--texto-suave"), maxTicksLimit: 12, autoSkip: true }, grid: { display: false } },
        y: {
          ticks: { color: cssVar("--texto-suave"), callback: (v) => nf(0).format(v) },
          grid: { color: cssVar("--borda") },
        },
      },
    },
  });
}

function pilulaModalidade(mod) {
  return `<span class="pilula"><span class="ponto" style="background:${cores[segmento][mod]}"></span>${mod}</span>`;
}

function cls(x) { return x == null ? "nulo" : x >= 0 ? "pos" : "neg"; }

function renderTabelaRanking() {
  const inicioTxt = fmtMesAnoCurto(dados.labels[rankInicio]);
  const fimTxt = fmtMesAnoCurto(dados.labels[rankFim]);
  document.getElementById("desc-ranking").textContent =
    `${rotuloSegmento()} · período ${inicioTxt}–${fimTxt}. Saldo, participação e taxa referem-se ao `
    + `mês final (${fimTxt}); variações e CAGR, ao período inteiro. Taxa subindo é custo maior — `
    + `por isso a variação de taxa aparece em vermelho quando positiva.`;

  document.querySelector("#tabela-ranking tbody").innerHTML = calcularRanking(rankInicio, rankFim)
    .map((m) => `
    <tr>
      <td>${pilulaModalidade(m.modalidade)}</td>
      <td class="num">${fmtSaldo(m.saldo_fim)}</td>
      <td class="num">${fmtPct(m.part_saldo_pct)}</td>
      <td class="num ${cls(m.var_saldo_pct)}">${fmtPct(m.var_saldo_pct, true)}</td>
      <td class="num ${cls(m.cagr_saldo_aa_pct)}">${fmtPct(m.cagr_saldo_aa_pct, true)}</td>
      <td class="num">${fmtTaxa(m.taxa_fim)}</td>
      <td class="num ${cls(m.var_taxa_pp == null ? null : -m.var_taxa_pp)}">${fmtPP(m.var_taxa_pp)}</td>
    </tr>`).join("");
}

function renderTabelaEstatistica() {
  const fmt = metrica === "taxa" ? fmtTaxa : fmtSaldo;
  document.getElementById("titulo-estatistica").textContent =
    `${rotuloSegmento()} · série mensal no período `
    + `${fmtMesAnoCurto(dados.labels[estInicio])}–${fmtMesAnoCurto(dados.labels[estFim])} `
    + `— métrica: ${rotuloMetrica()}.`;

  document.querySelector("#tabela-estatistica tbody").innerHTML = modalidades().map((mod) => {
    const e = calcularEstatistica(mod, metrica, estInicio, estFim);
    return `
      <tr>
        <td>${pilulaModalidade(mod)}</td>
        <td class="num">${fmt(e.media)}</td>
        <td class="num">${fmt(e.mediana)}</td>
        <td class="num">${fmt(e.desvio_padrao)}</td>
        <td class="num">${fmtPct(e.coef_variacao_pct)}</td>
        <td class="num">${fmt(e.minimo)}</td>
        <td class="num">${fmt(e.maximo)}</td>
      </tr>`;
  }).join("");
}

/** Tudo que depende da métrica escolhida. */
function renderMetricaDependente() {
  renderEvolucao();
  renderTabelaEstatistica();
}

/** Tudo que depende do segmento escolhido (inclui o que depende da métrica). */
function renderSegmentoDependente() {
  renderMetricaDependente();
  renderParticipacao();
  renderTaxas();
  renderSpread();
  renderTabelaRanking();
}

function ligarAlternador(id, atributo, aoTrocar) {
  document.querySelectorAll(`#${id} .alt-btn`).forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset[atributo] === (atributo === "segmento" ? segmento : metrica)) return;
      document.querySelectorAll(`#${id} .alt-btn`).forEach((b) => b.classList.remove("ativo"));
      btn.classList.add("ativo");
      aoTrocar(btn.dataset[atributo]);
    });
  });
}

/** Preenche um <select> com todos os meses (mmm/aa) e marca o índice atual. */
function preencherSelectMeses(sel, idxSelecionado) {
  sel.innerHTML = dados.labels
    .map((l, i) => `<option value="${i}">${fmtMesAnoCurto(l)}</option>`)
    .join("");
  sel.value = String(idxSelecionado);
}

/** Liga um par de selects De/Até, mantendo início <= fim. */
function ligarFiltro(idInicio, idFim, ler, escrever, aoMudar) {
  const selI = document.getElementById(idInicio);
  const selF = document.getElementById(idFim);
  preencherSelectMeses(selI, ler().inicio);
  preencherSelectMeses(selF, ler().fim);
  selI.addEventListener("change", () => {
    let { fim } = ler();
    const inicio = Number(selI.value);
    if (inicio > fim) { fim = inicio; selF.value = String(fim); }
    escrever(inicio, fim);
    aoMudar();
  });
  selF.addEventListener("change", () => {
    let { inicio } = ler();
    const fim = Number(selF.value);
    if (fim < inicio) { inicio = fim; selI.value = String(inicio); }
    escrever(inicio, fim);
    aoMudar();
  });
}

async function iniciar() {
  try {
    const resp = await fetch(ARQUIVO_DADOS);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    dados = await resp.json();
  } catch (erro) {
    document.getElementById("meta-info").textContent =
      "Não foi possível carregar os dados. Rode o pipeline "
      + `(python run_pipeline.py credito_modalidade) para gerar ${ARQUIVO_DADOS}.`;
    console.error(erro);
    return;
  }

  prepararCores();

  // Filtros começam cobrindo todo o período disponível.
  const ultimo = dados.labels.length - 1;
  rankInicio = 0; rankFim = ultimo;
  estInicio = 0; estFim = ultimo;

  renderCabecalho();
  renderKpis();
  ligarFiltro(
    "ranking-inicio", "ranking-fim",
    () => ({ inicio: rankInicio, fim: rankFim }),
    (i, f) => { rankInicio = i; rankFim = f; },
    renderTabelaRanking,
  );
  ligarFiltro(
    "est-inicio", "est-fim",
    () => ({ inicio: estInicio, fim: estFim }),
    (i, f) => { estInicio = i; estFim = f; },
    renderTabelaEstatistica,
  );
  renderSegmentoDependente();

  ligarAlternador("alt-segmento", "segmento", (v) => { segmento = v; renderSegmentoDependente(); });
  ligarAlternador("alt-metrica", "metrica", (v) => { metrica = v; renderMetricaDependente(); });
}

iniciar();
