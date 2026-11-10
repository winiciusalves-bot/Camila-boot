// Portais de transparência Betha (transparencia.betha.cloud): a lista de edições vem de uma API que a própria página
// pública chama. Abrimos a página como um visitante, reaproveitamos a mesma sessão anônima da página e listamos
// as edições e os anexos (PDF). Sem login, sem captcha. Grava listas/betha_<nome>.json para o robô Scrapy baixar.
// Os links de PDF são assinados e valem 24 h, por isso este passo roda logo antes do robô.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const PORTAIS = [
  { nome: 'rio_das_flores', portal: '6pate64yBjikfhmXWCPx0Q==', consulta: 5384 },   // Boletim Municipal (link indicado pelo usuário, 10/11/2026)
];
const INICIO = process.env.INICIO || '2025-11-01', FIM = process.env.FIM || '2099-12-31';
const SAIDA = path.join(process.env.GITHUB_WORKSPACE || '.', 'listas');
const API = 'https://api.transparencia.betha.cloud/transparencia/api';
const iso = s => { const m = /(\d{2})\/(\d{2})\/(\d{4})/.exec(s || ''); return m ? `${m[3]}-${m[2]}-${m[1]}` : null; };
(async () => {
  fs.mkdirSync(SAIDA, { recursive: true });
  const b = await chromium.launch();
  for (const p of PORTAIS) {
    const t0 = Date.now(); const ctx = await b.newContext(); const pg = await ctx.newPage(); let cab = null;
    pg.on('request', q => { if (!cab && q.url().startsWith(API + '/busca-textual/' + p.consulta + '?')) { const h = q.headers(); cab = { authorization: h.authorization, 'app-context': h['app-context'], 'content-type': 'application/json;charset=UTF-8', accept: 'application/json' }; } });
    await pg.goto(`https://transparencia.betha.cloud/#/${p.portal}/consulta/${p.consulta}`, { timeout: 90000, waitUntil: 'load' }).catch(() => null);
    for (let i = 0; i < 60 && !cab; i++) await pg.waitForTimeout(1000);
    if (!cab) { console.log(`${p.nome}: a página não chamou a lista (nada gravado)`); await ctx.close(); continue; }
    const itens = []; let off = 0, total = 0, parar = false;
    while (!parar) {
      const r = await ctx.request.post(`${API}/busca-textual/${p.consulta}?sortBy=null&sortDirection=null&offset=${off}&limit=100&hiperlink=false`, { headers: cab, data: {} });
      if (!r.ok()) { console.log(`${p.nome}: lista respondeu ${r.status()} no offset ${off}`); break; }
      const j = await r.json(); total = j.totalHits; const hits = j.hits || [];
      for (const h of hits) {
        const s = h.sourceAsMap || {}; const d = iso(s.descricao) || iso(s.titulo);
        if (!d) continue;
        if (d < INICIO) { parar = true; continue; }   // a lista vem da mais nova para a mais antiga
        if (d > FIM) continue;
        const a = await ctx.request.get(`${API}/busca/${p.consulta}/anexos/${h.id}`, { headers: cab });
        const anexos = a.ok() ? await a.json() : [];
        const urls = anexos.filter(x => /pdf/i.test(x.tipo || x.nome || '')).map(x => x.url);
        const ed = (/N[ºo°]\s*([\d.]+)/i.exec(s.titulo || '') || [])[1] || '';
        itens.push({ data: d, edicao: ed.replace('.', ''), extra: /extra/i.test(s.titulo + ' ' + s.descricao), titulo: s.titulo, urls, nomes: anexos.map(x => x.nome) });
      }
      off += hits.length; if (!hits.length || off >= total) break;
    }
    fs.writeFileSync(path.join(SAIDA, `betha_${p.nome}.json`), JSON.stringify(itens));
    console.log(`${p.nome}: ${itens.length} edições de ${INICIO} a ${FIM} (${total} no portal), ${((Date.now() - t0) / 1000).toFixed(0)} s`);
    await ctx.close();
  }
  await b.close();
})();
