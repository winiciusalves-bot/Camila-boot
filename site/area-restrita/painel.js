(function () {
  'use strict';
  var C = window.SITE_CONFIG || {};
  var $ = function (id) { return document.getElementById(id); };
  var ST = { novo: 'Novo', contatado: 'Contatado', respondeu: 'Respondeu', reuniao: 'Reunião marcada', cliente: 'Cliente', sem_interesse: 'Sem interesse', nao_contatar: 'Não contatar' };
  var sb = null, modo = null, usuario = '';
  var D = { empresas: [], autos: [], contatos: [], embargos: [], ocorrencias: [] }, porCnpj = {}, aba = 'fila';

  var TIPO_CURTO = { 'AUTO DE INFRACAO': 'auto de infração', 'TERMO DE EMBARGO': 'termo de embargo', 'NOTIFICACAO': 'notificação', 'TERMO DE SUSPENSAO': 'termo de suspensão',
    'TERMO DE DEMOLICAO': 'termo de demolição', 'TERMO DE APREENSAO': 'termo de apreensão', 'ACIDENTE AMBIENTAL (SIEMA)': 'registro de acidente ambiental', 'PENALIDADE INEA': 'penalidade do INEA', 'MENCAO NO DOU': 'menção no Diário Oficial' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function br(d) { d = String(d || '').slice(0, 10); var p = d.split('-'); return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : d; }
  function brDH(t) { var d = new Date(t); return isNaN(d) ? '' : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }); }
  function rs(v) { return v == null ? 'não informado' : 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2 }); }
  function semAcento(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  // CPF: mascarar qualquer sequência de 11 dígitos com DV de CPF válido (defesa extra; os dados já vêm mascarados).
  function cpfOk(c) { if (/^(\d)\1+$/.test(c)) return false; for (var n = 9; n <= 10; n++) { var s = 0; for (var i = 0; i < n; i++) s += +c[i] * (n + 1 - i); if ((s * 10) % 11 % 10 !== +c[n]) return false; } return true; }
  function masc(t) { return String(t || '').replace(/(^|[^\d./-])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?![\d./-])/g, function (m, a, b, c, d, e) { return cpfOk(b + c + d + e) ? a + '[CPF omitido]' : m; }); }
  function telefones(t) { return String(t || '').split('/').map(function (x) { return x.replace(/\D/g, ''); }).filter(Boolean); }
  function fmtTel(n) { return n.length === 11 ? '(' + n.slice(0, 2) + ') ' + n.slice(2, 7) + '-' + n.slice(7) : n.length === 10 ? '(' + n.slice(0, 2) + ') ' + n.slice(2, 6) + '-' + n.slice(6) : n; }
  function celular(n) { return n.length === 11 && n[2] === '9'; }

  // ---------- Inicialização ----------
  function mostrar(id) { ['tela-login', 'tela-sem-config', 'tela-painel'].forEach(function (t) { $(t).hidden = t !== id; }); }

  if (C.supabaseUrl && C.supabaseAnonKey && window.supabase) {
    modo = 'supabase';
    sb = window.supabase.createClient(C.supabaseUrl, C.supabaseAnonKey);
    sb.auth.getSession().then(function (r) { r.data.session ? entrar(r.data.session) : mostrar('tela-login'); });
  } else if (window.DADOS_LOCAIS) {
    modo = 'local';
    $('faixa-previa').hidden = false;
    D.empresas = DADOS_LOCAIS.empresas; D.autos = DADOS_LOCAIS.autos; D.embargos = DADOS_LOCAIS.embargos || []; D.ocorrencias = DADOS_LOCAIS.ocorrencias || [];
    try { D.contatos = JSON.parse(localStorage.getItem('ac_contatos') || '[]'); } catch (e) { D.contatos = []; }
    usuario = 'prévia local'; montar();
  } else {
    mostrar('tela-sem-config');
  }

  $('form-login').addEventListener('submit', function (ev) {
    ev.preventDefault();
    $('l-erro').hidden = true;
    var u = $('l-email').value.trim().toLowerCase();
    // Login por nome de usuário: "ccosta" vira ccosta@ambientalcosta.netlify.app (e-mail interno, nunca recebe mensagem)
    if (u.indexOf('@') < 0) u = u + '@ambientalcosta.netlify.app';
    sb.auth.signInWithPassword({ email: u, password: $('l-senha').value }).then(function (r) {
      if (r.error) { $('l-erro').textContent = 'Usuário ou senha incorretos.'; $('l-erro').hidden = false; return; }
      entrar(r.data.session);
    });
  });
  $('sair').addEventListener('click', function () { if (sb) sb.auth.signOut().then(function () { location.reload(); }); });

  // O Supabase devolve no máximo 1000 linhas por pedido: busca em páginas.
  function todos(tab, ordem, asc) {
    var out = [], passo = 1000;
    function pag(i) {
      var q = sb.from(tab).select('*'); if (ordem) q = q.order(ordem, { ascending: !!asc });
      return q.range(i, i + passo - 1).then(function (r) {
        if (r.error) return { error: r.error };
        out = out.concat(r.data); return r.data.length < passo ? { data: out } : pag(i + passo);
      });
    }
    return pag(0);
  }

  function entrar(sessao) {
    usuario = sessao.user.email;
    Promise.all([
      todos('empresas'),
      todos('autos', 'data_auto'),
      todos('contatos', 'criado_em', true),
      todos('embargos'),
      todos('ocorrencias', 'data_documento')
    ]).then(function (r) {
      if (r[3].error) r[3] = { data: [] };   // tabelas opcionais
      if (r[4].error) r[4] = { data: [] };
      var err = r.find(function (x) { return x.error; });
      if (err) { alert('Erro ao carregar os dados: ' + err.error.message); return; }
      if (!r[0].data.length) { $('tela-login').hidden = true; $('tela-sem-config').hidden = false; $('tela-sem-config').innerHTML = '<h1 class="login-tit">Sem acesso aos dados</h1><p>Seu login funcionou, mas este e-mail não está na lista de usuários autorizados (tabela usuarios_autorizados).</p>'; $('usuario').hidden = false; $('usuario-email').textContent = usuario; return; }
      D.empresas = r[0].data; D.autos = r[1].data; D.contatos = r[2].data; D.embargos = r[3].data || []; D.ocorrencias = r[4].data || []; montar();
    });
  }

  function indexar() {
    porCnpj = {};
    D.empresas.forEach(function (e) { porCnpj[e.cnpj] = { e: e, autos: [], contatos: [], embargos: [], occ: [] }; });
    if (!D.ocorrencias.length) D.ocorrencias = derivarOcorrencias();
    D.ocorrencias.forEach(function (o) { if (porCnpj[o.cnpj]) porCnpj[o.cnpj].occ.push(o); });
    (D.embargos || []).forEach(function (b) { if (porCnpj[b.cnpj]) porCnpj[b.cnpj].embargos.push(b); });
    D.autos.forEach(function (a) { if (porCnpj[a.cnpj]) porCnpj[a.cnpj].autos.push(a); });
    D.contatos.forEach(function (c) { if (porCnpj[c.cnpj]) porCnpj[c.cnpj].contatos.push(c); });
    Object.keys(porCnpj).forEach(function (k) {
      var x = porCnpj[k];
      x.autos.sort(function (a, b) { return a.data_auto < b.data_auto ? 1 : -1; });
      x.occ.sort(function (a, b) { return String(a.data_documento || '') < String(b.data_documento || '') ? 1 : -1; });
      x.validos = x.occ.filter(function (o) { return o.nivel !== 'INDICIO' && !invalido(o); });
      x.doc = x.validos[0] || x.occ[0] || null;
      x.ultimo = x.doc ? x.doc.data_documento : (x.autos[0] ? x.autos[0].data_auto : '');
      x.pri = (x.e.prioridade || '').charAt(0);
      x.status = x.contatos.length ? x.contatos[x.contatos.length - 1].status : 'novo';
      var lim = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
      x.novo = x.autos.some(function (a) { return a.primeira_coleta && a.primeira_coleta >= lim; });
      x.muns = Array.from(new Set(x.autos.map(function (a) { return a.municipio; }).concat(x.occ.map(function (o) { return o.municipio; })).filter(Boolean)));
      x.tels = telefones(x.e.telefone);
      x.texto = semAcento([x.e.razao_social, x.e.nome_fantasia, x.e.cnpj, x.e.cnpj.replace(/\D/g, '')].concat(x.autos.map(function (a) { return a.n_auto + ' ' + a.nome_no_auto; })).concat(x.occ.map(function (o) { return o.numero + ' ' + o.processo; })).join(' '));
    });
  }

  function invalido(o) { return /CANCEL|EXCLU|DESEMBARG/.test(semAcento(o.situacao).toUpperCase()); }
  // Sem a tabela ocorrencias (prévia local ou SQL 04 ainda não rodado): monta a partir de autos e embargos.
  function derivarOcorrencias() {
    var L = 'https://dadosabertos.ibama.gov.br/dataset/';
    return D.autos.map(function (a) {
      return { chave: 'IBAMA-AUTO|' + a.n_auto, orgao: 'IBAMA', fonte: 'IBAMA Dados Abertos', tipo_documento: 'AUTO DE INFRACAO', numero: a.n_auto, processo: a.processo || '',
        data_documento: a.data_auto, data_ciencia: a.data_ciencia, prazo_defesa_fim_estimado: a.prazo_defesa_estimado, situacao: a.cancelado ? 'CANCELADO/EXCLUIDO' : 'VALIDO',
        cnpj: a.cnpj, nome: a.nome_no_auto, municipio: a.municipio, valor_indicado_rs_nao_e_dano: a.valor_auto, assunto: a.tipo_infracao, descricao: a.descricao, nivel: 'FATO', link_fonte: L + 'fiscalizacao-auto-de-infracao' };
    }).concat((D.embargos || []).map(function (b) {
      return { chave: 'IBAMA-EMB|' + b.num_tad, orgao: 'IBAMA', fonte: 'IBAMA Dados Abertos', tipo_documento: 'TERMO DE EMBARGO', numero: b.num_tad, processo: '', data_documento: b.data_embargo,
        situacao: b.status, cnpj: b.cnpj, nome: '', municipio: b.municipio, assunto: b.tipo_area, descricao: '', nivel: 'FATO', link_fonte: L + 'fiscalizacao-termo-de-embargo' };
    }));
  }
  function tipoCurto(t) { return TIPO_CURTO[t] || String(t || 'documento').toLowerCase(); }
  function fonteCurta(o) { return o.orgao === 'INEA' ? 'do INEA' : /DOU|DOM/.test(String(o.chave || '').split('|')[0]) ? 'do Diário Oficial' : 'do IBAMA'; }

  function trocarAba(n) {
    if (['fila', 'empresas', 'registro'].indexOf(n) < 0) n = 'fila';
    aba = n;
    document.querySelectorAll('.aba').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-aba') === n ? 'true' : 'false'); });
    ['fila', 'empresas', 'registro'].forEach(function (k) { $('aba-' + k).hidden = k !== n; });
    try { localStorage.setItem('ac_aba', n); } catch (e) {}
  }

  function montar() {
    indexar();
    mostrar('tela-painel');
    $('usuario').hidden = false; $('usuario-email').textContent = usuario;
    var coleta = D.autos.length ? (D.autos[0].data_coleta || (window.DADOS_LOCAIS || {}).coleta) : '';
    $('p-fonte').innerHTML = 'Fonte: <a href="https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao" target="_blank" rel="noopener">IBAMA Dados Abertos</a> (autos) e base pública do CNPJ (cadastro). Coleta: ' + esc(br(coleta)) + '. Só pessoas jurídicas; CPF sempre mascarado.';
    var muns = Array.from(new Set(D.autos.map(function (a) { return a.municipio; }).concat(D.ocorrencias.map(function (o) { return o.municipio; })).filter(Boolean))).sort();
    var opts = function (l) { return '<option value="">Todos</option>' + l.map(function (m) { return '<option>' + esc(m) + '</option>'; }).join(''); };
    $('p-mun').innerHTML = opts(muns); $('f-mun').innerHTML = opts(muns);
    $('r-tipo').innerHTML = opts(Array.from(new Set(D.ocorrencias.map(function (o) { return o.tipo_documento; }))).sort());
    $('r-org').innerHTML = opts(Array.from(new Set(D.ocorrencias.map(function (o) { return o.orgao; }))).sort());
    $('p-fonte').innerHTML = 'Fontes: <a href="https://dadosabertos.ibama.gov.br/" target="_blank" rel="noopener">IBAMA Dados Abertos</a>' + (D.ocorrencias.some(function (o) { return o.orgao !== 'IBAMA'; }) ? ', INEA e diários oficiais (base do Radar-Ambiental)' : '') + ' e base pública do CNPJ. Última coleta: ' + esc(br(coleta)) + '. Só pessoas jurídicas; CPF sempre mascarado.';
    document.querySelectorAll('.aba').forEach(function (b) { b.addEventListener('click', function () { trocarAba(b.getAttribute('data-aba')); }); });
    var salva = 'fila'; try { salva = localStorage.getItem('ac_aba') || 'fila'; } catch (e) {}
    trocarAba(salva);
    ['f-pri', 'f-mun', 'f-novos', 'f-tel', 'r-q', 'r-tipo', 'r-org', 'r-niv', 'r-val'].forEach(function (id) { $(id).addEventListener('input', render); });
    $('p-st').innerHTML = '<option value="">Todos</option>' + Object.keys(ST).map(function (k) { return '<option value="' + k + '">' + ST[k] + '</option>'; }).join('');
    $('p-ord').value = D.empresas.some(function (e) { return e.pontos != null; }) ? 'pontos' : 'recente';
    if (!D.empresas.some(function (e) { return e.prioridade; })) $('f-pri').value = '';   // base ainda sem pontuação
    ['p-q', 'p-mun', 'p-st', 'p-ord', 'p-ativas', 'p-tel', 'p-pri'].forEach(function (id) { $(id).addEventListener('input', render); });
    render();
  }

  function selos(e) {
    var s = '';
    if (e.prioridade) s += '<span class="selo pri pri-' + esc(e.prioridade.charAt(0)) + '" title="' + esc(e.motivos || '') + '">Prioridade ' + esc(e.prioridade) + (e.pontos != null ? ' · ' + e.pontos + ' pts' : '') + '</span>';
    if (e.embargos_vigentes) s += '<span class="selo selo-verm">' + e.embargos_vigentes + ' embargo(s) vigente(s)</span>';
    if (e.situacao_receita && e.situacao_receita !== 'ATIVA') s += '<span class="selo selo-verm">' + esc(e.situacao_receita) + ' na Receita</span>';
    if (e.nome_divergente) s += '<span class="selo selo-amar">Nome no auto ≠ razão social</span>';
    if (e.individual) s += '<span class="selo">MEI / empresário individual</span>';
    return s;
  }

  function render() {
    var q = semAcento($('p-q').value.trim()), mun = $('p-mun').value, st = $('p-st').value, ord = $('p-ord').value;
    var lista = Object.keys(porCnpj).map(function (k) { return porCnpj[k]; }).filter(function (x) {
      if (q && x.texto.indexOf(q) < 0) return false;
      if (mun && x.muns.indexOf(mun) < 0) return false;
      if (st && x.status !== st) return false;
      var pf = $('p-pri').value;
      if (pf && x.pri !== pf) return false;
      if ($('p-ativas').checked && x.e.situacao_receita !== 'ATIVA') return false;
      if ($('p-tel').checked && !x.tels.length) return false;
      return true;
    });
    lista.sort(function (a, b) {
      if (ord === 'qtd') return b.autos.length - a.autos.length;
      if (ord === 'pontos') return (b.e.pontos || 0) - (a.e.pontos || 0);
      if (ord === 'nome') return a.e.razao_social.localeCompare(b.e.razao_social);
      return a.ultimo < b.ultimo ? 1 : -1;
    });
    var todos = Object.keys(porCnpj).map(function (k) { return porCnpj[k]; });
    var cont = function (f) { return todos.filter(f).length; };
    $('p-kpis').innerHTML = [
      ['Empresas', todos.length], ['Com telefone', cont(function (x) { return x.tels.length; })],
      ['Já contatadas', cont(function (x) { return x.status !== 'novo' && x.status !== 'nao_contatar'; })],
      ['Clientes', cont(function (x) { return x.status === 'cliente'; })], ['Não contatar', cont(function (x) { return x.status === 'nao_contatar'; })]
    ].map(function (k) { return '<div><span class="kpi">' + k[1] + '</span><span class="kpi-l">' + k[0] + '</span></div>'; }).join('');
    $('p-info').textContent = lista.length + ' empresa(s)';
    $('p-linhas').innerHTML = lista.map(function (x) {
      return '<tr><td>' + (x.novo ? '<span class="selo selo-novo">Auto novo (7 dias)</span> ' : '') + '<strong>' + esc(x.e.razao_social) + '</strong><br><small>' + esc(x.e.cnpj) + '</small>' + (selos(x.e) ? '<div class="selos-l">' + selos(x.e) + '</div>' : '') + '</td>' +
        '<td data-l="Autos">' + x.autos.length + '<br><small>último ' + esc(br(x.ultimo)) + '</small></td>' +
        '<td data-l="Municípios"><small>' + esc(x.muns.join(', ')) + '</small></td>' +
        '<td data-l="Telefone"><small>' + (x.tels.length ? esc(x.tels.map(fmtTel).join(' / ')) : '—') + '</small></td>' +
        '<td data-l="Status"><span class="st st-' + x.status + '">' + ST[x.status] + '</span></td>' +
        '<td class="td-acao"><button class="btn btn-linha btn-sm" data-abrir="' + esc(x.e.cnpj) + '" type="button">Abrir</button></td></tr>';
    }).join('') || '<tr><td colspan="6">Nenhuma empresa com esses filtros.</td></tr>';
    renderFila(todos); renderRegistro();
  }

  // ---------- Aba Fila de prospecção ----------
  function renderFila(todos) {
    var pf = $('f-pri').value, mun = $('f-mun').value;
    var lista = todos.filter(function (x) {
      if (x.pri === 'X' || (!x.pri && x.e.situacao_receita !== 'ATIVA')) return false;
      if (x.status === 'nao_contatar' || x.status === 'cliente' || x.status === 'sem_interesse') return false;
      if (pf === 'AB' ? !(x.pri === 'A' || x.pri === 'B') : (pf && x.pri !== pf)) return false;
      if (mun && x.muns.indexOf(mun) < 0) return false;
      if ($('f-novos').checked && x.status !== 'novo') return false;
      if ($('f-tel').checked && !x.tels.length) return false;
      return true;
    }).sort(function (a, b) { return (b.e.pontos || 0) - (a.e.pontos || 0) || (a.ultimo < b.ultimo ? 1 : -1); });
    $('f-info').textContent = lista.length + ' empresa(s) na fila, da maior para a menor pontuação. A pontuação indica urgência de contato, não culpa nem dano.';
    $('f-cards').innerHTML = lista.slice(0, 300).map(function (x) {
      var e = x.e, d = x.doc, cel = x.tels.filter(celular)[0];
      var mot = String(e.motivos || '').split('; ').slice(0, 3).join(' · ');
      return '<article class="card-f"><div class="selos-l">' + selos(e) + '</div>' +
        '<h3>' + esc(e.razao_social) + '</h3>' +
        '<div class="cf-meta">' + esc(e.cnpj) + ' · ' + esc(x.muns.slice(0, 2).join(', ')) + (e.porte ? ' · ' + esc(e.porte) : '') + '</div>' +
        (d ? '<div class="cf-meta">Último: <strong>' + esc(tipoCurto(d.tipo_documento)) + '</strong> ' + esc(fonteCurta(d)) + ' em ' + esc(br(d.data_documento)) + ' · ' + x.validos.length + ' documento(s) válido(s)</div>' : '') +
        (e.prazo_defesa_ate ? '<div class="cf-meta">Prazo de defesa estimado até <strong>' + esc(br(e.prazo_defesa_ate)) + '</strong></div>' : '') +
        (mot ? '<div class="cf-mot">' + esc(mot) + '</div>' : '') +
        '<div class="cf-meta">' + (x.tels.length ? esc(x.tels.map(fmtTel).join(' / ')) : 'Sem telefone no cadastro') + ' · <span class="st st-' + x.status + '">' + ST[x.status] + '</span></div>' +
        '<div class="cf-acoes">' + (cel ? '<a class="btn btn-wa btn-sm" target="_blank" rel="noopener" href="https://wa.me/55' + cel + '?text=' + encodeURIComponent(mensagemPadrao(x)) + '">WhatsApp</a>' : '') +
        '<button class="btn btn-linha btn-sm" data-abrir="' + esc(e.cnpj) + '" type="button">Abrir e registrar</button></div></article>';
    }).join('') || '<p>Ninguém na fila com esses filtros.</p>';
  }

  // ---------- Aba Registro de documentos ----------
  function renderRegistro() {
    var q = semAcento($('r-q').value.trim()), tp = $('r-tipo').value, og = $('r-org').value, nv = $('r-niv').value, so = $('r-val').checked;
    var l = D.ocorrencias.filter(function (o) {
      if (tp && o.tipo_documento !== tp) return false;
      if (og && o.orgao !== og) return false;
      if (nv && (o.nivel || 'FATO') !== nv) return false;
      if (so && invalido(o)) return false;
      if (q) { var emp = (porCnpj[o.cnpj] || {}).e || {}; if (semAcento([o.nome, emp.razao_social, o.cnpj, String(o.cnpj || '').replace(/\D/g, ''), o.numero, o.processo].join(' ')).indexOf(q) < 0) return false; }
      return true;
    }).sort(function (a, b) { return String(a.data_documento || '') < String(b.data_documento || '') ? 1 : -1; });
    $('r-info').textContent = l.length + ' documento(s)';
    $('r-linhas').innerHTML = l.slice(0, 500).map(function (o) {
      var emp = (porCnpj[o.cnpj] || {}).e;
      return '<tr><td data-l="Data">' + esc(br(o.data_documento)) + '</td>' +
        '<td data-l="Documento"><span class="niv niv-' + esc(o.nivel || 'FATO') + '">' + esc(o.nivel || 'FATO') + '</span> ' + esc(tipoCurto(o.tipo_documento)) + '<br><small>' + esc(o.orgao || '') + (o.numero ? ' · nº ' + esc(o.numero) : '') + (o.valor_indicado_rs_nao_e_dano ? ' · valor indicado ' + esc(rs(o.valor_indicado_rs_nao_e_dano)) + ' (não é dano)' : '') + '</small></td>' +
        '<td data-l="Empresa">' + esc(emp ? emp.razao_social : masc(o.nome)) + '<br><small>' + esc(o.cnpj || '') + '</small></td>' +
        '<td data-l="Município"><small>' + esc(o.municipio || '') + '</small></td>' +
        '<td data-l="Situação"><small>' + esc(o.situacao || '') + '</small></td>' +
        '<td class="td-acao">' + (emp ? '<button class="btn btn-linha btn-sm" data-abrir="' + esc(o.cnpj) + '" type="button">Empresa</button> ' : '') + (/^https:\/\//.test(o.link_fonte || '') ? '<a class="btn btn-linha btn-sm" href="' + esc(o.link_fonte) + '" target="_blank" rel="noopener">Fonte</a>' : '') + '</td></tr>';
    }).join('') || '<tr><td colspan="6">Nenhum documento com esses filtros.</td></tr>';
    $('r-mais').textContent = l.length > 500 ? 'Mostrando os 500 mais recentes. Use a busca para achar os demais.' : '';
  }

  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-abrir]'); if (b) abrir(b.getAttribute('data-abrir'));
  });
  function fechar() { $('gaveta').hidden = true; $('gaveta-fundo').hidden = true; }
  $('gaveta-x').addEventListener('click', fechar); $('gaveta-fundo').addEventListener('click', fechar);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') fechar(); });

  function mensagemPadrao(x) {
    var d = x.validos[0], mes = d ? String(d.data_documento || '').slice(0, 7).split('-').reverse().join('/') : '';
    return 'Olá! Aqui é da ' + (C.nomeEmpresa || 'Ambiental Costa') + ', empresa de engenharia e consultoria ambiental registrada no CREA-RJ. ' +
      (d ? 'Vi nos dados públicos ' + fonteCurta(d) + ' um(a) ' + tipoCurto(d.tipo_documento) + (d.numero ? ' nº ' + d.numero : '') + ' em nome da ' + x.e.razao_social + (d.municipio ? ', em ' + d.municipio : '') + ' (' + mes + '). ' : '') +
      'Ajudamos empresas nessa situação com a parte técnica: análise do caso e dos prazos, laudos, PRAD e licenciamento. ' +
      'Se preferir não receber mensagens, é só responder SAIR que não voltaremos a escrever.';
  }

  function abrir(cnpj) {
    var x = porCnpj[cnpj], e = x.e, bloq = x.status === 'nao_contatar';
    var avisos = '';
    if (e.situacao_receita !== 'ATIVA') avisos += '<p class="aviso-l verm">Empresa ' + esc(e.situacao_receita) + ' na Receita. Não prospectar sem conferir quem responde hoje pela atividade.</p>';
    if (e.nome_divergente) avisos += '<p class="aviso-l amar">O nome escrito no auto difere da razão social atual. Pode ser troca de nome ou CNPJ digitado errado no auto. Confira antes de contatar (HIPÓTESE, não FATO).</p>';
    if (e.individual) avisos += '<p class="aviso-l">MEI / empresário individual: o contato é da própria pessoa. Use só para tratar do auto, identifique a fonte (dados abertos do IBAMA e cadastro do CNPJ) e atenda na hora a quem pedir para não ser contatado (LGPD).</p>';
    if (e.motivos) avisos += '<p class="aviso-l"><strong>Por que esta prioridade:</strong> ' + esc(e.motivos) + '. A pontuação indica urgência de contato; não indica culpa nem dano.</p>';
    if (e.prazo_defesa_ate) avisos += '<p class="aviso-l amar">Prazo de defesa <strong>estimado</strong> até ' + esc(br(e.prazo_defesa_ate)) + ' (ciência + 20 dias, Decreto 6.514/2008, art. 113). Confirme na notificação.</p>';
    if (bloq) avisos += '<p class="aviso-l verm">Marcada como <strong>Não contatar</strong>. Não envie mensagens.</p>';

    var contato = '';
    if (!bloq && x.tels.length) {
      contato = '<h3>Contato (cadastro da Receita)</h3><ul class="tels">' + x.tels.map(function (t) {
        return '<li><span>' + esc(fmtTel(t)) + '</span> <a class="btn btn-linha btn-sm" href="tel:+55' + t + '">Ligar</a>' +
          (celular(t) ? ' <a class="btn btn-wa btn-sm js-wa-g" data-tel="55' + t + '" href="#">WhatsApp</a>' : ' <small>fixo, sem WhatsApp</small>') + '</li>';
      }).join('') + '</ul>' + (e.email ? '<p><a href="mailto:' + esc(e.email) + '">' + esc(e.email) + '</a></p>' : '') +
        '<label class="campo"><span>Mensagem sugerida (edite antes de enviar)</span><textarea id="g-msg" rows="5">' + esc(mensagemPadrao(x)) + '</textarea></label>';
    }

    var autos = x.autos.map(function (a) {
      return '<li class="auto' + (a.cancelado ? ' auto-canc' : '') + '"><div class="auto-cab"><strong>Auto ' + esc(a.n_auto) + '</strong><span>' + esc(br(a.data_auto)) + ' · ' + esc(a.municipio) + '</span></div>' +
        '<div class="auto-meta">' + esc(a.tipo_infracao) + (a.gravidade ? ' · gravidade ' + esc(a.gravidade.toLowerCase()) : '') + ' · valor indicado no auto: ' + esc(rs(a.valor_auto)) + (a.cancelado ? ' · <strong>CANCELADO</strong>' : '') + (a.processo ? ' · processo ' + esc(a.processo) : '') + (a.prazo_defesa_estimado ? ' · prazo estimado até ' + esc(br(a.prazo_defesa_estimado)) : '') + '</div>' +
        (a.nome_no_auto && e.nome_divergente ? '<div class="auto-meta">Nome no auto: ' + esc(masc(a.nome_no_auto)) + '</div>' : '') +
        '<p>' + esc(masc(a.descricao)) + '</p></li>';
    }).join('');

    var hist = x.contatos.slice().reverse().map(function (c) {
      return '<li><span class="st st-' + esc(c.status) + '">' + esc(ST[c.status] || c.status) + '</span> <small>' + esc(brDH(c.criado_em)) + ' · ' + esc(c.autor_email || '') + (c.canal ? ' · ' + esc(c.canal) : '') + '</small>' + (c.nota ? '<p>' + esc(c.nota) + '</p>' : '') + '</li>';
    }).join('') || '<li><small>Nenhum contato registrado.</small></li>';

    $('gaveta-corpo').innerHTML =
      '<h2 id="g-tit">' + esc(e.razao_social) + '</h2>' +
      '<p class="g-sub">' + esc(e.cnpj) + (e.nome_fantasia ? ' · ' + esc(e.nome_fantasia) : '') + '<br>' + esc(e.atividade || '') + '<br>Sede: ' + esc(e.municipio_sede || '') + ' · ' + esc(e.situacao_receita || '') + '</p>' +
      (e.socios ? '<p class="g-sub"><strong>Sócios (QSA):</strong> ' + esc(masc(e.socios)) + '</p>' : '') +
      avisos + contato +
      '<h3>Registrar contato</h3><form class="g-form" id="g-form"><div class="duas">' +
      '<label class="campo"><span>Status</span><select id="g-st">' + Object.keys(ST).map(function (k) { return '<option value="' + k + '"' + (k === x.status ? ' selected' : '') + '>' + ST[k] + '</option>'; }).join('') + '</select></label>' +
      '<label class="campo"><span>Canal</span><select id="g-canal"><option>WhatsApp</option><option>Telefone</option><option>E-mail</option><option>Presencial</option><option>Outro</option></select></label></div>' +
      '<label class="campo"><span>Anotação</span><textarea id="g-nota" rows="2" placeholder="Ex.: falei com o setor ambiental, pediram proposta"></textarea></label>' +
      '<button class="btn btn-wa btn-sm" type="submit">Salvar registro</button> <small class="erro" id="g-erro" hidden></small></form>' +
      '<h3>Histórico</h3><ul class="hist">' + hist + '</ul>' +
      (x.embargos.length ? '<h3>Termos de embargo (' + x.embargos.length + ')</h3><ul class="autos">' + x.embargos.map(function (b) {
        return '<li class="auto' + (b.status === 'CANCELADO' ? ' auto-canc' : '') + '"><div class="auto-cab"><strong>TAD ' + esc(b.num_tad) + '</strong><span>' + esc(br(b.data_embargo)) + ' · ' + esc(b.municipio) + '</span></div><div class="auto-meta">' + esc(b.status) + (b.data_desembargo ? ' em ' + esc(br(b.data_desembargo)) : '') + (b.tipo_area ? ' · ' + esc(b.tipo_area) : '') + '</div></li>';
      }).join('') + '</ul>' : '') +
      (function () {
        var outros = x.occ.filter(function (o) { return !/^IBAMA-(AUTO|EMB)\|/.test(o.chave || ''); });
        return outros.length ? '<h3>Outros documentos (' + outros.length + ')</h3><p class="nota">INDÍCIO = menção em diário oficial: leia o ato antes de qualquer conclusão.</p><ul class="autos">' + outros.map(function (o) {
          return '<li class="auto' + (invalido(o) ? ' auto-canc' : '') + '"><div class="auto-cab"><strong><span class="niv niv-' + esc(o.nivel || 'FATO') + '">' + esc(o.nivel || 'FATO') + '</span> ' + esc(tipoCurto(o.tipo_documento)) + (o.numero ? ' ' + esc(o.numero) : '') + '</strong><span>' + esc(br(o.data_documento)) + ' · ' + esc(o.orgao || '') + '</span></div>' +
            '<div class="auto-meta">' + esc(o.situacao || '') + (o.processo ? ' · processo ' + esc(o.processo) : '') + (o.assunto ? ' · ' + esc(o.assunto) : '') + (/^https:\/\//.test(o.link_fonte || '') ? ' · <a href="' + esc(o.link_fonte) + '" target="_blank" rel="noopener">fonte</a>' : '') + '</div>' +
            (o.descricao ? '<p>' + esc(masc(o.descricao)) + '</p>' : '') + '</li>';
        }).join('') + '</ul>' : '';
      })() +
      '<h3>Autos (' + x.autos.length + ')</h3><p class="nota">Auto de infração não é condenação. Valor indicado não é dano.</p><ul class="autos">' + autos + '</ul>' +
      '<p class="nota">Fonte: <a href="https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao" target="_blank" rel="noopener">IBAMA Dados Abertos</a>. Confira o auto na <a href="https://servicos.ibama.gov.br/ctf/publico/areasembargadas/ConsultaPublicaAreasEmbargadas.php" target="_blank" rel="noopener">consulta pública do IBAMA</a>.</p>';

    $('gaveta').hidden = false; $('gaveta-fundo').hidden = false; $('gaveta').scrollTop = 0;

    $('gaveta-corpo').querySelectorAll('.js-wa-g').forEach(function (a) {
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        window.open('https://wa.me/' + a.getAttribute('data-tel') + '?text=' + encodeURIComponent($('g-msg').value), '_blank', 'noopener');
      });
    });
    $('g-form').addEventListener('submit', function (ev) {
      ev.preventDefault();
      var reg = { cnpj: cnpj, status: $('g-st').value, canal: $('g-canal').value, nota: $('g-nota').value.trim() };
      salvar(reg).then(function (ok) {
        if (!ok) return;
        indexar(); render(); abrir(cnpj);
      });
    });
  }

  function salvar(reg) {
    if (modo === 'local') {
      reg.criado_em = new Date().toISOString(); reg.autor_email = 'prévia local';
      D.contatos.push(reg);
      try { localStorage.setItem('ac_contatos', JSON.stringify(D.contatos)); } catch (e) {}
      return Promise.resolve(true);
    }
    return sb.from('contatos').insert(reg).select().then(function (r) {
      if (r.error) { $('g-erro').textContent = 'Não foi possível salvar: ' + r.error.message; $('g-erro').hidden = false; return false; }
      D.contatos.push(r.data[0]); return true;
    });
  }
})();
