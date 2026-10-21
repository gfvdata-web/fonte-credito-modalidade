// Contador de downloads (cloudflare/contagem.mjs) com D1 falso em memória: node --test tests/js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const SITE = "fonte-credito-modalidade";
const carregar = () => import(pathToFileURL(path.resolve(__dirname, "..", "..", "cloudflare", "contagem.mjs")).href);

// D1 falso: entende só os dois comandos do contador (o UPSERT e o SELECT por site).
function d1Falso({ falhar = false } = {}) {
  const linhas = new Map();
  return {
    linhas,
    prepare(sql) {
      return {
        bind(...args) {
          return {
            async run() {
              if (falhar) throw new Error("D1 fora do ar");
              assert.match(sql, /^INSERT INTO downloads .* ON CONFLICT \(site, arquivo, dia, tipo\) DO UPDATE SET total = total \+ 1$/);
              const chave = args.join("|");
              linhas.set(chave, (linhas.get(chave) || 0) + 1);
            },
            async all() {
              if (falhar) throw new Error("D1 fora do ar");
              assert.match(sql, /^SELECT arquivo, dia, tipo, total FROM downloads WHERE site = \?1$/);
              const results = [...linhas.entries()]
                .map(([chave, total]) => {
                  const [site, arquivo, dia, tipo] = chave.split("|");
                  return { site, arquivo, dia, tipo, total };
                })
                .filter((l) => l.site === args[0]);
              return { results };
            },
          };
        },
      };
    },
  };
}

const pedido = (caminho, { method = "GET", ua = "Mozilla/5.0 Firefox/130.0", range } = {}) => {
  const headers = new Headers({ "user-agent": ua });
  if (range) headers.set("range", range);
  return new Request(`https://creditomodalidade.gfvdata.com${caminho}`, { method, headers });
};

async function chamar(contagem, db, req, status = 200) {
  const pendentes = [];
  const resposta = await contagem.atender(req, {
    db,
    site: SITE,
    servirArquivo: async () => new Response(status === 304 ? null : "conteudo", { status }),
    adiar: (p) => pendentes.push(p),
  });
  await Promise.all(pendentes);
  return resposta;
}

test("classifica navegador, script (skill em Python) e robô", async () => {
  const { classificar } = await carregar();
  assert.equal(classificar("Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36"), "navegador");
  assert.equal(classificar("Python-urllib/3.12"), "script");
  assert.equal(classificar("python-requests/2.32"), "script");
  assert.equal(classificar("curl/8.5.0"), "script");
  assert.equal(classificar(""), "script");
  assert.equal(classificar(undefined), "script");
  assert.equal(classificar("Mozilla/5.0 (compatible; Googlebot/2.1)"), "robo");
  assert.equal(classificar("facebookexternalhit/1.1"), "robo");
  assert.equal(classificar("curl/8.5.0 gfvdata-verificacao (site-checker)"), "robo");
});

test("só o zip da skill e os CSV de dados contam", async () => {
  const { tipoDeArquivo } = await carregar();
  assert.equal(tipoDeArquivo("/skill/credito-modalidade-bcb.zip"), "skill");
  assert.equal(tipoDeArquivo("/dados/credito_modalidade.csv"), "csv");
  assert.equal(tipoDeArquivo("/dados/credito_modalidade.json"), null);
  assert.equal(tipoDeArquivo("/skill.html"), null);
  assert.equal(tipoDeArquivo("/skill/sub/x.zip"), null);
});

test("dia no horário de Brasília", async () => {
  const { diaBrasilia } = await carregar();
  assert.equal(diaBrasilia(new Date("2026-10-18T02:59:00Z")), "2026-10-17");
  assert.equal(diaBrasilia(new Date("2026-10-18T03:00:00Z")), "2026-10-18");
});

test("download conta uma vez por pedido e devolve o arquivo intacto", async () => {
  const contagem = await carregar();
  const db = d1Falso();
  const r1 = await chamar(contagem, db, pedido("/skill/credito-modalidade-bcb.zip"));
  await chamar(contagem, db, pedido("/skill/credito-modalidade-bcb.zip"));
  await chamar(contagem, db, pedido("/dados/credito_modalidade.csv", { ua: "Python-urllib/3.12" }));
  assert.equal(await r1.text(), "conteudo");
  const dia = contagem.diaBrasilia();
  assert.equal(db.linhas.get(`${SITE}|/skill/credito-modalidade-bcb.zip|${dia}|navegador`), 2);
  assert.equal(db.linhas.get(`${SITE}|/dados/credito_modalidade.csv|${dia}|script`), 1);
});

test("HEAD, Range, 304/404 e páginas comuns não contam", async () => {
  const contagem = await carregar();
  const db = d1Falso();
  await chamar(contagem, db, pedido("/skill/credito-modalidade-bcb.zip", { method: "HEAD" }));
  await chamar(contagem, db, pedido("/skill/credito-modalidade-bcb.zip", { range: "bytes=0-99" }));
  await chamar(contagem, db, pedido("/skill/credito-modalidade-bcb.zip"), 304);
  await chamar(contagem, db, pedido("/dados/nao-existe.csv"), 404);
  await chamar(contagem, db, pedido("/index.html"));
  assert.equal(db.linhas.size, 0);
});

test("D1 fora do ar não derruba o download", async () => {
  const contagem = await carregar();
  const erroOriginal = console.error;
  const erros = [];
  console.error = (m) => erros.push(m);
  try {
    const r = await chamar(contagem, d1Falso({ falhar: true }), pedido("/skill/credito-modalidade-bcb.zip"));
    assert.equal(r.status, 200);
    assert.equal(await r.text(), "conteudo");
  } finally {
    console.error = erroOriginal;
  }
  assert.match(erros[0], /\[contagem\] falha ao registrar/);
});

test("/contagem.json resume por arquivo, sem robôs no total, com série de 30 dias", async () => {
  const contagem = await carregar();
  const db = d1Falso();
  const zip = "/skill/credito-modalidade-bcb.zip";
  const hoje = contagem.diaBrasilia();
  const antigo = "2026-01-05";
  db.linhas.set(`${SITE}|${zip}|${hoje}|navegador`, 3);
  db.linhas.set(`${SITE}|${zip}|${hoje}|robo`, 7);
  db.linhas.set(`${SITE}|${zip}|${antigo}|script`, 2);
  db.linhas.set(`outro-site|${zip}|${hoje}|navegador`, 99);
  const r = await chamar(contagem, db, pedido("/contagem.json"));
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("access-control-allow-origin"), "*");
  const corpo = await r.json();
  assert.equal(corpo.site, SITE);
  assert.equal(corpo.desde, antigo);
  assert.match(corpo.gerado_em, /^\d{4}-\d{2}-\d{2}T/);
  assert.deepEqual(corpo.arquivos, [
    {
      arquivo: zip,
      tipo_arquivo: "skill",
      total: 5,
      por_tipo: { navegador: 3, script: 2, robo: 7 },
      serie_30d: [{ dia: hoje, total: 3 }],
    },
  ]);
  assert.equal(db.linhas.size, 4, "ler a contagem não registra nada");
});

test("/contagem.json sem dado e com D1 fora do ar", async () => {
  const contagem = await carregar();
  const vazio = await (await chamar(contagem, d1Falso(), pedido("/contagem.json"))).json();
  assert.deepEqual([vazio.arquivos, vazio.desde], [[], null]);
  const r = await chamar(contagem, d1Falso({ falhar: true }), pedido("/contagem.json"));
  assert.equal(r.status, 503);
  const post = await chamar(contagem, d1Falso(), pedido("/contagem.json", { method: "POST" }));
  assert.equal(post.status, 405);
});

test("o middleware do Pages liga o contador a next(), waitUntil e ao binding DOWNLOADS", async () => {
  const { onRequest } = await import(pathToFileURL(path.resolve(__dirname, "..", "..", "functions", "_middleware.js")).href);
  const db = d1Falso();
  const pendentes = [];
  const context = {
    request: pedido("/skill/credito-modalidade-bcb.zip"),
    env: { DOWNLOADS: db, SITE },
    next: async () => new Response("zip", { status: 200 }),
    waitUntil: (p) => pendentes.push(p),
  };
  const r = await onRequest(context);
  await Promise.all(pendentes);
  assert.equal(await r.text(), "zip");
  assert.equal(db.linhas.size, 1);
});
