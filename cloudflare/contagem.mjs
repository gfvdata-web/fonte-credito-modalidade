// Contador de downloads (skill .zip e CSV) no D1 `downloads`, compartilhado pelos sites de dados abertos.
// Mesmo arquivo em fonte-arrecadacao-federal, fonte-meios-pagamento e fonte-credito-modalidade: mudou aqui, copiar lá.
// Guarda só um total por (site, arquivo, dia, tipo); nada de IP, cookie ou User-Agent.
// O painel-status lê /contagem.json de cada site.
//
// Tabela (criada uma vez com `wrangler d1 execute downloads --remote`):
//   CREATE TABLE IF NOT EXISTS downloads (site TEXT NOT NULL, arquivo TEXT NOT NULL, dia TEXT NOT NULL,
//     tipo TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (site, arquivo, dia, tipo)) WITHOUT ROWID;

export const ROTA_CONTAGEM = "/contagem.json";
const DIAS_SERIE = 30;

const ROBO = /bot|crawl|spider|slurp|facebookexternalhit|whatsapp|telegram|preview|uptime|monitor|headless|lighthouse/i;
const SCRIPT = /python|curl|wget|httpx|aiohttp|requests|node|undici|go-http|java|okhttp|axios|libwww|powershell|r-curl|httr/i;

/** "robo", "script" (uso por código, como a skill do Claude) ou "navegador". */
export function classificar(userAgent) {
  const ua = (userAgent || "").trim();
  if (!ua) return "script";
  if (ROBO.test(ua)) return "robo";
  if (SCRIPT.test(ua)) return "script";
  return "navegador";
}

/** Arquivo que entra na contagem: o .zip da skill ou um CSV de dados. */
export function tipoDeArquivo(caminho) {
  if (/^\/skill\/[^/]+\.zip$/.test(caminho)) return "skill";
  if (/^\/dados\/[^/]+\.csv$/.test(caminho)) return "csv";
  return null;
}

/** Só GET inteiro que deu 200: HEAD, pedido parcial (Range), 304 e 404 não contam. */
export function deveContar(pedido, resposta) {
  return pedido.method === "GET" && !pedido.headers.get("range") && resposta.status === 200;
}

/** Dia no horário de Brasília (UTC-3, sem horário de verão desde 2019). */
export function diaBrasilia(agora = new Date()) {
  return new Date(agora.getTime() - 3 * 3600 * 1000).toISOString().slice(0, 10);
}

export async function registrar(db, site, arquivo, tipo, dia) {
  await db
    .prepare(
      "INSERT INTO downloads (site, arquivo, dia, tipo, total) VALUES (?1, ?2, ?3, ?4, 1) " +
        "ON CONFLICT (site, arquivo, dia, tipo) DO UPDATE SET total = total + 1"
    )
    .bind(site, arquivo, dia, tipo)
    .run();
}

/** Corpo do /contagem.json: por arquivo, total sem robôs, totais por tipo e série dos últimos 30 dias. */
export async function resumo(db, site, agora = new Date()) {
  const { results } = await db
    .prepare("SELECT arquivo, dia, tipo, total FROM downloads WHERE site = ?1")
    .bind(site)
    .all();
  const corte = diaBrasilia(new Date(agora.getTime() - (DIAS_SERIE - 1) * 86400 * 1000));
  const porArquivo = new Map();
  let desde = null;
  for (const { arquivo, dia, tipo, total } of results) {
    if (!porArquivo.has(arquivo)) {
      porArquivo.set(arquivo, { total: 0, por_tipo: { navegador: 0, script: 0, robo: 0 }, dias: new Map() });
    }
    const item = porArquivo.get(arquivo);
    item.por_tipo[tipo] = (item.por_tipo[tipo] || 0) + total;
    if (tipo !== "robo") {
      item.total += total;
      if (dia >= corte) item.dias.set(dia, (item.dias.get(dia) || 0) + total);
    }
    if (!desde || dia < desde) desde = dia;
  }
  const arquivos = [...porArquivo.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([arquivo, item]) => ({
      arquivo,
      tipo_arquivo: tipoDeArquivo(arquivo),
      total: item.total,
      por_tipo: item.por_tipo,
      serie_30d: [...item.dias.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([dia, total]) => ({ dia, total })),
    }));
  return { site, gerado_em: agora.toISOString(), desde, arquivos };
}

/**
 * Atende um pedido. `servirArquivo()` devolve a resposta do arquivo estático (env.ASSETS.fetch no
 * Worker, context.next() no Pages). `adiar(promessa)` é o waitUntil: a contagem nunca atrasa nem
 * derruba o download.
 */
export async function atender(pedido, { db, site, servirArquivo, adiar }) {
  const caminho = new URL(pedido.url).pathname;
  if (caminho === ROTA_CONTAGEM) {
    if (pedido.method !== "GET" && pedido.method !== "HEAD") return new Response(null, { status: 405 });
    let corpo;
    try {
      corpo = await resumo(db, site);
    } catch (erro) {
      return Response.json({ site, erro: "contagem indisponível" }, { status: 503, headers: CABECALHOS_JSON });
    }
    return Response.json(corpo, { headers: CABECALHOS_JSON });
  }
  const resposta = await servirArquivo();
  if (tipoDeArquivo(caminho) && deveContar(pedido, resposta)) {
    const tipo = classificar(pedido.headers.get("user-agent"));
    adiar(
      registrar(db, site, caminho, tipo, diaBrasilia()).catch((erro) =>
        console.error(`[contagem] falha ao registrar ${caminho}: ${erro}`)
      )
    );
  }
  return resposta;
}

const CABECALHOS_JSON = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "public, max-age=300",
};
