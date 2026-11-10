// Para os sites onde o robô de lista não achou PDF: compara o HTML cru com a página montada pelo navegador,
// lista os links que parecem edição e as chamadas de dados (XHR/fetch) que a página faz. Só olha.
const { chromium } = require('playwright');
const alvos = require('./alvos_links.json');
const RX = /\.pdf|download|arquivo|visualizar|edi[cç][aã]o|di[aá]rio|jornal|boletim|\/\d{4}\/\d{2}\//i;
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36' });
  for (const [n, url] of Object.entries(alvos)) {
    const pg = await ctx.newPage(); const xhr = [];
    pg.on('request', q => { if (['xhr', 'fetch'].includes(q.resourceType())) xhr.push(q.method() + ' ' + q.url().slice(0, 200)); });
    let cru = 0;
    try { const r = await ctx.request.get(url, { timeout: 30000 }); cru = (await r.text()).length; } catch (e) { cru = 'erro'; }
    try {
      const r = await pg.goto(url, { timeout: 60000, waitUntil: 'networkidle' }).catch(() => null);
      await pg.waitForTimeout(4000);
      const html = await pg.content();
      const links = await pg.$$eval('a', as => as.map(a => [a.textContent.replace(/\s+/g, ' ').trim().slice(0, 70), a.href]));
      const bons = links.filter(([t, h]) => /\.pdf|download|arquivo|visualizar|edi[cç][aã]o|\/\d{4}\/\d{2}\//i.test(t + ' ' + h));
      const frames = pg.frames().map(f => f.url()).filter(u => u && u !== 'about:blank' && u !== pg.url());
      console.log(JSON.stringify({ n, url, status: r && r.status(), final: pg.url(), html_cru: cru, html_montado: html.length,
        total_links: links.length, links_edicao: bons.length, exemplos: bons.slice(0, 12), frames: frames.slice(0, 5),
        xhr: [...new Set(xhr)].slice(0, 15), captcha: /turnstile|g-recaptcha|hcaptcha|cf-chl/i.test(html) }));
    } catch (e) { console.log(JSON.stringify({ n, url, erro: String(e.message).split('\n')[0].slice(0, 150) })); }
    await pg.close();
  }
  await b.close();
})();
