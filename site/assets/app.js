(function () {
  'use strict';
  var C = window.SITE_CONFIG || {}, P = window.RADAR_PUBLICO || null;
  function br(d) { var p = (d || '').split('-'); return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : d; }
  function num(n) { return Number(n).toLocaleString('pt-BR'); }
  function waLink(msg) { return 'https://wa.me/' + C.whatsapp + '?text=' + encodeURIComponent(msg); }

  // Botões de WhatsApp
  document.querySelectorAll('.js-wa').forEach(function (a) {
    a.href = waLink(a.getAttribute('data-msg') || 'Olá!');
    a.target = '_blank'; a.rel = 'noopener';
  });
  var tel = document.getElementById('tel-rodape');
  if (tel) {
    var n = C.whatsapp.replace(/^55/, '');
    tel.textContent = '(' + n.slice(0, 2) + ') ' + n.slice(2, 7) + '-' + n.slice(7) + (C.whatsappProvisorio ? ' (número provisório)' : '');
  }

  var cr = document.getElementById('crea-rodape');
  if (cr) cr.textContent = 'CREA-RJ nº ' + (C.creaRegistro || '(a informar)') + ' · Responsável técnico: ' + (C.responsavelTecnico || '(a informar)');

  // Painel agregado: ao vivo do banco (só totais, função resumo_publico) ou, sem banco, do arquivo publico.js
  function painel(P) {
    if (!P || !P.autos || !P.tipos || !P.tipos.length) return;
    document.getElementById('kpi-autos').textContent = num(P.autos);
    document.getElementById('kpi-cnpjs').textContent = num(P.cnpjs);
    document.getElementById('kpi-cancel').textContent = num(P.cancelados);
    document.getElementById('painel-periodo').textContent = 'Autos de ' + br(P.de) + ' a ' + br(P.ate);
    document.querySelectorAll('.js-coleta').forEach(function (e) { e.textContent = br(P.coleta || ''); });
    document.querySelectorAll('.js-periodo').forEach(function (e) { e.textContent = br(P.de) + ' a ' + br(P.ate); });
    var max = P.tipos[0][1], h = '';
    P.tipos.forEach(function (t) {
      var nome = String(t[0] || 'Não informado').replace(/[&<>"']/g, '');
      h += '<div class="barra"><span class="barra-n">' + nome + '</span><span class="barra-t"><i style="width:' + Math.max(2, t[1] / max * 100) + '%"></i></span><span class="barra-v">' + Number(t[1]) + '</span></div>';
    });
    document.getElementById('barras-tipo').innerHTML = h;
  }
  painel(P);
  if (C.supabaseUrl && C.supabaseAnonKey && window.fetch) {
    fetch(C.supabaseUrl.replace(/\/$/, '') + '/rest/v1/rpc/resumo_publico', {
      method: 'POST', headers: Object.assign({ apikey: C.supabaseAnonKey, 'Content-Type': 'application/json' }, /^eyJ/.test(C.supabaseAnonKey) ? { Authorization: 'Bearer ' + C.supabaseAnonKey } : {}), body: '{}'
    }).then(function (r) { return r.ok ? r.json() : null; }).then(painel).catch(function () {});
  }

  // CNPJ
  function cnpjOk(c) {
    c = (c || '').replace(/\D/g, '');
    if (c.length !== 14 || /^(\d)\1+$/.test(c)) return false;
    function d(b, p) { var s = 0; for (var i = 0; i < p.length; i++) s += +b[i] * p[i]; var r = s % 11; return r < 2 ? 0 : 11 - r; }
    var p1 = [5,4,3,2,9,8,7,6,5,4,3,2];
    return d(c, p1) === +c[12] && d(c, [6].concat(p1)) === +c[13];
  }
  window.cnpjOk = cnpjOk;
  var fc = document.getElementById('c-cnpj');
  if (fc) fc.addEventListener('input', function () {
    var v = fc.value.replace(/\D/g, '').slice(0, 14);
    fc.value = v.replace(/^(\d{2})(\d)/, '$1.$2').replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3').replace(/\.(\d{3})(\d)/, '.$1/$2').replace(/(\d{4})(\d)/, '$1-$2');
    document.getElementById('e-cnpj').hidden = !(v.length === 14 && !cnpjOk(v));
  });

  // Campos do auto só aparecem quando o assunto é auto de infração
  var as = document.getElementById('c-assunto');
  if (as) { var tg = function () { document.querySelectorAll('.so-auto').forEach(function (e) { e.hidden = !/auto/i.test(as.value); }); }; as.addEventListener('change', tg); tg(); }

  // Animações: entrada ao rolar e contadores (respeita quem pediu menos movimento)
  var calmo = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var rev = document.querySelectorAll('.revela');
  if (!calmo && 'IntersectionObserver' in window) {
    document.documentElement.classList.add('anima');
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('visivel'); io.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    rev.forEach(function (e, i) { e.style.transitionDelay = (i % 4) * 70 + 'ms'; io.observe(e); });
  }
  window.contarKpis = function () {
    document.querySelectorAll('.kpi').forEach(function (k) {
      var alvo = parseInt(String(k.textContent).replace(/\D/g, ''), 10); if (!alvo || calmo) return;
      var t0 = null; (function passo(t) { t0 = t0 || t; var f = Math.min(1, (t - t0) / 1200); k.textContent = Math.round(alvo * (1 - Math.pow(1 - f, 3))).toLocaleString('pt-BR'); if (f < 1) requestAnimationFrame(passo); })(performance.now());
    });
  };
  var pn = document.querySelector('.painel');
  if (pn && 'IntersectionObserver' in window) new IntersectionObserver(function (es, o) { if (es[0].isIntersecting) { o.disconnect(); window.contarKpis(); } }).observe(pn);

  // Formulário -> WhatsApp
  var f = document.getElementById('form-wa');
  if (f) f.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var g = function (id) { return document.getElementById(id).value.trim(); };
    var err = document.getElementById('e-form'), msgs = [];
    if (!g('c-nome')) msgs.push('Informe seu nome.');
    if (g('c-cnpj') && !cnpjOk(g('c-cnpj'))) msgs.push('Confira o CNPJ.');
    if (!document.getElementById('c-lgpd').checked) msgs.push('Marque a autorização de uso dos dados.');
    err.hidden = !msgs.length; err.textContent = msgs.join(' ');
    if (msgs.length) return;
    var linhas = ['Olá! Vim pelo site da ' + C.nomeEmpresa + '.', 'Assunto: ' + g('c-assunto'), 'Nome: ' + g('c-nome')];
    var ehAuto = /auto/i.test(g('c-assunto'));
    if (g('c-emp')) linhas.push('Empresa: ' + g('c-emp'));
    if (g('c-cnpj')) linhas.push('CNPJ: ' + g('c-cnpj'));
    if (ehAuto) linhas.push('Órgão: ' + g('c-org'));
    if (ehAuto && g('c-auto')) linhas.push('Nº do auto: ' + g('c-auto'));
    if (ehAuto && g('c-data')) linhas.push('Recebi o auto em: ' + br(g('c-data')));
    if (g('c-msg')) linhas.push('', g('c-msg'));
    window.open(waLink(linhas.join('\n')), '_blank', 'noopener');
  });
})();
