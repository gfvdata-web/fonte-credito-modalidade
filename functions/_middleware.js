// Pages Function: só roda nas rotas de docs/_routes.json (/contagem.json, /skill/*, /dados/*), o resto sai
// direto dos estáticos sem invocar código (cota grátis). A lógica fica em cloudflare/contagem.mjs.
import { atender } from "../cloudflare/contagem.mjs";

export const onRequest = (context) =>
  atender(context.request, {
    db: context.env.DOWNLOADS,
    site: context.env.SITE,
    servirArquivo: () => context.next(),
    adiar: (promessa) => context.waitUntil(promessa),
  });
