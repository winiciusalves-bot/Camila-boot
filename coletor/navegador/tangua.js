// Tanguá: Diário Oficial no portal Supernova (Contas Públicas > Diário oficial). Página pública, sem captcha
// (link indicado pelo usuário em 10/11/2026). A lista é JSF/PrimeFaces e o PDF sai por envio de formulário,
// então o navegador clica como um visitante e salva os PDFs da janela INICIO–FIM.
// Grava pdf/tangua/*.pdf e out/rj_tangua.jsonl no mesmo formato dos robôs Scrapy (date, edition_number, files[path,url]).
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const URL = 'https://webtangua.supernova.com.br:8443/contaspublicas/pages/publicacao_demais_relatorio.xhtml?faces-redirect=true&idTipoRelatorio=1';
const W = process.env.GITHUB_WORKSPACE || '.';
const INICIO = process.env.INICIO || '2026-10-01', FIM = process.env.FIM || '2099-12-31';
const PASTA = path.join(W, 'pdf', 'tangua'); fs.mkdirSync(PASTA, { recursive: true }); fs.mkdirSync(path.join(W, 'out'), { recursive: true });
const RX = /N[ºo°]\s*(\d+)\D+?(\d{2})(\d{2})(\d{4})/i;
(async () => {
  const t0 = Date.now(); const b = await chromium.launch();
  const ctx = await b.newContext({ acceptDownloads: true }); const pg = await ctx.newPage();
  const itens = [];
  for (let ano = +INICIO.slice(0, 4); ano <= +FIM.slice(0, 4); ano++) {
    await pg.goto(URL, { timeout: 90000, waitUntil: 'load' });
    await pg.fill('input[name="campo_exercicio"]', String(ano)).catch(() => null);
    await pg.click('#j_idt62_button'); await pg.waitForTimeout(1500);
    await pg.click('a:has-text("Diário oficial") >> visible=true'); await pg.waitForLoadState('networkidle').catch(() => null);
    await pg.click('button:has-text("Pesquisar") >> visible=true'); await pg.waitForTimeout(4000);
    let pagina = 1;
    while (true) {
      const linhas = await pg.$$eval('a[onclick*="demais_relatorios"]', as => as.map((a, i) => [i, a.textContent.trim()]));
      for (const [i, nome] of linhas) {
        const m = RX.exec(nome); if (!m) continue;
        const d = `${m[4]}-${m[3]}-${m[2]}`;
        if (d < INICIO || d > FIM) continue;
        const destino = path.join(PASTA, nome.replace(/[^\w.\-]+/g, '_'));
        if (!fs.existsSync(destino)) {
          try {
            const [dl] = await Promise.all([pg.waitForEvent('download', { timeout: 60000 }), pg.locator('a[onclick*="demais_relatorios"]').nth(i).click()]);
            await dl.saveAs(destino);
          } catch (e) { console.log(`tangua: falhou ${nome}: ${String(e.message).slice(0, 80)}`); continue; }
        }
        itens.push({ date: d, edition_number: m[1], is_extra_edition: /extra/i.test(nome), territory_id: '3305752', power: 'executive',
                     file_urls: [URL], files: [{ url: URL, path: path.relative(path.join(W, 'pdf'), destino) }] });
      }
      const prox = pg.locator('.ui-paginator-next:not(.ui-state-disabled) >> visible=true').first();
      if (!(await prox.count())) break;
      await prox.click(); await pg.waitForTimeout(2500); pagina++;
      if (pagina > 80) break;
    }
    console.log(`tangua ${ano}: ${pagina} página(s) lidas, ${itens.length} edições na janela até agora (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
  }
  fs.writeFileSync(path.join(W, 'out', 'rj_tangua.jsonl'), itens.map(x => JSON.stringify(x)).join('\n') + (itens.length ? '\n' : ''));
  console.log(`tangua: ${itens.length} edições de ${INICIO} a ${FIM}`);
  await b.close();
})();
