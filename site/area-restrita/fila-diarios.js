// Aba "Diários a conferir" (pedido do usuário em 18/11/2026).
// Achados dos diários das prefeituras (INDÍCIO). Quem confere lê o ato e marca "É FATO" ou "Descartar".
// O coletor diário (coletor/fila_diarios.py) transforma o que foi marcado como FATO em empresa da base.
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var sb = null, L = [], ok = null, carregando = false, ligado = false, aberto = null;
  var PRE = { provavel: ['Provável ambiental', 'selo-apr'], duvidoso: ['Duvidoso', 'selo-amar'], provavel_falso: ['Provável não ambiental', 'selo-verm'] };
  var TIPOS = ['auto de infração ambiental', 'embargo', 'interdição', 'notificação ambiental'];
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function br(d) { d = String(d || '').slice(0, 10); var p = d.split('-'); return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : d; }
  function semAcento(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  // número com cara de CPF sai mascarado mesmo se o coletor deixou passar
  function masc(t) { return String(t || '').replace(/(^|[^\d./-])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d/])/g, '$1[CPF omitido]'); }
  // destaca as palavras que fizeram o robô parar aqui
  function realce(t) { return esc(masc(t)).replace(/(auto de infra[çc][ãa]o|embargo|interdi[çc][ãa]o|meio ambiente|ambiental|postura|sanit[áa]ri\w*)/gi, '<mark>$1</mark>'); }

  function todos() {
    var out = [], passo = 1000;
    function pag(i) {
      return sb.from('fila_diarios').select('*').order('data_documento', { ascending: false }).range(i, i + passo - 1).then(function (r) {
        if (r.error) return r;
        out = out.concat(r.data);
        return r.data.length < passo ? { data: out } : pag(i + passo);
      });
    }
    return pag(0);
  }

  function carregar() {
    if (carregando) return; carregando = true;
    $('d-info').textContent = 'Carregando…';
    todos().then(function (r) {
      carregando = false;
      if (r.error) { ok = false; $('d-info').textContent = ''; $('d-cards').innerHTML = '<p class="nota">A fila ainda não existe no banco. É preciso rodar uma vez o arquivo <strong>supabase/10_fila_diarios.sql</strong> no Supabase (SQL Editor). Depois disso, a coleta diária enche a fila sozinha.</p>'; return; }
      ok = true; L = r.data;
      var muns = Array.from(new Set(L.map(function (x) { return x.municipio; }).filter(Boolean))).sort();
      var v = $('d-mun').value;
      $('d-mun').innerHTML = '<option value="">Todos</option>' + muns.map(function (m) { return '<option>' + esc(m) + '</option>'; }).join('');
      $('d-mun').value = v;
      render();
    });
  }

  function render() {
    if (!ok) return;
    var st = $('d-st').value, pre = $('d-pre').value, mun = $('d-mun').value, q = semAcento($('d-q').value).trim();
    var pend = L.filter(function (x) { return x.status === 'a_conferir'; }).length;
    $('n-dia').textContent = pend || '';
    var ordem = { provavel: 0, duvidoso: 1, provavel_falso: 2 };
    var l = L.filter(function (x) {
      return (!st || x.status === st) && (!pre || x.pretriagem === pre) && (!mun || x.municipio === mun) &&
        (!q || semAcento([x.nome, x.cnpj, x.cnpj.replace(/\D/g, ''), x.trecho].join(' ')).indexOf(q) >= 0);
    }).sort(function (a, b) {
      var o = (ordem[a.pretriagem] == null ? 1 : ordem[a.pretriagem]) - (ordem[b.pretriagem] == null ? 1 : ordem[b.pretriagem]);
      return o || (String(a.data_documento) < String(b.data_documento) ? 1 : -1);
    });
    var cnpjs = new Set(l.map(function (x) { return x.cnpj; })).size;
    $('d-info').textContent = l.length + ' achado(s) de ' + cnpjs + ' CNPJ(s) · ' + pend + ' a conferir no total. Ordem: provável ambiental primeiro, depois os mais novos.';
    $('d-cards').innerHTML = l.slice(0, 200).map(card).join('') || '<p class="nota">Nada aqui com esses filtros.</p>';
    if (l.length > 200) $('d-cards').insertAdjacentHTML('beforeend', '<p class="nota">Mostrando 200. Use os filtros para ver o resto.</p>');
  }

  function card(x) {
    var p = PRE[x.pretriagem] || ['Sem pré-triagem', ''];
    var decidido = x.status !== 'a_conferir';
    var h = '<article class="card-f" data-chave="' + esc(x.chave) + '">' +
      '<h3>' + esc(x.nome || 'Razão social não conferida') + '</h3>' +
      '<div class="cf-meta">' + esc(x.cnpj) + ' · ' + esc(x.municipio || '') + ' · diário de ' + esc(br(x.data_documento)) + ' · termos: ' + esc(x.assunto || '') + '</div>' +
      '<div class="selos-l"><span class="selo ' + p[1] + '" title="' + esc(x.pretriagem_motivo || '') + '">' + esc(p[0]) + '</span>' +
      (x.status === 'fato' ? '<span class="selo selo-apr">É FATO: ' + esc(x.tipo_confirmado || '') + (x.numero_ato ? ' nº ' + esc(x.numero_ato) : '') + '</span>' : '') +
      (x.status === 'descartado' ? '<span class="selo selo-verm">Descartado</span>' : '') + '</div>' +
      (x.pretriagem_motivo ? '<div class="cf-meta">Pré-triagem: ' + esc(x.pretriagem_motivo) + '</div>' : '') +
      '<div class="cf-mot">' + realce(x.trecho) + '</div>' +
      (decidido ? '<div class="cf-meta">' + esc(x.autor_email || '') + (x.conferido_em ? ' em ' + esc(new Date(x.conferido_em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })) : '') + (x.nota ? ' · ' + esc(x.nota) : '') + '</div>' : '') +
      '<div class="cf-acoes">' + (x.link_fonte ? '<a class="btn btn-linha btn-sm" href="' + esc(x.link_fonte) + '" target="_blank" rel="noopener">Abrir o diário</a>' : '');
    if (decidido) h += '<button class="btn btn-linha btn-sm" type="button" data-d-voltar>Voltar para conferir</button>';
    else h += '<button class="btn btn-wa btn-sm" type="button" data-d-fato>✓ É FATO</button><button class="btn btn-linha btn-sm" type="button" data-d-desc>✕ Descartar</button>';
    h += '</div>';
    if (aberto === x.chave) h += form(x);
    return h + '</article>';
  }

  function form(x) {
    return '<form class="busca d-form" data-d-form onsubmit="return false">' +
      '<label class="campo"><span>O que o ato é</span><select data-d-tipo>' + TIPOS.map(function (t) { return '<option>' + esc(t) + '</option>'; }).join('') + '</select></label>' +
      '<label class="campo"><span>Nº do ato</span><input data-d-num placeholder="ex.: 105/2025"></label>' +
      '<label class="campo"><span>Data do ato (se o diário disser)</span><input type="date" data-d-data></label>' +
      '<label class="campo campo-grande"><span>Nota (opcional)</span><input data-d-nota placeholder="O que você conferiu no ato"></label>' +
      '<button class="btn btn-wa btn-sm" type="button" data-d-salvar>Confirmar: li o ato e é FATO</button></form>';
  }

  function gravar(chave, campos) {
    campos.conferido_em = campos.status === 'a_conferir' ? null : new Date().toISOString();
    return sb.auth.getUser().then(function (u) {
      campos.autor_email = campos.status === 'a_conferir' ? null : ((u.data && u.data.user && u.data.user.email) || null);
      return sb.from('fila_diarios').update(campos).eq('chave', chave).select();
    }).then(function (r) {
      if (r.error || !r.data || !r.data.length) { alert('Não foi possível gravar: ' + ((r.error && r.error.message) || 'sem permissão')); return; }
      L = L.map(function (x) { return x.chave === chave ? r.data[0] : x; }); aberto = null; render();
    });
  }

  function ligar() {
    if (ligado) return; ligado = true;
    ['d-st', 'd-pre', 'd-mun', 'd-q'].forEach(function (id) { $(id).addEventListener('input', render); });
    $('d-cards').addEventListener('click', function (ev) {
      var art = ev.target.closest('[data-chave]'); if (!art) return;
      var chave = art.getAttribute('data-chave');
      if (ev.target.closest('[data-d-fato]')) { aberto = aberto === chave ? null : chave; render(); return; }
      if (ev.target.closest('[data-d-desc]')) {
        var nota = prompt('Por que descartar? (opcional; ex.: fiscalização de posturas, CNPJ de outra parte do ato)');
        if (nota === null) return;
        gravar(chave, { status: 'descartado', tipo_confirmado: null, numero_ato: null, data_ato: null, nota: nota || null }); return;
      }
      if (ev.target.closest('[data-d-voltar]')) { gravar(chave, { status: 'a_conferir', tipo_confirmado: null, numero_ato: null, data_ato: null, nota: null }); return; }
      if (ev.target.closest('[data-d-salvar]')) {
        var f = art.querySelector('[data-d-form]');
        gravar(chave, { status: 'fato', tipo_confirmado: f.querySelector('[data-d-tipo]').value,
          numero_ato: f.querySelector('[data-d-num]').value.trim() || null, data_ato: f.querySelector('[data-d-data]').value || null,
          nota: f.querySelector('[data-d-nota]').value.trim() || null });
      }
    });
  }

  window.FilaDiarios = {
    abrir: function (cliente) {
      ligar();
      if (!cliente) { $('d-cards').innerHTML = '<p class="nota">A fila dos diários só funciona com o login (Supabase), não na prévia local.</p>'; return; }
      sb = cliente;
      if (ok === null) carregar(); else render();
    }
  };
})();
