// 3ª sondagem: clica no primeiro link de edição e anota para onde o navegador vai (download, nova aba ou requisição).
// Também testa se a pasta dos PDFs mostra a lista de arquivos. Só páginas públicas; nada de login ou captcha.
const { chromium } = require('playwright');
const cliques = {
  duque_de_caxias: ['https://transparencia.duquedecaxias.rj.gov.br/diario_oficial_busca.php', 'text=/Nº\\s*\\d+/'],
  natividade: ['https://www.natividade.rj.gov.br/diario-oficial?category[0]=3&category_children=1', 'text=/Baixar pdf/'],
  miguel_pereira: ['https://transparencia.miguelpereira.rj.gov.br/?serv=113', 'text=/Diário Oficial do Município/'],
  barra_do_pirai: ['https://barradopirai.rj.gov.br/page/4edb08b8-3bae-4279-ad18-e8b88e798bda/diario-oficial-eletronico', 'text=/Boletim Municipal/'],
};
const pastas = ['https://paracambi.rj.gov.br/diariooficial/', 'https://patydoalferes.rj.gov.br/wp-content/uploads/auto-publication/diario-oficial/2026/',
  'https://do.ib.itaborai.rj.gov.br/edicoes/2026/', 'https://paracambi.rj.gov.br/diario-oficial-eletronico-2026/', 'https://patydoalferes.rj.gov.br/diario-oficial/'];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ acceptDownloads: true, userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36' });
  for (const [n, [url, sel]] of Object.entries(cliques)) {
    const pg = await ctx.newPage(); const reqs = [];
    pg.on('request', q => { if (!/google|clarity|userway|facebook|twitter|\.(css|js|png|jpg|svg|woff2?)(\?|$)/i.test(q.url())) reqs.push(q.method() + ' ' + q.url().slice(0, 250) + (q.postData() ? ' | ' + q.postData().slice(0, 200) : '')); });
    try {
      await pg.goto(url, { timeout: 60000, waitUntil: 'networkidle' }).catch(() => null);
      await pg.waitForTimeout(3000);
      const el = pg.locator(sel).first();
      const html = await el.evaluate(e => (e.closest('a,button,div') || e).outerHTML.slice(0, 600)).catch(e => 'sem elemento: ' + e.message.slice(0, 80));
      const antes = reqs.length;
      const [pop, dl] = await Promise.all([
        ctx.waitForEvent('page', { timeout: 15000 }).catch(() => null),
        pg.waitForEvent('download', { timeout: 15000 }).catch(() => null),
        el.click({ timeout: 10000 }).catch(() => null)]);
      await pg.waitForTimeout(4000);
      console.log(JSON.stringify({ n, html, popup: pop && pop.url(), download: dl && dl.url(), depois: reqs.slice(antes, antes + 12), pagina: pg.url() }));
      if (pop) await pop.close();
    } catch (e) { console.log(JSON.stringify({ n, erro: String(e.message).slice(0, 150) })); }
    await pg.close();
  }
  for (const u of pastas) {
    try {
      const r = await ctx.request.get(u, { timeout: 30000 }); const t = await r.text();
      const pdfs = [...t.matchAll(/href=["']([^"']+\.pdf)["']/gi)].map(m => m[1]);
      console.log(JSON.stringify({ pasta: u, status: r.status(), tamanho: t.length, indice: /Index of|Parent Directory/i.test(t), n_pdfs: pdfs.length, exemplos: pdfs.slice(0, 6) }));
    } catch (e) { console.log(JSON.stringify({ pasta: u, erro: String(e.message).slice(0, 120) })); }
  }
  await b.close();
})();
