// Login da área restrita aberto na própria página inicial (janela sobreposta).
// Depois de entrar, vai para area-restrita/, que reaproveita a mesma sessão do Supabase.
(function () {
  'use strict';
  var C = window.SITE_CONFIG || {}, dlg = document.getElementById('dlg-login');
  var $ = function (id) { return document.getElementById(id); };
  var SB_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js';
  var cliente = null;
  if (!dlg || typeof dlg.showModal !== 'function' || !C.supabaseUrl || !C.supabaseAnonKey) return; // sem suporte: o link abre a página de login normal

  function carregar() {
    if (cliente) return Promise.resolve(cliente);
    return new Promise(function (ok, falha) {
      if (window.supabase) return ok();
      var s = document.createElement('script'); s.src = SB_JS; s.onload = ok; s.onerror = falha; document.head.appendChild(s);
    }).then(function () { cliente = window.supabase.createClient(C.supabaseUrl, C.supabaseAnonKey); return cliente; });
  }
  function erro(t) { $('dlg-erro').textContent = t; $('dlg-erro').hidden = !t; }

  document.querySelectorAll('.js-login').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      erro(''); dlg.showModal(); $('dlg-user').focus();
      carregar().then(function (sb) {          // já logado: vai direto
        return sb.auth.getSession().then(function (r) { if (r.data.session) location.href = 'area-restrita/'; });
      }).catch(function () {});
    });
  });
  $('dlg-x').addEventListener('click', function () { dlg.close(); });
  dlg.addEventListener('click', function (ev) { if (ev.target === dlg) dlg.close(); });   // clique fora fecha

  $('dlg-form').addEventListener('submit', function (ev) {
    ev.preventDefault(); erro('');
    var u = $('dlg-user').value.trim().toLowerCase();
    if (u.indexOf('@') < 0) u += '@ambientalcosta.netlify.app';
    $('dlg-ok').disabled = true; $('dlg-ok').textContent = 'Entrando…';
    carregar().then(function (sb) {
      return sb.auth.signInWithPassword({ email: u, password: $('dlg-senha').value });
    }).then(function (r) {
      if (r.error) throw r.error;
      location.href = 'area-restrita/';
    }).catch(function (e) {
      erro(e && e.status === 400 ? 'Usuário ou senha incorretos.' : 'Não foi possível entrar agora. Tente de novo.');
      $('dlg-ok').disabled = false; $('dlg-ok').textContent = 'Entrar';
    });
  });
})();
