#!/usr/bin/env python3
"""
Ambiental Costa · DOU Seção 3: editais de notificação/intimação de órgãos ambientais federais (IBAMA, ICMBio, MMA, ANA).
Versão online da opção [5] do Radar-Ambiental (c5_dou_editais.ps1, v4), com as mesmas regras.

Fontes (nenhuma sozinha):
  A) INLABS (Imprensa Nacional), edição diária DO3 + DO3E. Precisa de login: o usuário cola INLABS_EMAIL e INLABS_SENHA
     nos Secrets do GitHub. A senha nunca aparece no log. Sem login, ou com o site em manutenção, pula para B.
  B) Base mensal dos Dados Abertos da Imprensa Nacional (S03MMAAAA.zip), sem login. Sai com atraso de semanas;
     cobre o mês que o INLABS não cobriu.
O que entra no banco (tabela ocorrencias, nivel FATO = ato publicado; notificação/intimação NÃO é condenação):
  um registro por CNPJ (DV válido) citado em ato de órgão ambiental cujo texto fala de auto de infração,
  notificação, intimação, embargo, multa ou penalidade, e que menciona o RJ. CPF é mascarado em todo texto.

Uso: python -I coletor/dou.py [--dias 7] [--meses 1] [--sem-supabase] [--amostra]
"""
import datetime as dt, http.cookiejar, io, os, re, sys, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from coletar import Supabase, dv_cnpj, fmt_cnpj, mascara, log, UA   # mesmas regras do coletor diário

INLABS = 'https://inlabs.in.gov.br'
ORIGEM = {'origem': '736372697074'}            # cabeçalho dos scripts oficiais do INLABS (github.com/Imprensa-Nacional/inlabs)
DADOS_ABERTOS = 'https://www.in.gov.br/acesso-a-informacao/dados-abertos/base-de-dados'
SECOES = ('DO3', 'DO3E')
LIMITE_INLABS = 120                            # dias que o INLABS guarda
RX_ORGAO = re.compile(r'Instituto Brasileiro do Meio Ambiente|Instituto Chico Mendes|Meio Ambiente|Ag[eê]ncia Nacional de [AÁ]guas', re.I)
RX_ASSUNTO = re.compile(r'auto de infra|notifica|intima|embargo|multa|penalidade|infrator|autuad', re.I)
RX_RJ = re.compile(r'Rio de Janeiro|/RJ\b|\bRJ\b')
RX_CNPJ = re.compile(r'(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)')
RX_AUTO = re.compile(r'autos? de infra[cç][aã]o\s*(?:n[º°o]\.?|n[uú]mero)?\s*[:.]?\s*([A-Z]{0,4}\d[0-9A-Z]{4,11}(?:-[A-Z])?)\b', re.I)


def arg(nome, padrao):
    return type(padrao)(sys.argv[sys.argv.index(nome) + 1]) if nome in sys.argv else padrao


class Cliente:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def get(self, url, dados=None, cab=None, timeout=300):
        r = urllib.request.Request(url, data=dados, headers=dict({'User-Agent': UA}, **(cab or {})))
        with self.op.open(r, timeout=timeout) as resp:
            return resp.read()


def inlabs_login(c):
    try:
        if re.search(rb'(?i)manuten', c.get(INLABS + '/', timeout=30)): return 'EM MANUTENÇÃO'
    except Exception as e: return f'FORA DO AR ({e.__class__.__name__})'
    email, senha = os.environ.get('INLABS_EMAIL', '').strip(), os.environ.get('INLABS_SENHA', '')
    if not email or not senha: return 'SEM LOGIN (falta INLABS_EMAIL/INLABS_SENHA nos Secrets do GitHub)'
    try:
        c.get(INLABS + '/logar.php', urllib.parse.urlencode({'email': email, 'password': senha}).encode(), ORIGEM, 60)
    except Exception as e: return f'LOGIN FALHOU ({e.__class__.__name__})'
    finally: senha = None
    if not any(k.name == 'inlabs_session_cookie' for k in c.cj): return 'LOGIN NÃO ACEITO (sem cookie de sessão)'
    return 'OK'


class Leitor:
    def __init__(self):
        self.atos, self.vistos, self.datas = [], set(), set()

    def artigo(self, xml, fonte, so_datas=None):
        try: raiz = ET.fromstring(xml)
        except ET.ParseError: return 0
        a = raiz if raiz.tag == 'article' else raiz.find('.//article')
        if a is None: return 0
        pub = a.get('pubDate') or ''
        if so_datas and pub not in so_datas: return 0
        self.datas.add(pub)
        cat = a.get('artCategory') or ''
        if not RX_ORGAO.search(cat): return 0
        corpo = a.find('.//body')
        bruto = ' '.join(''.join(e.itertext()) for e in (list(corpo) if corpo is not None else [a]))
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', bruto).replace('&nbsp;', ' ')).strip()
        if not RX_ASSUNTO.search(txt): return 0
        chave = f"{a.get('id')}|{a.get('idMateria')}|{pub}"
        if chave in self.vistos: return 0
        self.vistos.add(chave)
        ident = a.find('.//Identifica')
        ident = ''.join(ident.itertext()).strip() if ident is not None else (a.get('name') or '')
        docs = sorted({fmt_cnpj(m.group(0)) for m in RX_CNPJ.finditer(txt) if dv_cnpj(m.group(0))})
        self.atos.append(dict(pub=pub, secao=a.get('pubName') or '', pagina=a.get('numberPage') or '', orgao=cat, tipo=a.get('artType') or '',
                              ident=mascara(ident), rj=bool(RX_RJ.search(cat + ' ' + txt)), cnpjs=docs,
                              autos=sorted({m.group(1) for m in RX_AUTO.finditer(txt)}), txt=txt, link=a.get('pdfPage') or '',
                              id_materia=a.get('idMateria') or a.get('id') or '', fonte=fonte))
        return 1

    def zip(self, binario, fonte, so_datas=None):
        n = 0
        with zipfile.ZipFile(io.BytesIO(binario)) as z:
            for nome in z.namelist():
                if nome.lower().endswith('.xml'): n += self.artigo(z.read(nome), fonte, so_datas)
                elif nome.lower().endswith('.zip'): n += self.zip(z.read(nome), fonte, so_datas)
        return n


def data_br(d): return d.strftime('%d/%m/%Y')


def main():
    dias, meses = arg('--dias', 7), arg('--meses', 1)
    sem_sb = '--sem-supabase' in sys.argv
    hoje = dt.date.today(); t0 = dt.datetime.now(dt.timezone.utc)
    sb = None if sem_sb else Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
    c, L, cob = Cliente(), Leitor(), []

    # A) INLABS
    datas = [hoje - dt.timedelta(days=i) for i in range(dias)]
    datas = [d for d in datas if d.weekday() < 5]
    sit = inlabs_login(c)
    log(f'INLABS: {sit}')
    ok_do3 = set()
    for k, d in enumerate(datas):
        for s in SECOES:
            nome = f'{d:%Y-%m-%d}-{s}.zip'; st = 'OK'; n = 0
            if sit != 'OK': st = f'INLABS {sit.split(" (")[0]}'
            else:
                try:
                    b = c.get(f'{INLABS}/index.php?p={d:%Y-%m-%d}&dl={nome}', cab=ORIGEM)
                    if b[:2] != b'PK':
                        st = 'ERRO MANUTENÇÃO' if re.search(rb'(?i)manuten', b) else 'ERRO SESSÃO' if re.search(rb'(?i)logar|login|senha', b) else 'SEM EDIÇÃO'
                    else: n = L.zip(b, f'DOU {s} via INLABS (Imprensa Nacional)')
                except urllib.error.HTTPError as e: st = 'SEM EDIÇÃO' if e.code == 404 else f'ERRO {e.code}'
                except Exception as e: st = f'ERRO {e.__class__.__name__}'
            if st == 'SEM EDIÇÃO' and s == 'DO3E': st = 'SEM EXTRA'
            if s == 'DO3' and st in ('OK', 'SEM EDIÇÃO'): ok_do3.add(d)
            cob.append((f'{d:%Y-%m-%d}', s, st, n))
        log(f'{d:%d/%m/%Y}: ' + ' · '.join(f'{x[1]} {x[2]} ({x[3]} atos)' for x in cob[-2:]), 60 * (k + 1) / max(1, len(datas)))

    # B) base mensal para os dias sem DO3 e para os meses anteriores (--meses)
    faltam = [d for d in datas if d not in ok_do3]
    alvo = {}
    for d in faltam: alvo.setdefault(f'{d:%m%Y}', set()).add(data_br(d))
    y, m = hoje.year, hoje.month
    for _ in range(meses):                                       # meses anteriores inteiros
        m -= 1
        if m == 0: m, y = 12, y - 1
        alvo[f'{m:02d}{y}'] = None                                # None = mês inteiro
    pagina = None
    for mmaaaa, so in sorted(alvo.items(), key=lambda x: x[0][2:] + x[0][:2]):
        if pagina is None:
            try: pagina = c.get(DADOS_ABERTOS, timeout=60).decode('utf-8', 'ignore')
            except Exception as e: pagina = ''; log(f'página dos Dados Abertos: {e}')
        links = sorted({(u if u.startswith('http') else 'https://www.in.gov.br' + u).replace('&amp;', '&')
                        for u in re.findall(rf'href="([^"]*?S0?3\w*?{mmaaaa}[^"]*?\.zip[^"]*)"', pagina, re.I)})
        if not links:
            log(f'base mensal {mmaaaa}: ainda não publicada (ou link não achado)'); cob.append((mmaaaa, 'DO3 mensal', 'NÃO PUBLICADA', 0)); continue
        for u in links:
            log(f'base mensal {mmaaaa}: baixando {u}')
            try: b = c.get(u, timeout=1200)
            except Exception as e: log(f'   falhou: {e}'); cob.append((mmaaaa, 'DO3 mensal', f'ERRO {e.__class__.__name__}', 0)); continue
            if b[:2] != b'PK': log('   não é zip; ignorado'); continue
            n = L.zip(b, 'DOU Seção 3 - base mensal Dados Abertos (Imprensa Nacional)', so)
            cob.append((mmaaaa, 'DO3 mensal', 'OK', n)); log(f'   {n} ato(s) ambiental(is) em {len(b) / 1e6:.0f} MB')

    rj = [a for a in L.atos if a['rj']]
    com_cnpj = [a for a in rj if a['cnpjs']]
    log(f'{len(L.atos)} ato(s) ambiental(is); {len(rj)} mencionam o RJ; {len(com_cnpj)} com CNPJ válido', 90)

    occ = []
    for a in com_cnpj:
        try: d = dt.datetime.strptime(a['pub'], '%d/%m/%Y').date().isoformat()
        except ValueError: d = None
        trecho = mascara(a['txt'][:1500])
        for cn in a['cnpjs']:
            occ.append(dict(chave=f"DOU3|{cn}|{a['pub']}|{a['id_materia']}", fonte=a['fonte'], orgao=a['orgao'][:120],
                            tipo_documento=f"EDITAL DOU SECAO 3 - {a['tipo'].upper()}"[:120], numero=' | '.join(a['autos'])[:200], processo='',
                            data_documento=d, situacao='VALIDO', cnpj=cn, nome='', municipio='',
                            assunto=a['ident'][:300], descricao='Ato publicado no DOU (FATO). Notificação/intimação NÃO é condenação. ' + trecho,
                            nivel='FATO', link_fonte=a['link'], ultima_coleta=hoje.isoformat(), origem='coletor-online'))
    occ = list({o['chave']: o for o in occ}.values())
    if '--amostra' in sys.argv:
        for o in occ[:10]: log(f"   amostra: {o['data_documento']} · {o['cnpj']} · {o['orgao'][:60]} · {o['tipo_documento'][:50]} · autos {o['numero']} · {o['assunto'][:80]}")
        for a in rj[:5]: log(f"   ato RJ: {a['pub']} · {a['orgao'][:60]} · {a['ident'][:80]} · CNPJs {a['cnpjs']}")
    novas = len(occ)
    if sb:
        ja = {o['chave'] for o in sb.todos('ocorrencias', 'chave') if o['chave'].startswith('DOU3|')}
        novas = len([o for o in occ if o['chave'] not in ja])
        if occ: sb.upsert('ocorrencias', occ, 'chave')
        sb.req('POST', '/coletas', dict(
            fonte='DOU Seção 3 (INLABS e base mensal dos Dados Abertos da Imprensa Nacional): editais de órgãos ambientais federais',
            metodo=f'artCategory ~ órgão ambiental e texto ~ notificação/intimação/auto/embargo/multa; menciona RJ; CNPJ com DV válido; CPF mascarado; janela {dias} dia(s) + {meses} mês(es) da base mensal',
            status='ok', iniciada_em=t0.isoformat(), terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(),
            autos_lidos=len(L.atos), autos_novos=novas,
            mensagem=(f'INLABS: {sit}; {len(rj)} ato(s) com RJ, {len(com_cnpj)} com CNPJ; {novas} registro(s) novo(s); '
                      + '; '.join(f'{x[0]} {x[1]} {x[2]}' for x in cob if not x[2].startswith(('OK', 'SEM EXTRA'))))[:900]),
            {'Prefer': 'return=minimal'})
    log(f'FIM: {len(occ)} registro(s) de CNPJ ({novas} novo(s))', 100)
    print('\a')


if __name__ == '__main__':
    main()
