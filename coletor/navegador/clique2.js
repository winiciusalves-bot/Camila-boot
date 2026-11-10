// Sondagem com clique (10/11/2026): abre página pública, clica no item indicado pelo texto, mostra texto, links de PDF e chamadas de dados.
// Não preenche login, não contorna captcha.
const { chromium } = require('playwright');
const ALVOS = [
  { n: 'tangua', url: 'https://webtangua.supernova.com.br:8443/contaspublicas/pages/publicacao_demais_relatorio.xhtml?faces-redirect=true&idTipoRelatorio=1', clicar: ['#j_idt62_button', 'a:has-text("Diário oficial") >> visible=true', 'label:has-text("Selecione") >> visible=true', 'li:has-text("Diário Oficial") >> visible=true', 'button:has-text("Pesquisar") >> visible=true'] },
  // { n: 'betha', url: 'https://transparencia.betha.cloud/#/6pate64yBjikfhmXWCPx0Q==/consulta/5384', clicar: ['text=Ver arquivos >> nth=0'] },
];
const LIXO = /google|clarity|userway|facebook|vlibras|hotjar|cdn-cgi|elementor/i;
async function foto(pg) {
  for (let i = 0; i < 3; i++) {
    try {
      await pg.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => null);
      const texto = (await pg.innerText('body')).replace(/\s+/g, ' ').slice(0, 2500);
      const links = await pg.$$eval('a', as => as.map(a => [a.textContent.replace(/\s+/g, ' ').trim().slice(0, 70), a.href, (a.getAttribute('onclick') || '').slice(0, 120)])
        .filter(([t, h, o]) => /\.pdf|download|arquivo|visualiz|anexo/i.test(h + o) || /baixar|download|visualizar|pdf|edi[cç][aã]o/i.test(t)));
      return { final: pg.url(), texto, nlinks: links.length, links: links.slice(0, 30) };
    } catch (e) { await pg.waitForTimeout(3000); }
  }
  return { erro: 'navegação não estabilizou' };
}
(async () => {
  const b = await chromium.launch({ args: ['--ignore-certificate-errors'] });
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36', ignoreHTTPSErrors: true });
  for (const a of ALVOS) {
    const pg = await ctx.newPage(); const xhr = [];
    pg.on('response', async r => {
      const q = r.request();
      if (!['xhr', 'fetch'].includes(q.resourceType()) || LIXO.test(q.url())) return;
      let c = ''; try { c = (await r.text()).slice(0, 6000); } catch (e) {}
      const h = q.headers(); xhr.push({ m: q.method(), u: q.url().slice(0, 300), env: (q.postData() || '').slice(0, 600), st: r.status(), cab: Object.fromEntries(Object.entries(h).filter(([k]) => !/user-agent|accept-lang|sec-|referer|accept-enc/.test(k))), resp: c });
    });
    await pg.goto(a.url, { timeout: 60000, waitUntil: 'load' }).catch(e => console.log(a.n, 'goto', String(e.message).slice(0, 100)));
    await pg.waitForTimeout(6000);
    console.log(JSON.stringify({ n: a.n, etapa: 'aberta', ...(await foto(pg)) }));
    for (const c of a.clicar) {
      try { await pg.click(c, { timeout: 15000 }); await pg.waitForTimeout(8000); console.log(JSON.stringify({ n: a.n, etapa: 'clicou ' + c, ...(await foto(pg)) })); }
      catch (e) { console.log(JSON.stringify({ n: a.n, etapa: 'clique falhou ' + c, erro: String(e.message).slice(0, 150) })); }
    }
    console.log(JSON.stringify({ n: a.n, xhr: xhr.slice(-10) }));
    await pg.close();
  }
  await b.close();
})();
