// São João da Barra, São José de Ubá, Italva e Cardoso Moreira: mesmo sistema de site (AngularJS). A página pública /site/diarios_oficiais
// pede a lista por POST a controllers/diario_oficial/class_diario.php e recebe JSON (numero, ano, data, arquivo).
// Fora do navegador o servidor responde 403 (11/11/2026), então abrimos a página como visitante, lemos a resposta
// que a própria página recebe e baixamos os PDFs da janela INICIO–FIM. Sem login, sem captcha, sem contornar nada.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const W = process.env.GITHUB_WORKSPACE || '.';
const INICIO = process.env.INICIO || '2026-10-01', FIM = process.env.FIM || '2099-12-31', SO = new RegExp(process.env.SO || '.');
const SITES = [
  { nome: 'sao_joao_da_barra', ibge: '3304904', base: 'https://sjb.rj.gov.br' },
  { nome: 'sao_jose_de_uba', ibge: '3305133', base: 'https://saojosedeuba.rj.gov.br' },
  { nome: 'italva', ibge: '3302056', base: 'https://www.italva.rj.gov.br' },              // mesmo sistema (11/11/2026)
  { nome: 'cardoso_moreira', ibge: '3301157', base: 'https://www.cardosomoreira.rj.gov.br' },
  { nome: 'bom_jesus_do_itabapoana', ibge: '3300605', base: 'https://bomjesus.rj.gov.br' },
];
fs.mkdirSync(path.join(W, 'out'), { recursive: true });
(async () => {
  const b = await chromium.launch();
  for (const s of SITES) {
    if (!SO.test('rj_' + s.nome)) continue;
    const t0 = Date.now(); const itens = []; let falhas = 0;
    const PASTA = path.join(W, 'pdf', s.nome); fs.mkdirSync(PASTA, { recursive: true });
    const ctx = await b.newContext(); const pg = await ctx.newPage();
    try {
      const [resp] = await Promise.all([
        pg.waitForResponse(r => r.url().includes('class_diario.php') && r.request().method() === 'POST', { timeout: 90000 }),
        pg.goto(s.base + '/site/diarios_oficiais', { timeout: 90000, waitUntil: 'domcontentloaded' }),
      ]);
      const lista = await resp.json();
      console.log(`${s.nome}: lista com ${lista.length} edições`);
      for (const it of lista) {
        const m = /(\d{2})\/(\d{2})\/(\d{4})/.exec(it.data || ''); if (!m || !it.arquivo) continue;
        const d = `${m[3]}-${m[2]}-${m[1]}`; if (d < INICIO || d > FIM) continue;
        const url = `${s.base}/arquivos/diario_oficial/${it.arquivo}`;
        const destino = path.join(PASTA, it.arquivo.replace(/[^\w.\-]+/g, '_'));
        if (!fs.existsSync(destino)) {
          try {
            const r = await ctx.request.get(url, { timeout: 120000 });
            const corpo = await r.body();
            if (r.status() !== 200 || corpo.slice(0, 5).toString() !== '%PDF-') { falhas++; continue; }
            fs.writeFileSync(destino, corpo);
          } catch (e) { falhas++; continue; }
        }
        itens.push({ date: d, edition_number: `${it.numero}/${it.ano}`, is_extra_edition: /extra/i.test((it.descricao || '') + it.arquivo),
                     territory_id: s.ibge, power: 'executive', file_urls: [url], files: [{ url, path: path.relative(path.join(W, 'pdf'), destino) }] });
      }
    } catch (e) { console.log(`${s.nome}: falhou (${String(e.message).split('\n')[0].slice(0, 120)}); registrado, sem contornar`); }
    fs.writeFileSync(path.join(W, 'out', `rj_${s.nome}.jsonl`), itens.map(x => JSON.stringify(x)).join('\n') + (itens.length ? '\n' : ''));
    console.log(`${s.nome}: ${itens.length} edições de ${INICIO} a ${FIM}, ${falhas} PDFs não baixados (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
    await ctx.close();
  }
  await b.close();
})();
