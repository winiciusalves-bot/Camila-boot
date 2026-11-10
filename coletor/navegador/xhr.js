// 2ª sondagem: para cada página, mostra as chamadas de dados (corpo enviado e começo da resposta) e todos os links de PDF.
// Só olha a página pública; não preenche formulário de login, não contorna captcha nem bloqueio.
const { chromium } = require('playwright');
const alvos = require('./alvos_xhr.json');
const LIXO = /google|clarity|userway|facebook|twitter|allorigins|cdn-cgi|popular-posts|getColors|golog|LastVisitante|sso\/users|notifications|configurations|elementor/i;
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36' });
  for (const [n, url] of Object.entries(alvos)) {
    const pg = await ctx.newPage(); const xhr = [];
    pg.on('response', async r => {
      const q = r.request();
      if (!['xhr', 'fetch'].includes(q.resourceType()) || LIXO.test(q.url())) return;
      let corpo = ''; try { corpo = (await r.text()).slice(0, 2500); } catch (e) {}
      xhr.push({ m: q.method(), u: q.url().slice(0, 300), enviado: (q.postData() || '').slice(0, 900), st: r.status(), resp: corpo });
    });
    try {
      await pg.goto(url, { timeout: 60000, waitUntil: 'networkidle' }).catch(() => null);
      await pg.waitForTimeout(5000);
      const pdfs = await pg.$$eval('a', as => as.map(a => [a.textContent.replace(/\s+/g, ' ').trim().slice(0, 80), a.href])
        .filter(([t, h]) => /\.pdf|download|arquivo|visualiz|di[aá]rio|edi[cç]/i.test(h) || /edi[cç][aã]o|di[aá]rio oficial|baixar|download/i.test(t)));
      const forms = await pg.$$eval('form', fs => fs.map(f => ({ action: f.action, method: f.method, campos: [...f.elements].map(e => e.name + '=' + (e.value || '').slice(0, 20)).slice(0, 15) })));
      console.log(JSON.stringify({ n, url, final: pg.url(), pdfs: pdfs.slice(0, 40), forms: forms.slice(0, 4), xhr: xhr.slice(0, 8) }));
    } catch (e) { console.log(JSON.stringify({ n, url, erro: String(e.message).split('\n')[0].slice(0, 150) })); }
    await pg.close();
  }
  await b.close();
})();
