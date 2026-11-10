// Abre, num navegador de verdade (Chromium), a página do diário dos municípios problemáticos e lista os links de
// diário/boletim/PDF que aparecem. Só olha: não preenche nada, não contorna captcha, login nem bloqueio.
const { chromium } = require('playwright');
const alvos = {
 'Búzios':'https://buzios.aexecutivo.com.br', 'Búzios (prefeitura)':'https://www.buzios.rj.gov.br',
 'Barra Mansa':'https://portaltransparencia.barramansa.rj.gov.br/boletim-oficial/',
 'Duque de Caxias':'https://duquedecaxias.rj.gov.br/portal/boletim-oficial.html',
 'Iguaba Grande':'https://portal.iguaba.rj.gov.br', 'Maricá':'https://www.marica.rj.gov.br/jom/',
 'Nova Friburgo':'https://plenussistemas.dioenet.com.br/list/nova-friburgo',
 'São João da Barra':'https://www.sjb.rj.gov.br', 'Varre-Sai':'https://varresai.rj.gov.br',
 'Angra dos Reis':'https://angra.rj.gov.br/boletim-oficial', 'Miguel Pereira':'https://transparencia.miguelpereira.rj.gov.br',
 'Cabo Frio':'https://portal.cabofrio.rj.gov.br/diariooficial.php'};
(async()=>{
 const b=await chromium.launch();
 const ctx=await b.newContext({ignoreHTTPSErrors:false, userAgent:'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'});
 for (const [n,url] of Object.entries(alvos)){
  const pg=await ctx.newPage(); let r;
  try{ r=await pg.goto(url,{timeout:45000,waitUntil:'domcontentloaded'}); await pg.waitForTimeout(3000);
   const t=await pg.title(); const links=await pg.$$eval('a',as=>as.map(a=>[a.textContent.trim().slice(0,50),a.href]).filter(([t,h])=>/di[aá]rio|boletim|jom|\.pdf|edi[cç]/i.test(t+h)).slice(0,8));
   const desafio=/turnstile|captcha|challenge|cf-chl/i.test(await pg.content());
   console.log(JSON.stringify({n,status:r&&r.status(),final:pg.url(),title:t.slice(0,80),captcha:desafio,links}));
  }catch(e){console.log(JSON.stringify({n,erro:String(e.message).split('\n')[0].slice(0,150)}));}
  await pg.close();}
 await b.close();})();
