/* Etapa E — página de exploração.
 *
 * Lê dois arquivos com donos diferentes:
 *   docs/dados/perfil_<slug>.json  — gerado pelo pipeline (src/perfil/), sobrescrito
 *   docs/dados/notas_<slug>.json   — escrito à mão, nunca tocado por código
 *
 * Sem perfil a página não existe; sem notas ela funciona só com a metade medida.
 * O slug vem de <body data-slug>, então este arquivo é idêntico em todas as fontes.
 */
(() => {
  "use strict";

  const SLUG = document.body.dataset.slug;
  const nInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nDec = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

  // --- utilitários ------------------------------------------------------
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const num = (v) => (Number.isInteger(v) ? nInt : nDec).format(v);
  const selo = (texto, tipo) => `<span class="selo selo-${esc(tipo)}">${esc(texto)}</span>`;
  const $ = (id) => document.getElementById(id);

  function mostrar(idSecao) { $(idSecao).hidden = false; }

  function celula(v, alinhaNum) {
    if (v === null || v === undefined || v === "") return '<td class="nulo">—</td>';
    if (typeof v === "number") return `<td class="num">${num(v)}</td>`;
    return `<td${alinhaNum ? ' class="num"' : ""}>${esc(v)}</td>`;
  }

  // --- resumo ------------------------------------------------------------
  function renderResumo(perfil, notas) {
    const tidy = perfil.tabelas.find((t) => t.camada === "tidy") || perfil.tabelas[0];
    const cob = perfil.cobertura_temporal;
    const dims = tidy.colunas.filter((c) => c.papel === "dimensao" || c.papel === "data").length;
    const meds = tidy.colunas.filter((c) => c.papel === "medida").length;
    const pauta = notas?.pauta || [];

    const kpis = [
      ["Tabelas perfiladas", perfil.tabelas.length,
       perfil.tabelas.map((t) => t.camada).join(" · ")],
      ["Período coberto", `${cob.inicio} → ${cob.fim}`,
       `${num(cob.meses_presentes)} meses${cob.lacunas.length ? ` · ${cob.lacunas.length} lacuna(s)` : " · sem lacunas"}`],
      ["Linhas no tidy", num(tidy.n_linhas), `${dims} dimensões × ${meds} medidas`],
      ["Joins medidos", perfil.relacionamentos.length,
       perfil.relacionamentos.every((r) => r.orfaos === 0) ? "nenhum órfão" : "há órfãos — ver mapa"],
      ["Itens na pauta", pauta.length || "—",
       pauta.length ? `${pauta.filter((p) => p.status === "aprovado").length} aprovados · ${pauta.filter((p) => p.status === "proposto").length} propostos` : "sem notas curadas"],
    ];

    $("resumo").innerHTML = kpis.map(([r, v, a]) => `
      <article class="kpi">
        <p class="rotulo">${esc(r)}</p>
        <p class="valor">${esc(v)}</p>
        <p class="apoio">${esc(a)}</p>
      </article>`).join("");

    $("meta-info").textContent =
      `${perfil.meta.fonte} · perfil gerado em ${perfil.meta.gerado_em.slice(0, 10)}` +
      (notas ? ` · notas de ${notas.meta.atualizado_em}` : " · sem notas curadas");
    $("rodape-perfil").textContent =
      `Perfil: docs/dados/perfil_${SLUG}.json (gerado em ${perfil.meta.gerado_em}). ` +
      (notas ? `Notas: docs/dados/notas_${SLUG}.json (atualizado em ${notas.meta.atualizado_em}).`
             : "Notas curadas ainda não escritas.");
  }

  // --- mapa das tabelas + relacionamentos --------------------------------
  function renderMapa(perfil) {
    $("mapa").innerHTML = perfil.tabelas.map((t) => `
      <div class="mapa-caixa camada-${esc(t.camada)}">
        ${selo(t.camada, t.camada === "tidy" ? "medida" : t.camada === "auxiliar" ? "dimensao" : "texto")}
        <h3>${esc(t.nome)}</h3>
        <p><span class="mapa-dim">${num(t.n_linhas)} × ${t.n_colunas}</span> ·
           ${esc(t.formato.split("—")[0].trim())}</p>
        <p style="margin-top:6px">${t.chave_primaria_valida
            ? selo("chave única", "ok")
            : selo(`${t.duplicatas} duplicatas`, "erro")}
           <span class="mono">${esc(t.chave_primaria.join(" + ") || "sem chave declarada")}</span></p>
      </div>`).join("");

    $("tabela-relacionamentos").querySelector("tbody").innerHTML =
      perfil.relacionamentos.map((r) => `
        <tr>
          <td><span class="mono">${esc(r.tabela_de)}.${esc(r.de)}</span></td>
          <td><span class="mono">${esc(r.tabela_para)}.${esc(r.para)}</span></td>
          <td>${esc(r.cardinalidade)}</td>
          <td class="num ${r.cobertura_pct === 100 ? "pos" : "neg"}">${nDec.format(r.cobertura_pct)}%</td>
          <td class="num ${r.orfaos ? "neg" : ""}">${num(r.orfaos)}</td>
          <td>${esc(r.uso)}</td>
        </tr>`).join("");
    mostrar("sec-mapa");
  }

  // --- cobertura temporal -------------------------------------------------
  function renderCobertura(perfil) {
    const cob = perfil.cobertura_temporal;
    if (!cob.inicio) return;

    const lacunas = new Set(cob.lacunas);
    const meses = [];
    let [ano, mes] = cob.inicio.split("-").map(Number);
    const [anoF, mesF] = cob.fim.split("-").map(Number);
    while (ano < anoF || (ano === anoF && mes <= mesF)) {
      meses.push(`${ano}-${String(mes).padStart(2, "0")}`);
      if (++mes > 12) { mes = 1; ano++; }
    }

    $("barra-cobertura").innerHTML = meses.map((m) =>
      `<div style="flex:1" class="${lacunas.has(m) ? "lacuna" : ""}" title="${m}"></div>`).join("");
    $("cob-inicio").textContent = cob.inicio;
    $("cob-fim").textContent = cob.fim;
    $("cobertura-desc").textContent = cob.lacunas.length
      ? `${num(cob.meses_presentes)} de ${num(cob.meses_esperados)} meses presentes. Faltam: ${cob.lacunas.join(", ")}.`
      : `${num(cob.meses_presentes)} de ${num(cob.meses_esperados)} meses presentes, sem lacunas.`;
    mostrar("sec-cobertura");
  }

  // --- tabelas -------------------------------------------------------------
  function dicionario(t) {
    const linhas = t.colunas.map((c) => {
      let est = "";
      if (c.min !== undefined) {
        est = `min ${num(c.min)} · mediana ${c.mediana === null ? "—" : num(c.mediana)} · máx ${num(c.max)}` +
              (c.zeros ? ` · ${num(c.zeros)} zeros` : "");
      } else if (c.min_data !== undefined) {
        est = `${esc(c.min_data)} → ${esc(c.max_data)}`;
      } else if (c.top_valores?.length) {
        est = c.top_valores.slice(0, 3).map((v) => `${esc(v.valor)} (${v.n})`).join(" · ");
      }
      return `
        <tr>
          <td><span class="mono">${esc(c.nome)}</span></td>
          <td>${selo(c.papel.replace("_", " "), c.papel)}</td>
          <td><span class="mono">${esc(c.tipo)}</span></td>
          <td>${esc(c.unidade || "—")}</td>
          <td class="num ${c.pct_nulos > 0 ? "neg" : ""}">${nDec.format(c.pct_nulos)}%</td>
          <td class="num">${num(c.distintos)}</td>
          <td>${est}</td>
        </tr>`;
    }).join("");

    return `
      <div class="tabela-wrap">
        <table class="tabela tabela-densa">
          <thead><tr>
            <th>Coluna</th><th>Papel</th><th>Tipo</th><th>Unidade</th>
            <th class="num">Nulos</th><th class="num">Distintos</th><th>Valores</th>
          </tr></thead>
          <tbody>${linhas}</tbody>
        </table>
      </div>`;
  }

  function amostra(t) {
    const a = t.amostra;
    const papeis = Object.fromEntries(t.colunas.map((c) => [c.nome, c]));
    const cab = a.cabecalho.map((c) => {
      const col = papeis[c] || {};
      const alinha = /int|float/.test(col.tipo || "") && col.papel !== "data";
      return `<th${alinha ? ' class="num"' : ""}>
                <span class="mono">${esc(c)}</span><br>${selo(col.papel || "?", col.papel || "texto")}
              </th>`;
    }).join("");

    const linha = (r) => `<tr>${r.map((v) => celula(v)).join("")}</tr>`;
    const meio = a.omitidas
      ? `<tr class="linha-omitida"><td colspan="${a.cabecalho.length}">⋯ ${num(a.omitidas)} linhas omitidas ⋯</td></tr>`
      : "";

    return `
      <div class="tabela-wrap">
        <table class="tabela tabela-densa">
          <thead><tr>${cab}</tr></thead>
          <tbody>${a.inicio.map(linha).join("")}${meio}${a.fim.map(linha).join("")}</tbody>
        </table>
      </div>`;
  }

  function renderTabelas(perfil, notas) {
    const leituras = Object.fromEntries((notas?.leitura || []).map((l) => [l.tabela_id, l.texto]));

    $("tabelas").innerHTML = perfil.tabelas.map((t) => `
      <details class="bloco-tabela"${t.camada === "tidy" ? " open" : ""}>
        <summary>
          ${selo(t.camada, t.camada === "tidy" ? "medida" : t.camada === "auxiliar" ? "dimensao" : "texto")}
          ${esc(t.nome)}
          <span style="color:var(--texto-suave);font-weight:400">
            ${num(t.n_linhas)} linhas × ${t.n_colunas} colunas</span>
          ${t.chave_primaria_valida ? "" : selo("chave inválida", "erro")}
          ${t.alertas.length ? selo(`${t.alertas.length} observações`, "medio") : ""}
        </summary>
        <div class="bloco-corpo">
          <div class="meta-linha">
            <span>Arquivo: <b class="mono">${esc(t.arquivo)}</b></span>
            <span>Formato: <b>${esc(t.formato)}</b></span>
          </div>
          <div class="meta-linha">
            <span>Granularidade: <b>${esc(t.granularidade || "—")}</b></span>
          </div>
          <div class="meta-linha">
            <span>Chave primária: <b class="mono">${esc(t.chave_primaria.join(" + ") || "—")}</b>
              ${t.chave_primaria_valida ? selo("validada", "ok") : selo(`${t.duplicatas} duplicatas`, "erro")}</span>
          </div>
          <div class="meta-linha"><span>Origem: <b>${esc(t.origem)}</b></span></div>

          <h4>Dicionário de colunas</h4>
          ${dicionario(t)}

          ${t.alertas.length ? `<h4>Observações do perfil</h4>
            <ul class="alertas">${t.alertas.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}

          <h4>Amostra — ${t.amostra.omitidas ? "primeiras e últimas 25 linhas" : "todas as linhas"}</h4>
          ${amostra(t)}

          ${leituras[t.id] ? `<div class="nota-curada"><b>Leitura:</b> ${esc(leituras[t.id])}</div>` : ""}
        </div>
      </details>`).join("");
  }

  // --- blocos curados ------------------------------------------------------
  function renderArmadilhas(notas) {
    if (!notas?.armadilhas?.length) return;
    const ordem = { alto: 0, medio: 1, baixo: 2 };
    $("armadilhas").innerHTML = [...notas.armadilhas]
      .sort((a, b) => ordem[a.impacto] - ordem[b.impacto])
      .map((a) => `
        <div class="mini-cartao">
          ${selo(`impacto ${a.impacto}`, a.impacto)}
          <h3>${esc(a.titulo)}</h3>
          <p>${esc(a.texto)}</p>
        </div>`).join("");
    mostrar("sec-armadilhas");
  }

  function renderComparativos(notas) {
    if (!notas?.comparativos?.length) return;
    $("comparativos").innerHTML = notas.comparativos.map((c) => `
      <div class="mini-cartao">
        ${selo(c.id, "medida")}
        <h3>${esc(c.titulo)}</h3>
        <p class="pergunta">${esc(c.pergunta)}</p>
        <p>${esc(c.o_que_esperar)}</p>
        <div class="colunas-usadas">${c.colunas.map((x) => selo(x, "texto")).join("")}</div>
      </div>`).join("");
    mostrar("sec-comparativos");
  }

  function renderContexto(notas) {
    if (!notas?.contexto_externo?.length) return;
    $("contexto").innerHTML = notas.contexto_externo.map((c) => `
      <div class="mini-cartao">
        ${c.numero ? selo(c.numero, "chave") : ""}
        <h3>${esc(c.titulo)}</h3>
        <p>${esc(c.resumo)}</p>
        <p><b>Por que importa:</b> ${esc(c.por_que_importa)}</p>
        <p style="margin-top:10px">
          <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.fonte)} ↗</a>
          <span style="opacity:.7"> · consultado em ${esc(c.consultado_em)}</span>
        </p>
      </div>`).join("");
    mostrar("sec-contexto");
  }

  function renderCruzamentos(notas) {
    if (!notas?.cruzamentos?.length) return;
    const url = (f) => `https://gfvdata-web.github.io/fonte-${f.replace(/_/g, "-").replace("-mensal", "")}/`;
    $("cruzamentos").innerHTML = notas.cruzamentos.map((c) => `
      <div class="mini-cartao">
        ${selo(`chave: ${c.chave}`, "chave")}
        <h3><a href="${esc(url(c.com_fonte))}" target="_blank" rel="noopener">${esc(c.com_fonte)} ↗</a></h3>
        <p class="pergunta">${esc(c.pergunta)}</p>
        <p><b>Cuidado:</b> ${esc(c.cuidado)}</p>
      </div>`).join("");
    mostrar("sec-cruzamentos");
  }

  function renderPauta(notas) {
    if (!notas?.pauta?.length) return;
    const rotulo = { proposto: "proposto", aprovado: "aprovado", descartado: "descartado", no_painel: "no painel" };

    $("tabela-pauta").querySelector("tbody").innerHTML = notas.pauta.map((p) => `
      <tr data-status="${esc(p.status)}" class="${p.status === "descartado" ? "pauta-descartado" : ""}">
        <td class="mono">${esc(p.id)}</td>
        <td>
          <span class="pauta-titulo">${esc(p.titulo)}</span>
          <span class="pauta-pergunta">${esc(p.pergunta)}</span>
        </td>
        <td>${esc(p.tipo_grafico)}</td>
        <td>${selo(p.prioridade, p.prioridade)}</td>
        <td>${selo(p.esforco, p.esforco)}</td>
        <td>${selo(rotulo[p.status] || p.status, p.status)}</td>
      </tr>`).join("");

    $("pauta-justificativas").innerHTML = `
      <h4 style="margin:26px 0 10px;font-size:.78rem;text-transform:uppercase;
                 letter-spacing:.05em;color:var(--texto-suave)">Justificativa de cada escolha</h4>` +
      notas.pauta.map((p) => `
        <details class="bloco-tabela" data-status="${esc(p.status)}">
          <summary>${selo(p.id, "medida")} ${esc(p.titulo)}
            ${selo(rotulo[p.status] || p.status, p.status)}</summary>
          <div class="bloco-corpo">
            <p style="margin:0 0 10px"><b>Por que esse tipo de gráfico:</b> ${esc(p.por_que_esse_tipo)}</p>
            <div class="meta-linha"><span>Tabela: <b class="mono">${esc(p.tabela)}</b></span></div>
            <div class="colunas-usadas">${p.colunas.map((c) => selo(c, "texto")).join("")}</div>
            ${p.comentario ? `<div class="nota-curada" style="margin-top:14px">
                <b>Decisão${p.decidido_em ? ` em ${esc(p.decidido_em)}` : ""}:</b> ${esc(p.comentario)}</div>` : ""}
          </div>
        </details>`).join("");

    $("filtro-pauta").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button");
      if (!btn) return;
      $("filtro-pauta").querySelectorAll(".alt-btn").forEach((b) => b.classList.remove("ativo"));
      btn.classList.add("ativo");
      const alvo = btn.dataset.status;
      document.querySelectorAll(
        "#tabela-pauta tbody tr[data-status], #pauta-justificativas details[data-status]"
      ).forEach((el) => {
        el.hidden = alvo !== "todos" && el.dataset.status !== alvo;
      });
    });
    mostrar("sec-pauta");
  }

  function renderPerguntas(notas) {
    if (!notas?.perguntas_abertas?.length) return;
    $("perguntas").innerHTML = notas.perguntas_abertas.map((p) => `<li>${esc(p)}</li>`).join("");
    mostrar("sec-perguntas");
  }

  // --- arranque -------------------------------------------------------------
  async function json(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url} respondeu ${r.status}`);
    return r.json();
  }

  async function iniciar() {
    let perfil;
    try {
      perfil = await json(`dados/perfil_${SLUG}.json`);
    } catch (e) {
      $("erro").hidden = false;
      $("erro").innerHTML = `<div class="aviso"><b>Perfil não encontrado.</b>
        Rode <span class="mono">python run_pipeline.py</span> para gerar
        <span class="mono">docs/dados/perfil_${esc(SLUG)}.json</span>. (${esc(e.message)})</div>`;
      $("meta-info").textContent = "Falha ao carregar o perfil.";
      return;
    }

    let notas = null;
    try { notas = await json(`dados/notas_${SLUG}.json`); } catch { /* metade medida só */ }

    renderResumo(perfil, notas);
    renderMapa(perfil);
    renderCobertura(perfil);
    renderTabelas(perfil, notas);
    renderArmadilhas(notas);
    renderComparativos(notas);
    renderContexto(notas);
    renderCruzamentos(notas);
    renderPauta(notas);
    renderPerguntas(notas);
  }

  iniciar();
})();
