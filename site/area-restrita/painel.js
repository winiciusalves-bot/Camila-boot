(function () {
  'use strict';
  var C = window.SITE_CONFIG || {};
  var $ = function (id) { return document.getElementById(id); };
  var ST = { novo: 'Novo', contatado: 'Contatado', respondeu: 'Respondeu', reuniao: 'Reunião marcada', cliente: 'Cliente', sem_interesse: 'Sem interesse', nao_contatar: 'Não contatar' };
  var sb = null, modo = null, usuario = '';
  var D = { empresas: [], autos: [], contatos: [], embargos: [], ocorrencias: [] }, porCnpj = {}, aba = 'fila';
  var TRI = {}, triOk = true, desfazer = [], DIAS_REPROVADO = 45, confAtual = null, forcar = null, ocupado = false;
  var ABAS = ['conferencia', 'aprovados', 'reprovados', 'empresas', 'registro', 'fila'], grupo = 'acontatar', VOLTAS = [7, 14];   // sem resposta: volta em 7 dias, depois em 14; sem resposta de novo, vai para o lixo

  var TIPO_CURTO = { 'AUTO DE INFRACAO': 'auto de infração', 'TERMO DE EMBARGO': 'termo de embargo', 'NOTIFICACAO': 'notificação', 'TERMO DE SUSPENSAO': 'termo de suspensão',
    'TERMO DE DEMOLICAO': 'termo de demolição', 'TERMO DE APREENSAO': 'termo de apreensão', 'ACIDENTE AMBIENTAL (SIEMA)': 'registro de acidente ambiental', 'PENALIDADE INEA': 'penalidade do INEA', 'MENCAO NO DOU': 'menção no Diário Oficial' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function br(d) { d = String(d || '').slice(0, 10); var p = d.split('-'); return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : d; }
  function brDH(t) { var d = new Date(t); return isNaN(d) ? '' : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }); }
  function rs(v) { return v == null ? 'não informado' : 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2 }); }
  function semAcento(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  // CPF: mascarar qualquer sequência de 11 dígitos com DV de CPF válido (defesa extra; os dados já vêm mascarados).
  function cpfOk(c) { if (/^(\d)\1+$/.test(c)) return false; for (var n = 9; n <= 10; n++) { var s = 0; for (var i = 0; i < n; i++) s += +c[i] * (n + 1 - i); if ((s * 10) % 11 % 10 !== +c[n]) return false; } return true; }
  function masc(t) { return String(t || '').replace(/(^|[^\d./-])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d|[./-]\d)/g, function (m, a, b, c, d, e) { return cpfOk(b + c + d + e) ? a + '[CPF omitido]' : m; }); }
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
    D.empresas = DADOS_LOCAIS.empresas; D.autos = DADOS_LOCAIS.autos; D.embargos = DADOS_LOCAIS.embargos || []; D.ocorrencias = DADOS_LOCAIS.ocorrencias || []; tirarDescartadas();
    try { D.contatos = JSON.parse(localStorage.getItem('ac_contatos') || '[]'); } catch (e) { D.contatos = []; }
    try { TRI = JSON.parse(localStorage.getItem('ac_triagem') || '{}'); } catch (e) { TRI = {}; }
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
      todos('ocorrencias', 'data_documento'),
      todos('triagem')
    ]).then(function (r) {
      if (r[5].error) { triOk = false; r[5] = { data: [] }; }
      TRI = {}; r[5].data.forEach(function (t) { TRI[t.cnpj] = t; });
      if (r[3].error) r[3] = { data: [] };   // tabelas opcionais
      if (r[4].error) r[4] = { data: [] };
      var err = r.find(function (x) { return x.error; });
      if (err) { alert('Erro ao carregar os dados: ' + err.error.message); return; }
      if (!r[0].data.length) { $('tela-login').hidden = true; $('tela-sem-config').hidden = false; $('tela-sem-config').innerHTML = '<h1 class="login-tit">Sem acesso aos dados</h1><p>Seu login funcionou, mas este e-mail não está na lista de usuários autorizados (tabela usuarios_autorizados).</p>'; $('usuario').hidden = false; $('usuario-email').textContent = usuario; return; }
      D.empresas = r[0].data; D.autos = r[1].data; D.contatos = r[2].data; D.embargos = r[3].data || []; D.ocorrencias = r[4].data || []; tirarDescartadas(); montar();
    });
  }

  // Descartadas (prioridade X: CNPJ baixado/suspenso, órgão público, lista de exclusão) nem entram no painel.
  function tirarDescartadas() {
    var fora = {};
    D.empresas.forEach(function (e) {
      if (String(e.prioridade || '').charAt(0) === 'X' || (e.situacao_receita && e.situacao_receita !== 'ATIVA')) fora[e.cnpj] = 1;
    });
    function f(l) { return (l || []).filter(function (o) { return !fora[o.cnpj]; }); }
    D.empresas = f(D.empresas); D.autos = f(D.autos); D.contatos = f(D.contatos); D.embargos = f(D.embargos); D.ocorrencias = f(D.ocorrencias);
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
      x.contatos.sort(function (a, b) { return String(a.criado_em) < String(b.criado_em) ? -1 : 1; });
      x.status = x.contatos.length ? x.contatos[x.contatos.length - 1].status : 'novo';
      x.ultContato = x.contatos.length ? x.contatos[x.contatos.length - 1].criado_em : '';
      // tentativas sem resposta desde o último recomeço (status Novo)
      x.tentativas = 0;
      for (var i = x.contatos.length - 1; i >= 0 && x.contatos[i].status !== 'novo'; i--) if (x.contatos[i].status === 'contatado') x.tentativas++;
      x.lixoEm = null;
      if (x.status === 'contatado' && x.tentativas > VOLTAS.length) x.lixoEm = new Date(new Date(x.ultContato).getTime() + VOLTAS[VOLTAS.length - 1] * 864e5);
      if (x.lixoEm && x.lixoEm > Date.now()) x.lixoEm = null;
      var lim = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
      var t = TRI[x.e.cnpj];
      x.tri = t ? t.decisao : '';
      // auto novo depois da reprovação devolve a empresa à conferência
      if (t && t.decisao === 'reprovado' && x.autos.some(function (a) { return a.primeira_coleta && a.primeira_coleta > String(t.decidido_em).slice(0, 10); })) x.tri = '';
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
    if (ABAS.indexOf(n) < 0 || n === 'fila') n = 'conferencia';
    aba = n; document.body.setAttribute('data-aba', n);
    document.querySelectorAll('.aba').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-aba') === n ? 'true' : 'false'); });
    ABAS.forEach(function (k) { $('aba-' + k).hidden = k !== n; });
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
    var salva = 'conferencia'; try { salva = localStorage.getItem('ac_aba') || 'conferencia'; } catch (e) {}
    trocarAba(salva);
    $('c-pri').addEventListener('input', function () { renderConf(); });
    $('a-per').addEventListener('input', renderAprovados);
    $('c-nao').addEventListener('click', function () { decidir('reprovado'); });
    $('c-sim').addEventListener('click', function () { decidir('aprovado'); });
    $('c-volta').addEventListener('click', voltar);
    $('a-xls').addEventListener('click', baixarPlanilha);
    try { grupo = localStorage.getItem('ac_grupo') || grupo; } catch (e) {}
    document.querySelectorAll('.sub-aba').forEach(function (b) { b.addEventListener('click', function () { grupo = b.getAttribute('data-g'); try { localStorage.setItem('ac_grupo', grupo); } catch (e) {} renderAprovados(); }); });
    ['f-pri', 'f-mun', 'f-novos', 'f-tel', 'r-q', 'r-tipo', 'r-org', 'r-niv', 'r-val'].forEach(function (id) { $(id).addEventListener('input', render); });
    $('p-st').innerHTML = '<option value="">Todos</option>' + Object.keys(ST).map(function (k) { return '<option value="' + k + '">' + ST[k] + '</option>'; }).join('');
    $('p-ord').value = D.empresas.some(function (e) { return e.pontos != null; }) ? 'pontos' : 'recente';
    if (!D.empresas.some(function (e) { return e.prioridade; })) $('f-pri').value = '';   // base ainda sem pontuação
    ['p-q', 'p-mun', 'p-st', 'p-ord', 'p-ativas', 'p-tel', 'p-pri'].forEach(function (id) { $(id).addEventListener('input', render); });
    render();
  }

  function selos(e) {
    var s = '', t = TRI[e.cnpj];
    if (t && t.decisao === 'aprovado') s += '<span class="selo selo-apr">✓ Aprovado na conferência</span>';
    if (t && t.decisao === 'reprovado') s += '<span class="selo selo-verm">✕ Reprovado na conferência</span>';
    if (e.prioridade) s += '<span class="selo pri pri-' + esc(e.prioridade.charAt(0)) + '" title="' + esc(e.motivos || '') + '">Prioridade ' + esc(e.prioridade) + (e.pontos != null ? ' · ' + e.pontos + ' pts' : '') + '</span>';
    if (e.chance_licenciamento) s += '<span class="selo chance chance-' + esc(e.chance_licenciamento.toLowerCase()) + '" title="' + esc(e.chance_motivo || '') + '">Chance de licenciamento: ' + esc(e.chance_licenciamento) + (e.chance_pontos != null ? ' · ' + e.chance_pontos + ' pts' : '') + '</span>';
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
    renderFila(todos); renderRegistro(); renderConf(); renderAprovados(); renderReprovados();
  }

  // ---------- Aba Fila de prospecção ----------
  function renderFila(todos) {
    var pf = $('f-pri').value, mun = $('f-mun').value;
    var lista = todos.filter(function (x) {
      if (x.pri === 'X' || (!x.pri && x.e.situacao_receita !== 'ATIVA')) return false;
      if (x.status === 'nao_contatar' || x.status === 'cliente' || x.status === 'sem_interesse') return false;
      if (x.tri === 'reprovado') return false;
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


  // ---------- Conferência diária (✕ / ✓) ----------
  function hojeISO() { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function diaLocal(t) { var d = new Date(t); return isNaN(d) ? '' : d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function lista() { return Object.keys(porCnpj).map(function (k) { return porCnpj[k]; }); }
  function filaConf() {
    var pf = $('c-pri').value;
    var l = lista().filter(function (x) {
      if (x.tri) return false;
      if (pf === 'X') return x.pri === 'X';
      if (x.pri === 'X') return false;
      return pf === 'AB' ? (x.pri === 'A' || x.pri === 'B') : (!pf || x.pri === pf);
    }).sort(function (a, b) { return (b.e.pontos || 0) - (a.e.pontos || 0) || (a.ultimo < b.ultimo ? 1 : -1); });
    if (forcar && porCnpj[forcar] && !porCnpj[forcar].tri) { l = l.filter(function (x) { return x.e.cnpj !== forcar; }); l.unshift(porCnpj[forcar]); }
    return l;
  }

  function renderConf() {
    var f = filaConf(), feitasHoje = Object.keys(TRI).filter(function (k) { return diaLocal(TRI[k].decidido_em) === hojeISO() && porCnpj[k]; }).length;
    $('n-conf').textContent = f.length ? f.length : '';
    $('c-aviso').hidden = triOk;
    $('c-aviso').textContent = 'A tabela da conferência ainda não existe no banco. As decisões não serão salvas até ela ser criada.';
    $('c-volta').disabled = !desfazer.length;
    if (!f.length) {
      confAtual = null; $('c-barra').hidden = true;
      $('c-info').textContent = feitasHoje ? 'Conferência em dia: ' + feitasHoje + ' decisão(ões) hoje.' : '';
      $('c-pilha').innerHTML = '<div class="conf-vazia"><strong>Nada para conferir com esse filtro.</strong><br>' + (feitasHoje ? 'Os aprovados de hoje estão na aba Aprovados, com a planilha.' : 'Quando a coleta trouxer empresas novas, elas aparecem aqui.') + '</div>';
      return;
    }
    var x = f[0];
    $('c-info').innerHTML = '<strong>' + (feitasHoje + 1) + ' de ' + (feitasHoje + f.length) + '</strong> hoje · faltam ' + f.length;
    if (confAtual === x.e.cnpj && $('c-pilha').querySelector('.conf-card')) return;
    confAtual = x.e.cnpj;
    $('c-pilha').innerHTML = (f[1] ? '<div class="conf-atras" aria-hidden="true"></div>' : '') + '<article class="conf-card" id="c-card"><div class="conf-carimbo conf-c-nao">REPROVAR</div><div class="conf-carimbo conf-c-sim">APROVAR</div><div class="conf-ficha" id="c-ficha"></div></article>';
    abrir(x.e.cnpj, $('c-ficha'));
    $('c-barra').hidden = false;
    arrastar($('c-card'));
  }
  function arrastar(card) {
    var x0 = null, y0 = 0, dx = 0, horiz = null;
    card.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; horiz = null; card.style.transition = 'none'; }, { passive: true });
    card.addEventListener('touchmove', function (e) {
      if (x0 === null) return;
      var mx = e.touches[0].clientX - x0, my = e.touches[0].clientY - y0;
      if (horiz === null && (Math.abs(mx) > 12 || Math.abs(my) > 12)) horiz = Math.abs(mx) > Math.abs(my) * 1.3;
      if (!horiz) return;
      dx = mx; card.style.transform = 'translateX(' + dx + 'px) rotate(' + dx / 30 + 'deg)';
      card.classList.toggle('pende-nao', dx < -60); card.classList.toggle('pende-sim', dx > 60);
    }, { passive: true });
    card.addEventListener('touchend', function () {
      card.style.transition = '';
      if (horiz && Math.abs(dx) > 110) decidir(dx > 0 ? 'aprovado' : 'reprovado');
      else { card.style.transform = ''; card.classList.remove('pende-nao', 'pende-sim'); }
      x0 = null;
    });
  }
  function gravarTri(cnpj, novo) {
    if (modo === 'local' || !triOk) {
      if (novo) TRI[cnpj] = novo; else delete TRI[cnpj];
      if (modo === 'local') try { localStorage.setItem('ac_triagem', JSON.stringify(TRI)); } catch (e) {}
      return Promise.resolve(true);
    }
    var q = novo ? sb.from('triagem').upsert({ cnpj: cnpj, decisao: novo.decisao, decidido_em: novo.decidido_em, autor_email: usuario }).select()
      : sb.from('triagem').delete().eq('cnpj', cnpj);
    return q.then(function (r) {
      if (r.error) { alert('Não foi possível salvar a decisão: ' + r.error.message); return false; }
      if (novo) TRI[cnpj] = (r.data && r.data[0]) || novo; else delete TRI[cnpj];
      return true;
    });
  }

  function decidir(decisao) {
    if (!confAtual || ocupado) return;
    var cnpj = confAtual, card = $('c-card'); ocupado = true;
    var ant = TRI[cnpj] || null;
    if (card) { card.style.transform = 'translateX(' + (decisao === 'aprovado' ? 130 : -130) + '%) rotate(' + (decisao === 'aprovado' ? 12 : -12) + 'deg)'; card.style.opacity = '0'; }
    forcar = null;
    gravarTri(cnpj, { cnpj: cnpj, decisao: decisao, decidido_em: new Date().toISOString(), autor_email: usuario }).then(function (ok) {
      setTimeout(function () {
        ocupado = false;
        if (ok) { desfazer.push({ cnpj: cnpj, ant: ant }); if (desfazer.length > 30) desfazer.shift(); }
        indexar(); confAtual = null; render(); window.scrollTo({ top: $('aba-conferencia').offsetTop - 10 });
      }, 220);
    });
  }
  function voltar() {
    var u = desfazer.pop(); if (!u) return;
    gravarTri(u.cnpj, u.ant).then(function () {
      indexar(); confAtual = null;
      forcar = u.ant ? null : u.cnpj;
      render(); trocarAba('conferencia');
    });
  }
  document.addEventListener('keydown', function (e) {
    if (aba !== 'conferencia' || !$('gaveta').hidden || /INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '')) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); decidir('reprovado'); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); decidir('aprovado'); }
    else if (e.key === 'z' || e.key === 'Z') { e.preventDefault(); voltar(); }
  });

  function aprovados() {
    var per = $('a-per').value, h = hojeISO(), lim = per && per !== 'hoje' ? diaLocal(Date.now() - (+per) * 864e5) : '';
    return lista().filter(function (x) {
      var t = TRI[x.e.cnpj]; if (!t || t.decisao !== 'aprovado') return false;
      var d = diaLocal(t.decidido_em);
      return per === 'hoje' ? d === h : (!lim || d >= lim);
    }).sort(function (a, b) { return TRI[a.e.cnpj].decidido_em < TRI[b.e.cnpj].decidido_em ? 1 : -1; });
  }
  function grupoDe(x) {
    if (x.lixoEm) return 'lixo';
    if (x.status === 'novo') return 'acontatar';
    if (x.status === 'respondeu' || x.status === 'reuniao' || x.status === 'cliente') return 'retorno';
    if (x.status === 'sem_interesse' || x.status === 'nao_contatar') return 'encerrados';
    var dias = (Date.now() - new Date(x.ultContato).getTime()) / 864e5, espera = VOLTAS[Math.min(x.tentativas, VOLTAS.length) - 1] || VOLTAS[0];
    return x.tentativas <= VOLTAS.length && dias >= espera ? 'semretorno' : 'aguardando';
  }
  function canaisUsados(x) {
    return Array.from(new Set(x.contatos.map(function (c) { return c.canal; }).filter(Boolean)));
  }
  function renderAprovados() {
    var apr = lista().filter(function (x) { return x.tri === 'aprovado'; }), g = {};
    ['acontatar', 'aguardando', 'semretorno', 'retorno', 'encerrados', 'lixo'].forEach(function (k) { g[k] = []; });
    apr.forEach(function (x) { g[grupoDe(x)].push(x); });
    Object.keys(g).forEach(function (k) { if ($('g-n-' + k)) $('g-n-' + k).textContent = g[k].length || ''; });
    document.querySelectorAll('.sub-aba').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-g') === grupo ? 'true' : 'false'); });
    $('n-apr').textContent = (g.acontatar.length + g.semretorno.length) || '';
    var l = g[grupo].sort(function (a, b) {
      if (grupo === 'acontatar') return (b.e.pontos || 0) - (a.e.pontos || 0);
      return String(a.ultContato) < String(b.ultContato) ? (grupo === 'semretorno' ? -1 : 1) : (grupo === 'semretorno' ? 1 : -1);
    });
    var TXT = { acontatar: 'aprovada(s) e ainda sem nenhum contato, da maior para a menor pontuação.', aguardando: 'contatada(s), aguardando resposta. Sem resposta, voltam para nova tentativa em ' + VOLTAS[0] + ' dias e depois em ' + VOLTAS[1] + ' dias.',
      semretorno: 'sem resposta: hora da nova tentativa, de preferência por outro canal. Se a 3ª mensagem ficar ' + VOLTAS[1] + ' dias sem resposta, a empresa vai para o lixo.', retorno: 'responderam, têm reunião marcada ou já são clientes.', encerrados: 'sem interesse ou pediram para não ser contatadas.' };
    $('a-info').textContent = l.length + ' empresa(s) ' + TXT[grupo];
    $('a-cards').innerHTML = l.map(function (x) {
      var e = x.e, sc = e.site_contatos || {}, cel = x.tels.filter(celular)[0] || (sc.whatsapp || [])[0], ult = x.contatos[x.contatos.length - 1];
      var em = e.email || (sc.emails || [])[0], bloq = x.status === 'nao_contatar', usados = canaisUsados(x);
      var diasC = ult ? Math.floor((Date.now() - new Date(ult.criado_em).getTime()) / 864e5) : null;
      return '<article class="card-f"><div class="selos-l">' + selos(e).replace(/<span class="selo selo-apr">[^<]*<\/span>/, '') + '</div>' +
        '<h3>' + esc(e.razao_social) + '</h3>' +
        '<div class="cf-meta">' + esc(e.cnpj) + ' · ' + esc(x.muns.slice(0, 2).join(', ')) + ' · ' + x.autos.length + ' auto(s), último ' + esc(br(x.ultimo)) + '</div>' +
        '<div class="cf-meta">' + [x.tels.map(fmtTel).join(' / '), em].filter(Boolean).map(esc).join(' · ') + (e.site ? ' · <a href="' + esc(e.site) + '" target="_blank" rel="noopener">site</a>' : '') + (!x.tels.length && !em ? 'Sem telefone nem e-mail' : '') + '</div>' +
        (ult ? '<div class="cf-mot"><span class="st st-' + esc(x.status) + '">' + esc(ST[x.status]) + '</span> ' + esc(ult.canal || '') + ' em ' + esc(brDH(ult.criado_em)) + (diasC != null ? ' (há ' + diasC + ' dia' + (diasC === 1 ? '' : 's') + ')' : '') + (x.status === 'contatado' ? ' · ' + x.tentativas + 'ª tentativa' : '') + (usados.length ? ' · canais já usados: ' + esc(usados.join(', ')) : '') + (ult.nota ? '<br>' + esc(ult.nota) : '') + '</div>' : '') +
        (bloq ? '' : '<div class="cf-acoes">' +
          (cel ? '<a class="btn btn-wa btn-sm" data-wa="' + esc(e.cnpj) + '" target="_blank" rel="noopener" href="https://wa.me/55' + cel + '?text=' + encodeURIComponent(mensagemPadrao(x)) + '">WhatsApp</a>' : '') +
          (em ? '<a class="btn btn-linha btn-sm" data-mail="' + esc(e.cnpj) + '" href="mailto:' + esc(em) + '?subject=' + encodeURIComponent(assuntoEmail(x)) + '&body=' + encodeURIComponent(mensagemEmail(x)) + '">E-mail</a>' : '') +
          (grupo === 'aguardando' || grupo === 'semretorno' ? '<button class="btn btn-linha btn-sm" data-rapido="' + esc(e.cnpj) + '|respondeu" type="button">Respondeu</button><button class="btn btn-linha btn-sm" data-rapido="' + esc(e.cnpj) + '|sem_interesse" type="button">Sem interesse</button>' : '') +
          '<button class="btn btn-linha btn-sm" data-abrir="' + esc(e.cnpj) + '" type="button">Abrir ficha</button></div>') + '</article>';
    }).join('') || '<p class="conf-vazia">Ninguém neste grupo.</p>';
    var pl = aprovados();
    $('a-xls').disabled = !pl.length;
    $('a-xls-info').textContent = pl.length ? pl.length + ' empresa(s), todos os dados e a fonte de cada um.' : 'Nenhuma aprovada nesse período.';
  }
  // Ao clicar em WhatsApp ou E-mail, pergunta se a mensagem foi enviada e registra o contato.
  var pendente = null;
  document.addEventListener('click', function (ev) {
    var w = ev.target.closest('[data-wa],[data-mail]');
    if (w) { pendente = { cnpj: w.getAttribute('data-wa') || w.getAttribute('data-mail'), canal: w.hasAttribute('data-wa') ? 'WhatsApp' : 'E-mail' }; return; }
    var r = ev.target.closest('[data-rapido]'); if (!r) return;
    var p = r.getAttribute('data-rapido').split('|'), x = porCnpj[p[0]];
    salvar({ cnpj: p[0], status: p[1], canal: (x.contatos[x.contatos.length - 1] || {}).canal || 'Outro', nota: '' }).then(function (ok) { if (ok) { indexar(); render(); } });
  });
  window.addEventListener('focus', function () {
    if (!pendente) return;
    var p = pendente; pendente = null;
    setTimeout(function () {
      if (!confirm('Você enviou a mensagem por ' + p.canal + ' para ' + porCnpj[p.cnpj].e.razao_social + '? OK registra o contato de hoje.')) return;
      salvar({ cnpj: p.cnpj, status: 'contatado', canal: p.canal, nota: 'Mensagem enviada pelo painel' }).then(function (ok) { if (ok) { indexar(); render(); } });
    }, 300);
  });
  function renderReprovados() {
    var l = lista().filter(function (x) { return x.tri === 'reprovado' || (x.tri === 'aprovado' && x.lixoEm); }).map(function (x) {
      var lixo = x.tri !== 'reprovado', de = lixo ? x.lixoEm : new Date(TRI[x.e.cnpj].decidido_em);
      return { x: x, lixo: lixo, de: de, sai: new Date(de.getTime() + DIAS_REPROVADO * 864e5) };
    }).sort(function (a, b) { return b.de - a.de; });
    $('n-rep').textContent = l.length || '';
    $('x-info').textContent = l.length + ' empresa(s): reprovadas na conferência ou sem resposta depois de 3 tentativas. Ficam ' + DIAS_REPROVADO + ' dias aqui antes de sair do banco.';
    $('x-linhas').innerHTML = l.map(function (r) {
      var x = r.x, t = TRI[x.e.cnpj], falta = Math.max(0, Math.ceil((r.sai - Date.now()) / 864e5));
      return '<tr><td><strong>' + esc(x.e.razao_social) + '</strong><br><small>' + esc(x.e.cnpj) + (x.pri ? ' · prioridade ' + esc(x.pri) : '') + '</small><div class="selos-l"><span class="selo' + (r.lixo ? ' selo-amar' : ' selo-verm') + '">' + (r.lixo ? 'Sem resposta em ' + x.tentativas + ' tentativas' : '✕ Reprovada na conferência') + '</span></div></td>' +
        '<td data-l="Desde"><small>' + esc(r.de.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })) + (r.lixo ? '' : '<br>' + esc(t.autor_email || '')) + '</small></td>' +
        '<td data-l="Sai do banco em"><small>' + esc(r.sai.toLocaleDateString('pt-BR')) + '</small><br><span class="selo' + (falta <= 7 ? ' selo-verm' : '') + '">faltam ' + falta + ' dia(s)</span></td>' +
        '<td class="td-acao"><button class="btn btn-linha btn-sm" data-abrir="' + esc(x.e.cnpj) + '" type="button">Abrir</button> <button class="btn btn-wa btn-sm" ' + (r.lixo ? 'data-recomecar' : 'data-restaurar') + '="' + esc(x.e.cnpj) + '" type="button">Restaurar</button></td></tr>';
    }).join('') || '<tr><td colspan="4">Nenhuma empresa aqui.</td></tr>';
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-recomecar]'); if (!b) return;
    salvar({ cnpj: b.getAttribute('data-recomecar'), status: 'novo', canal: 'Outro', nota: 'Restaurada do lixo: contatos recomeçam do zero' }).then(function (ok) { if (ok) { indexar(); render(); } });
  });
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-restaurar]'); if (!b) return;
    var c = b.getAttribute('data-restaurar'), ant = TRI[c];
    gravarTri(c, null).then(function (ok) { if (ok) { desfazer.push({ cnpj: c, ant: ant }); indexar(); confAtual = null; render(); } });
  });

  // Planilha dos aprovados (SheetJS, carregado só quando pedir)
  function carregarXlsx() {
    if (window.XLSX) return Promise.resolve();
    return new Promise(function (ok, erro) {
      var s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js';
      s.onload = ok; s.onerror = function () { erro(new Error('não carregou a biblioteca da planilha')); }; document.head.appendChild(s);
    });
  }
  function baixarPlanilha() {
    var l = aprovados(); if (!l.length) return;
    var bt = $('a-xls'); bt.disabled = true; bt.textContent = 'Gerando…';
    carregarXlsx().then(function () {
      var IB = 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao', RF = 'Cadastro do CNPJ (Receita Federal, via base pública)';
      var emp = l.map(function (x) {
        var e = x.e, t = TRI[e.cnpj], sc = e.site_contatos || {}, j = function (a) { return (a || []).join(' / '); };
        return {
          'CNPJ': e.cnpj, 'Razão social': e.razao_social, 'Nome fantasia': e.nome_fantasia || '', 'Situação na Receita': e.situacao_receita || '', 'Porte': e.porte || '',
          'MEI / empresário individual': e.individual ? 'Sim' : 'Não', 'Atividade': e.atividade || '', 'Município sede': e.municipio_sede || '',
          'Sócios (QSA, CPF mascarado)': masc(e.socios || ''), 'Fonte do cadastro': RF + (e.data_coleta ? ', coletado em ' + br(e.data_coleta) : ''),
          'Telefones (Receita)': x.tels.map(fmtTel).join(' / '), 'E-mail': e.email || '', 'Fonte do e-mail': e.email_fonte || (e.email ? RF : ''),
          'Site': e.site || '', 'Como o site foi confirmado': e.site_confirmacao || '', 'E-mails no site': j(sc.emails), 'Telefones no site': j((sc.telefones || []).map(fmtTel)),
          'WhatsApp no site': j((sc.whatsapp || []).map(fmtTel)), 'Redes sociais no site': j(sc.redes), 'Páginas do site lidas': j(sc.paginas), 'Site conferido em': e.site_busca_em ? br(e.site_busca_em) : '',
          'Prioridade': e.prioridade || '', 'Pontos': e.pontos == null ? '' : e.pontos, 'Motivos da prioridade': e.motivos || '', 'Chance de licenciamento': e.chance_licenciamento || '', 'Pontos (licenciamento)': e.chance_pontos == null ? '' : e.chance_pontos, 'Motivo (licenciamento)': e.chance_motivo || '',
          'Nº de autos': x.autos.length, 'Último documento': x.ultimo ? br(x.ultimo) : '', 'Municípios dos autos': x.muns.join(', '),
          'Embargos vigentes': e.embargos_vigentes || 0, 'Prazo de defesa estimado até': e.prazo_defesa_ate ? br(e.prazo_defesa_ate) + ' (estimativa: ciência + 20 dias; confirmar na notificação)' : '',
          'Status do contato': ST[x.status] || x.status, 'Aprovado em': brDH(t.decidido_em), 'Aprovado por': t.autor_email || '', 'Fonte dos autos': IB
        };
      });
      var autos = [];
      l.forEach(function (x) {
        x.autos.forEach(function (a) { autos.push({ 'CNPJ': x.e.cnpj, 'Razão social': x.e.razao_social, 'Documento': 'Auto de infração', 'Número': a.n_auto, 'Data': br(a.data_auto), 'Município': a.municipio || '', 'Tipo de infração': a.tipo_infracao || '', 'Gravidade': a.gravidade || '', 'Valor indicado no auto (não é dano)': a.valor_auto == null ? '' : Number(a.valor_auto), 'Situação': a.cancelado ? 'CANCELADO' : '', 'Processo': a.processo || '', 'Descrição': masc(a.descricao || ''), 'Nível': 'FATO', 'Fonte': IB }); });
        x.occ.filter(function (o) { return !/^IBAMA-AUTO\|/.test(o.chave || ''); }).forEach(function (o) { autos.push({ 'CNPJ': x.e.cnpj, 'Razão social': x.e.razao_social, 'Documento': tipoCurto(o.tipo_documento), 'Número': o.numero || '', 'Data': br(o.data_documento), 'Município': o.municipio || '', 'Tipo de infração': o.assunto || '', 'Gravidade': '', 'Valor indicado no auto (não é dano)': o.valor_indicado_rs_nao_e_dano == null ? '' : Number(o.valor_indicado_rs_nao_e_dano), 'Situação': o.situacao || '', 'Processo': o.processo || '', 'Descrição': masc(o.descricao || ''), 'Nível': o.nivel || 'FATO', 'Fonte': /^https:\/\//.test(o.link_fonte || '') ? o.link_fonte : (o.orgao || '') }); });
      });
      var notas = [
        { 'Item': 'Gerado em', 'Texto': new Date().toLocaleString('pt-BR') + ' por ' + usuario },
        { 'Item': 'Seleção', 'Texto': $('a-per').options[$('a-per').selectedIndex].text + ' na conferência (' + l.length + ' empresa(s))' },
        { 'Item': 'Autos', 'Texto': 'IBAMA Dados Abertos: ' + IB + '. Auto de infração não é condenação. Valor indicado não é dano.' },
        { 'Item': 'Cadastro e e-mail', 'Texto': 'Base pública do CNPJ (Receita Federal) consultada por CNPJ.ws/ReceitaWS; a coluna "Fonte do e-mail" diz qual e quando.' },
        { 'Item': 'Site', 'Texto': 'Só é aceito se o Registro.br mostrar o próprio CNPJ como titular ou se o site mostrar o CNPJ. Contatos lidos das páginas públicas do site.' },
        { 'Item': 'Níveis', 'Texto': 'FATO = documento oficial. INDÍCIO = menção em diário oficial: ler o ato antes de concluir.' },
        { 'Item': 'Privacidade', 'Texto': 'CPF sempre mascarado. Contato de MEI é da própria pessoa: usar só para tratar do auto e atender pedido de não contato (LGPD).' }
      ];
      var wb = XLSX.utils.book_new();
      [['Empresas', emp], ['Documentos', autos], ['Fontes e notas', notas]].forEach(function (p) {
        var ws = XLSX.utils.json_to_sheet(p[1]);
        var cols = Object.keys(p[1][0] || {}); ws['!cols'] = cols.map(function (c) { return { wch: Math.min(60, Math.max(c.length, 12)) }; });
        XLSX.utils.book_append_sheet(wb, ws, p[0]);
      });
      var per = $('a-per').value;
      XLSX.writeFile(wb, 'aprovados-' + (per === 'hoje' ? hojeISO() : per ? 'ultimos-' + per + '-dias-' + hojeISO() : 'todos-' + hojeISO()) + '.xlsx');
    }).catch(function (e) { alert('Não foi possível gerar a planilha: ' + e.message); }).then(function () { bt.disabled = false; bt.textContent = 'Baixar planilha (Excel)'; });
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

  // Mensagens de prospecção: tom institucional e comercial (a empresa falando com a empresa).
  // Sem promessa de resultado e sem linguagem jurídica (consultoria registrada no CREA, não advocacia).
  function dadosMensagem(x) {
    var d = x.validos[0];
    var nome = String(x.e.razao_social || '').replace(/\s*\[CPF omitido\]/g, '').replace(/\d{3}\.?\d{3}\.?\d{3}-?\d{2}/g, '').replace(/\s{2,}/g, ' ').trim();
    var mun = d && d.municipio ? String(d.municipio).toLowerCase().replace(/(^|\s)\S/g, function (c) { return c.toUpperCase(); }).replace(/ (De|Da|Do|Dos|Das|E) /g, function (m) { return m.toLowerCase(); }) : '';
    return {
      d: d, nome: nome, mun: mun,
      mes: d && /^\d{4}-\d{2}/.test(d.data_documento || '') ? ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'][+d.data_documento.slice(5, 7) - 1] + ' de ' + d.data_documento.slice(0, 4) : '',
      empresa: C.nomeEmpresa || 'Origem Consultoria Ambiental',
      site: C.site || (location.hostname ? location.origin : 'https://ambientalcosta.netlify.app')
    };
  }
  function corpoMensagem(x) {
    var m = dadosMensagem(x), d = m.d, p = [];
    p.push('A ' + m.empresa + ' é uma empresa de engenharia e consultoria ambiental registrada no CREA-RJ, com atuação em todo o Estado do Rio de Janeiro.');
    if (d) p.push('Em consulta a dados públicos ' + fonteCurta(d) + ', identificamos ' + (/^(notificação|penalidade|menção|licença|comunicação)/.test(tipoCurto(d.tipo_documento)) ? 'uma ' : 'um ') + tipoCurto(d.tipo_documento) + (d.numero ? ' nº ' + d.numero : '') + (m.mes ? ', de ' + m.mes : '') + ', em nome de sua empresa' + (m.mun ? ', no município de ' + m.mun : '') + '.');
    p.push(d ? 'Prestamos assessoria técnica a empresas nessa situação, que compreende: análise técnica do caso e dos prazos administrativos; elaboração de laudos e pareceres técnicos; Projeto de Recuperação de Área Degradada (PRAD); e regularização e licenciamento ambiental.'
      : 'Prestamos assessoria técnica ambiental a empresas, que compreende: diagnóstico da situação ambiental; regularização e licenciamento ambiental; elaboração de laudos e pareceres técnicos; e acompanhamento de exigências dos órgãos ambientais.');
    p.push('Caso seja de interesse, teremos satisfação em agendar uma breve reunião de apresentação, sem compromisso, para avaliar a situação e indicar os caminhos técnicos possíveis.');
    return p;
  }
  function mensagemPadrao(x) {   // WhatsApp
    var m = dadosMensagem(x);
    return masc((m.nome ? ['À ' + m.nome, ''] : []).concat('Prezados(as) Senhores(as),', '', corpoMensagem(x).join('\n\n'), '',
      'Atenciosamente,', m.empresa, m.site, '',
      'Caso não deseje receber novos contatos, basta responder SAIR.').join('\n'));
  }
  function assuntoEmail(x) {
    var d = x.validos[0];
    return (C.nomeEmpresa || 'Origem Consultoria Ambiental') + ' | Assessoria técnica ambiental' + (d ? ' – ' + tipoCurto(d.tipo_documento).replace(/^./, function (c) { return c.toUpperCase(); }) + (d.numero ? ' nº ' + d.numero : '') : '');
  }
  function mensagemEmail(x) {
    var m = dadosMensagem(x);
    return masc((m.nome ? ['À ' + m.nome, ''] : []).concat('Prezados(as) Senhores(as),', '', corpoMensagem(x).join('\n\n'), '',
      'Permanecemos à disposição para quaisquer esclarecimentos.', '',
      'Atenciosamente,', '', m.empresa, 'Engenharia e Consultoria Ambiental | CREA-RJ', m.site + (C.email ? ' | ' + C.email : ''), '',
      'Os dados mencionados acima são públicos e foram obtidos ' + (m.d ? 'nas bases abertas ' + fonteCurta(m.d) : 'em bases abertas oficiais') + ' e no cadastro do CNPJ. Caso não deseje receber novos contatos, basta responder a este e-mail com a palavra SAIR.').join('\n'));
  }

  function abrir(cnpj, alvo) {
    var x = porCnpj[cnpj], e = x.e, bloq = x.status === 'nao_contatar';
    var avisos = '';
    if (e.situacao_receita !== 'ATIVA') avisos += '<p class="aviso-l verm">Empresa ' + esc(e.situacao_receita) + ' na Receita. Não prospectar sem conferir quem responde hoje pela atividade.</p>';
    if (e.nome_divergente) avisos += '<p class="aviso-l amar">O nome escrito no auto difere da razão social atual. Pode ser troca de nome ou CNPJ digitado errado no auto. Confira antes de contatar (HIPÓTESE, não FATO).</p>';
    if (e.individual) avisos += '<p class="aviso-l">MEI / empresário individual: o contato é da própria pessoa. Use só para tratar do auto, identifique a fonte (dados abertos do IBAMA e cadastro do CNPJ) e atenda na hora a quem pedir para não ser contatado (LGPD).</p>';
    if (e.chance_motivo) avisos += '<p class="aviso-l"><strong>Chance de contratar licenciamento (' + esc(e.chance_licenciamento || '') + '):</strong> ' + esc(e.chance_motivo) + '. É juízo comercial, não acusação.</p>';
    if (e.motivos) avisos += '<p class="aviso-l"><strong>Por que esta prioridade:</strong> ' + esc(e.motivos) + '. A pontuação indica urgência de contato; não indica culpa nem dano.</p>';
    if (e.prazo_defesa_ate) avisos += '<p class="aviso-l amar">Prazo de defesa <strong>estimado</strong> até ' + esc(br(e.prazo_defesa_ate)) + ' (ciência + 20 dias, Decreto 6.514/2008, art. 113). Confirme na notificação.</p>';
    if (bloq) avisos += '<p class="aviso-l verm">Marcada como <strong>Não contatar</strong>. Não envie mensagens.</p>';

    var contato = '';
    var sc = e.site_contatos || null, siteHtml = '';
    if (!bloq && e.site) {
      var lst = function (rot, arr, fn) { return arr && arr.length ? '<li><strong>' + rot + ':</strong> ' + arr.map(fn).join(' · ') + '</li>' : ''; };
      siteHtml = '<h3>No site da empresa</h3><p><a href="' + esc(e.site) + '" target="_blank" rel="noopener">' + esc(e.site) + '</a> <small>(' + esc(e.site_confirmacao || '') + ')</small></p><ul class="tels">' +
        (sc ? lst('E-mail', sc.emails, function (m) { return '<a href="mailto:' + esc(m) + '">' + esc(m) + '</a>'; }) +
          lst('Telefone', sc.telefones, function (t) { return '<a href="tel:+55' + esc(t) + '">' + esc(fmtTel(t)) + '</a>'; }) +
          lst('WhatsApp', sc.whatsapp, function (t) { return '<a class="js-wa-g" data-tel="55' + esc(t) + '" href="#">' + esc(fmtTel(t)) + '</a>'; }) +
          lst('Redes', sc.redes, function (u) { return '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(u.replace(/^https?:\/\/(www\.)?/, '')) + '</a>'; }) : '') + '</ul>';
    }
    if (!bloq && (x.tels.length || e.email || e.site)) {
      contato = '<h3>Contato (cadastro da Receita)</h3><ul class="tels">' + x.tels.map(function (t) {
        return '<li><span>' + esc(fmtTel(t)) + '</span> <a class="btn btn-linha btn-sm" href="tel:+55' + t + '">Ligar</a>' +
          (celular(t) ? ' <a class="btn btn-wa btn-sm js-wa-g" data-tel="55' + t + '" href="#">WhatsApp</a>' : ' <small>fixo, sem WhatsApp</small>') + '</li>';
      }).join('') + '</ul>' + (e.email ? '<p><a href="mailto:' + esc(e.email) + '">' + esc(e.email) + '</a></p>' : '') +
        siteHtml + '<label class="campo"><span>Mensagem sugerida (edite antes de enviar)</span><textarea id="g-msg" rows="12">' + esc(mensagemPadrao(x)) + '</textarea></label>';
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

    var formHtml = alvo ? '' : '<h3>Registrar contato</h3><form class="g-form" id="g-form"><div class="duas">' +
      '<label class="campo"><span>Status</span><select id="g-st">' + Object.keys(ST).map(function (k) { return '<option value="' + k + '"' + (k === x.status ? ' selected' : '') + '>' + ST[k] + '</option>'; }).join('') + '</select></label>' +
      '<label class="campo"><span>Canal</span><select id="g-canal"><option>WhatsApp</option><option>Telefone</option><option>E-mail</option><option>Presencial</option><option>Outro</option></select></label></div>' +
      '<label class="campo"><span>Anotação</span><textarea id="g-nota" rows="2" placeholder="Ex.: falei com o setor ambiental, pediram proposta"></textarea></label>' +
      '<button class="btn btn-wa btn-sm" type="submit">Salvar registro</button> <small class="erro" id="g-erro" hidden></small></form>' +
      '<h3>Histórico</h3><ul class="hist">' + hist + '</ul>';
    var corpo = alvo || $('gaveta-corpo');
    corpo.innerHTML = (alvo ? '<div class="selos-l">' + selos(e) + '</div>' : '') +
      '<h2 id="g-tit">' + esc(e.razao_social) + '</h2>' +
      '<p class="g-sub">' + esc(e.cnpj) + (e.nome_fantasia ? ' · ' + esc(e.nome_fantasia) : '') + '<br>' + esc(e.atividade || '') + '<br>Sede: ' + esc(e.municipio_sede || '') + ' · ' + esc(e.situacao_receita || '') + '</p>' +
      (e.socios ? '<p class="g-sub"><strong>Sócios (QSA):</strong> ' + esc(masc(e.socios)) + '</p>' : '') +
      avisos + contato +
      formHtml +
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

    if (!alvo) { $('gaveta').hidden = false; $('gaveta-fundo').hidden = false; $('gaveta').scrollTop = 0; }

    corpo.querySelectorAll('.js-wa-g').forEach(function (a) {
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        var m = corpo.querySelector('#g-msg');
        window.open('https://wa.me/' + a.getAttribute('data-tel') + '?text=' + encodeURIComponent(m ? m.value : mensagemPadrao(x)), '_blank', 'noopener');
      });
    });
    if (alvo) return;
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
      if (r.error && !$('g-erro')) { alert('Não foi possível salvar: ' + r.error.message); return false; }
      if (r.error) { $('g-erro').textContent = 'Não foi possível salvar: ' + r.error.message; $('g-erro').hidden = false; return false; }
      D.contatos.push(r.data[0]); return true;
    });
  }
})();
