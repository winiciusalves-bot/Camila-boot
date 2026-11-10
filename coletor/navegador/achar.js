// Para os municípios sem coleta: abre a página inicial da prefeitura num navegador, acha o link de "Diário/Boletim/
// Jornal Oficial", entra nele e conta PDFs com data e chamadas de dados (JSON). Só páginas públicas; sem login/captcha.
const { chromium } = require('playwright');
const alvos = require('./alvos_achar.json');
const RXD = /di[aá]rio\s*oficial|boletim\s*oficial|jornal\s*oficial|imprensa\s*oficial|\bD\.?O\.?M\b|\bJOM\b|publica[cç][oõ]es\s*oficiais|atos\s*oficiais/i;
const DATA = /\d{1,2}[\/.\-_]\d{1,2}[\/.\-_]\d{4}|\d{4}[\/.\-_]\d{2}[\/.\-_]\d{2}|\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4}/i;
const LIXO = /google|clarity|userway|facebook|twitter|cdn-cgi|elementor|analytics|hotjar|vlibras/i;
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36' });
  for (const [n, urls] of Object.entries(alvos)) {
    const r = { n };
    const pg = await ctx.newPage();
    try {
      for (const u of urls) {
        const resp = await pg.goto(u, { timeout: 40000, waitUntil: 'domcontentloaded' }).catch(() => null);
        if (resp && resp.status() < 400) { r.site = pg.url(); break; }
      }
      if (!r.site) { r.erro = 'site não abriu'; console.log(JSON.stringify(r)); await pg.close(); continue; }
      await pg.waitForTimeout(3000);
      const html = await pg.content();
      r.captcha = /turnstile|g-recaptcha|hcaptcha|cf-chl|challenge-platform/i.test(html);
      const cand = await pg.$$eval('a', as => as.map(a => [a.textContent.replace(/\s+/g, ' ').trim().slice(0, 60), a.href]));
      const dl = cand.filter(([t, h]) => /di[aá]rio\s*oficial|boletim\s*oficial|jornal\s*oficial|imprensa\s*oficial|atos\s*oficiais/i.test(t) || /diario|boletim|jornal-oficial|\bdom\b|\bjom\b/i.test(h));
      r.links_diario = [...new Map(dl.map(x => [x[1], x])).values()].slice(0, 5);
      const alvo = r.links_diario.find(([t, h]) => h.startsWith('http') && !/facebook|instagram|youtube|#$/.test(h));
      if (alvo) {
        const xhr = [];
        const pg2 = await ctx.newPage();
        pg2.on('response', async q => { const t = q.request().resourceType(); if (['xhr', 'fetch'].includes(t) && !LIXO.test(q.url())) { let c = ''; try { c = (await q.text()).slice(0, 300); } catch (e) {} xhr.push(q.request().method() + ' ' + q.url().slice(0, 200) + ' | ' + (q.request().postData() || '').slice(0, 100) + ' => ' + c.replace(/\s+/g, ' ')); } });
        const rr = await pg2.goto(alvo[1], { timeout: 45000, waitUntil: 'networkidle' }).catch(() => null);
        await pg2.waitForTimeout(4000);
        const h2 = await pg2.content().catch(() => '');
        const pdfs = await pg2.$$eval('a', as => as.map(a => [a.textContent.replace(/\s+/g, ' ').trim().slice(0, 60), a.href, (a.closest('tr,li,div') || a).textContent.replace(/\s+/g, ' ').slice(0, 120)])).catch(() => []);
        const comPdf = pdfs.filter(([t, h]) => /\.pdf|download|arquivo|visualiz|baixar/i.test(h + ' ' + t));
        r.pagina_diario = pg2.url(); r.status = rr && rr.status(); r.captcha_diario = /turnstile|g-recaptcha|hcaptcha|cf-chl/i.test(h2);
        r.n_pdf = comPdf.length; r.n_pdf_data = comPdf.filter(x => DATA.test(x.join(' '))).length;
        r.exemplos = comPdf.filter(x => DATA.test(x.join(' '))).slice(0, 3).map(x => x.slice(0, 2));
        r.frames = pg2.frames().map(f => f.url()).filter(u => u && u !== 'about:blank' && u !== pg2.url() && !LIXO.test(u)).slice(0, 3);
        r.xhr = xhr.slice(0, 4);
        await pg2.close();
      }
    } catch (e) { r.erro = String(e.message).split('\n')[0].slice(0, 120); }
    console.log(JSON.stringify(r));
    await pg.close();
  }
  await b.close();
})();
