#!/usr/bin/env python3
"""
Ambiental Costa · Leitura dos diários oficiais municipais do RJ baixados pelos
raspadores abertos do Querido Diário (github.com/okfn-brasil/querido-diario, licença MIT).

Não usa a API do Querido Diário: os PDFs vêm direto dos sites das prefeituras.
Procura, em cada edição:
  (a) CNPJ de empresa que já está na nossa base (Supabase);
  (b) termos ambientais (licença, auto de infração, embargo...) e os CNPJs citados perto deles.
Tudo o que sai daqui é INDÍCIO: menção em diário não é condenação nem prova de irregularidade.
Vão para o banco (tabela ocorrencias, nivel INDICIO, não pontua):
  (a) menção a empresa da base;
  (b) CNPJ (DV válido) citado perto de termo ambiental, com a razão social conferida na Receita (possível cliente novo).
Trechos com termo ambiental sem CNPJ ficam só no relatório CSV. Cada execução fica registrada na tabela coletas.
PDF sem texto (imagem escaneada) é lido por OCR (tesseract, português), com limite de páginas por edição.

Uso: python -I coletor/diarios_rj.py <pasta_jsonl> <pasta_saida> [--sem-supabase]
"""
import csv, datetime as dt, glob, json, os, re, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from coletar import Supabase, dv_cnpj, mascara, sem_acento, log, cadastro   # mesmas regras do coletor diário
from concurrent.futures import ThreadPoolExecutor
import shutil, tempfile, hashlib

TERMOS = [
    r'auto de infra[cç][aã]o', r'licen[cç]a ambiental', r'licenciamento ambiental', r'licen[cç]a (?:previa|pr[eé]via|de instala[cç][aã]o|de opera[cç][aã]o)',
    r'embargo', r'multa ambiental', r'infra[cç][aã]o ambiental', r'crime ambiental', r'dano ambiental', r'supress[aã]o de vegeta[cç][aã]o',
    r'termo de ajustamento de conduta', r'secretaria (?:municipal )?de (?:meio )?ambiente', r'\bINEA\b', r'interdi[cç][aã]o',
    r'notifica[cç][aã]o ambiental', r'compensa[cç][aã]o ambiental', r'\bPRAD\b', r'estudo de impacto ambiental', r'\bEIA\b',
]
RX_TERMO = re.compile('|'.join(TERMOS), re.I)
# Para gravar CNPJ como possível cliente, o termo precisa indicar ação sobre a empresa (não basta citar a secretaria ou o INEA)
RX_LEAD = re.compile(r'auto de infra|licen[cç]a|licenciamento|embargo|multa|infra[cç][aã]o ambiental|crime ambiental|dano ambiental|supress[aã]o|'
                     r'ajustamento de conduta|interdi[cç][aã]o|notifica[cç][aã]o|compensa[cç][aã]o|PRAD|impacto ambiental', re.I)
# Atos ambientais por categoria (relatório anual "quem publicou e quem não publicou"; 10/11/2026). Só conta quando há
# contexto ambiental perto (evita "notificação" de servidor, "interdição" de rua etc.). Tudo INDÍCIO de publicação, não de irregularidade.
AMB_CAT = [
    ('notificacao_ambiental', re.compile(r'notifica[cç][aã]o', re.I)),
    ('auto_infracao_ambiental', re.compile(r'auto de infra[cç][aã]o', re.I)),
    ('embargo_interdicao', re.compile(r'\bembarg|interdi[cç][aã]o', re.I)),
    ('licenca_ambiental', re.compile(r'licen[cç]a (?:ambiental|municipal ambiental|pr[eé]via|de instala[cç][aã]o|de opera[cç][aã]o|simplificada)|licenciamento ambiental|\bL[PIO]\s*n?[ºo°]', re.I)),
    ('tac_ambiental', re.compile(r'termo de (?:ajustamento|compromisso ambiental)', re.I)),
    ('supressao_vegetacao', re.compile(r'supress[aã]o de vegeta|corte de [aá]rvore|poda', re.I)),
    ('compensacao_ambiental', re.compile(r'compensa[cç][aã]o ambiental', re.I)),
]
RX_AMB_CTX = re.compile(r'meio ambiente|ambient|SEMMA|SEMAM|SMMA|SEMMATRAN|licenciamento|\bINEA\b|vegeta[cç]|polui[cç]|res[ií]duo|recursos h[ií]dricos|fauna|flora|APA\b|unidade de conserva', re.I)
JANELA_AMB = 300


def atos_ambientais(txt):
    """[(categoria, posição)] com contexto ambiental a até JANELA_AMB caracteres. Uma por categoria a cada 400 caracteres."""
    out, ult = [], {}
    for cat, rx in AMB_CAT:
        for m in rx.finditer(txt):
            i = m.start()
            if i - ult.get(cat, -10**9) < 400: continue
            if not RX_AMB_CTX.search(txt, max(0, i - JANELA_AMB), i + JANELA_AMB): continue
            ult[cat] = i; out.append((cat, i))
    return out


RX_CNPJ = re.compile(r'(?<!\d)(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?!\d)')
JANELA = 250
# atos de pessoal (plano único 09/11: mesmo formato da Vigia, nomeacoes_todas.csv). Secretário/subsecretário em destaque.
RX_PESSOAL = re.compile(r'\b(NOMEAR|NOMEIA|EXONERAR|EXONERA|DESIGNAR|DESIGNA|DISPENSAR|TORNAR SEM EFEITO A NOMEA[CÇ][AÃ]O)\b', re.I)
# alto escalão só quando é o CARGO do ato ("para o cargo ... de Secretário"), não quem assina (teste 09/11: 396 de 696 era largo demais)
RX_ALTO = re.compile(r'(cargo|fun[cç][aã]o)[^.;]{0,60}?\b((sub)?secret[aá]ri[oa]|chefe de gabinete|procurador[ -]geral|controlador[ -]geral)', re.I)


def fmt(c): return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}'


def cnpjs_em(txt):
    out = []
    for m in RX_CNPJ.finditer(txt):
        c = ''.join(m.groups())
        if dv_cnpj(c): out.append((c, m.start()))
    return out


def trecho(txt, i, n=300):
    a = max(0, i - n // 2); t = re.sub(r'\s+', ' ', txt[a:a + n]).strip()
    return mascara(t)


OCR_MAX_PAG = int(os.environ.get('OCR_MAX_PAG', '60'))     # páginas por edição (diário escaneado pode ter centenas)
OCR_MAX_MIN = float(os.environ.get('OCR_MAX_MIN', '45'))   # tempo total de OCR na execução
CAD_MAX = int(os.environ.get('CAD_MAX', '40'))              # consultas à Receita por execução (CNPJs novos)


def paginas(pdf):
    try:
        out = subprocess.run(['pdfinfo', pdf], capture_output=True, timeout=60).stdout.decode('utf-8', 'ignore')
        return int(re.search(r'Pages:\s+(\d+)', out).group(1))
    except Exception: return 0


def ocr(pdf):
    """Texto de PDF escaneado: cada página vira imagem (200 dpi) e passa pelo tesseract em português.
    Devolve (texto, páginas lidas, total de páginas)."""
    if not shutil.which('tesseract'): return '', 0, 0
    tot = paginas(pdf); n = min(tot, OCR_MAX_PAG)
    if not n:
        try:
            cab = open(pdf, 'rb').read(400)
            tipo = subprocess.run(['file', '-b', pdf], capture_output=True, timeout=30).stdout.decode()[:80].strip()
            log(f'   arquivo não é PDF legível: {tipo} · início: {cab[:120]!r}')
        except Exception: pass
        return '', 0, tot
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(['pdftoppm', '-r', '200', '-gray', '-png', '-f', '1', '-l', str(n), pdf, os.path.join(tmp, 'p')],
                       capture_output=True, timeout=900)
        imgs = sorted(glob.glob(os.path.join(tmp, 'p*.png')))
        def um(img):
            try: return subprocess.run(['tesseract', img, '-', '-l', 'por', '--psm', '3'], capture_output=True, timeout=300).stdout.decode('utf-8', 'ignore')
            except Exception: return ''
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as ex:
            return '\f'.join(ex.map(um, imgs)), len(imgs), tot   # \f separa páginas, como no pdftotext
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def seguir_link(pdf):
    """Portais 'transparencia.<municipio>.rj.gov.br' (Mesquita, Miguel Pereira, Quatis, Queimados, Meriti, S. Pedro da
    Aldeia) devolvem um arquivo de texto com o endereço do PDF em vez do PDF (visto em 09/11/2026). Baixa esse endereço
    e troca o arquivo. Sem login e sem contornar bloqueio: se o portal recusar, fica sem texto e vai para o log."""
    try:
        if os.path.getsize(pdf) > 2000: return False
        cab = open(pdf, 'rb').read().strip()
        if not re.match(rb'^https?://\S+$', cab): return False
        url = cab.decode('ascii', 'ignore')
        url = url.replace(' ', '%20')
        import urllib.request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; AmbientalCosta-Coletor/1.0; levantamento em dados abertos)'})
        with urllib.request.urlopen(req, timeout=120) as r:
            dado = r.read()
        if not dado.startswith(b'%PDF'):
            log(f'   link do portal não trouxe PDF ({len(dado)} bytes, início {dado[:40]!r}): {url[:140]}'); return False
        open(pdf, 'wb').write(dado)
        log(f'   PDF baixado pelo link do portal ({len(dado) // 1024} KB): {url[:140]}')
        return True
    except Exception as e:
        log(f'   link do portal falhou ({e})'); return False


RX_NOME_ATO = re.compile(r"^\s*[,:]?\s*(?:a pedido,?\s*)?(?:(?:o|a) (?:servidor|servidora|senhor|senhora|sr\.?|sra\.?)\s+)?([A-ZÀ-Ú][A-ZÀ-Ú'´`\. ]{4,90}?)(?=\s*(?:,|\(|\bpara\b|\bdo cargo\b|\bda fun|\bdo emprego\b|\bocupante\b|\bmatr|\bCPF\b|\bRG\b| - |$))")
RX_CARGO_ATO = re.compile(r'(?:cargo|fun[cç][aã]o|emprego)(?:\s+(?:em comiss[aã]o|comissionad[oa]|de confian[cç]a|efetivo|gratificad[oa]))?(?:\s+(?:de|do|da))?\s+([^,;.\n]{3,120})', re.I)


def nome_ato(t, verbo):
    """Nome logo depois do verbo (em maiúsculas, como os diários publicam). Vazio se não der para ler com segurança."""
    m = RX_NOME_ATO.match(t[len(verbo):])
    return m.group(1).strip(' .') if m and len(m.group(1).split()) >= 2 else ''


def cargo_ato(t):
    m = RX_CARGO_ATO.search(t)
    return m.group(1).strip() if m else ''


def gravar_comum(manifesto, citados, pessoal, base, ambiental=()):
    """Base comum do gabinete pelas funções RPC (regras de 09/11/2026). Nunca derruba a rodada."""
    from comum import Comum, hash_ato
    cm = Comum('diarios_rj.py', os.environ.get('GITHUB_SHA', 'local')[:12], 'GitHub Actions' if os.environ.get('GITHUB_ACTIONS') else 'local')
    if not cm.ok:
        log(f'formato comum: não gravado ({cm.motivo})'); return
    n_atos, erro = 0, ''
    try:
        chave = {}   # _k -> (ente, data, edicao, parte) = identificação da edição na base comum
        edicoes = []
        for m in manifesto:
            ed = (m['edicao'] or 's/n') + (' extra' if m['_extra'] else '')
            chave[m['_k']] = dict(ente=m['ente'], data=m['data'], edicao=ed, parte=m['sha256'][:12])
            edicoes.append(dict(chave[m['_k']], link=m['link'], sha256=m['sha256'], paginas=m['_paginas'],
                                id_fonte=m['link'], arquivo=m['_arquivo'], bytes=m['bytes']))
        sha = {m['_k']: m['sha256'] for m in manifesto}
        cnpjs = sorted({a['_cnpj'] for a in citados if a['_k'] in chave})
        receita = {}
        if cnpjs:
            try:
                r = cm.cnpj_pedir(cnpjs)
                log(f"base comum: {r.get('aceitos', 0)} CNPJ(s) pedidos ao robô da Receita"
                    + (f"; DV inválido: {r['dv_invalido']}" if r.get('dv_invalido') else ''))
                receita = cm.cnpj_consultar(cnpjs)
            except Exception as e:
                log(f'base comum: pedir/consultar CNPJ falhou ({type(e).__name__}: {str(e)[:200]})')
        atos = []
        for a in citados:
            if a['_k'] not in chave: continue
            rs = (receita.get(a['_cnpj']) or {}).get('razao_social') or base.get(a['_cnpj']) or None
            atos.append(dict(chave[a['_k']], orgao=f"PREFEITURA {a['ente'].upper()}",
                             tipo='cnpj_citado', cnpj=a['_cnpj'], razao_receita=rs, classe='INDICIO',
                             link=a['link'], pagina=a['_pag'], trecho=a['trecho'], papel=(f"perto de termo ambiental: {a['_papel']}" if a['_papel'] else None),
                             hash_ato=hash_ato('QUERIDO_DIARIO', sha[a['_k']], 'cnpj', a['_cnpj'], a['_pos'])))
        for a in pessoal:
            if a['_k'] not in chave: continue
            atos.append(dict(chave[a['_k']], orgao=f"PREFEITURA {a['ente'].upper()}",
                             tipo='pessoal', pessoa_nome=a['_nome'] or None, cargo=a['_cargo'] or None, acao=a['_acao'],
                             nivel='alto escalão' if a['_alto'] else None, classe='INDICIO', link=a['link'], pagina=a['_pag'],
                             trecho=a['trecho'], hash_ato=hash_ato('QUERIDO_DIARIO', sha[a['_k']], 'pessoal', a['_pos'])))
        for a in ambiental:
            if a['_k'] not in chave: continue
            atos.append(dict(chave[a['_k']], orgao=f"PREFEITURA {a['ente'].upper()}", tipo='ambiental', acao=a['_cat'],
                             cnpj=a['_cnpj'] or None, classe='INDICIO', link=a['link'], pagina=a['_pag'], trecho=a['trecho'],
                             papel='ato ambiental publicado (categoria por palavra-chave; ler o ato)',
                             hash_ato=hash_ato('QUERIDO_DIARIO', sha[a['_k']], 'ambiental', a['_cat'], a['_pos'])))
        n_ed, n_atos, n_rep = cm.gravar(edicoes, atos)
        log(f'base comum: {n_ed} edição(ões), {n_atos} ato(s) novo(s), {n_rep} repetido(s), {len(cm.rejeitados)} recusado(s) pelo banco')
        for r in cm.rejeitados[:10]: log(f'  recusado: {r}')
    except Exception as e:
        erro = f'{type(e).__name__}: {e}'; log(f'base comum: ERRO ao gravar ({erro[:300]})')
    cm.fim('falhou' if erro else 'ok', n_atos, erro)


def municipio_de(arq):
    n = os.path.basename(arq).replace('.jsonl', '').replace('rj_', '').replace('_v2', '').replace('_v3', '')
    n = re.sub(r'_(betha|api|seq|lista|gesdom|ajax|drive|dioenet|geosiap|nav|wp)$', '', n)   # sufixo do tipo de robô não entra no nome do município
    if n == 'aemerj': return 'AEMERJ (vários municípios)'
    if n == 'tribuna_dos_municipios': return 'Tribuna dos Municípios (jornal, vários municípios)'
    return n.replace('_', ' ').title().replace(' De ', ' de ').replace(' Do ', ' do ').replace(' Da ', ' da ').replace(' Dos ', ' dos ')


def main():
    pasta, saida = sys.argv[1], sys.argv[2]
    sem_sb = '--sem-supabase' in sys.argv
    os.makedirs(saida, exist_ok=True)
    hoje = dt.date.today()

    base = {}
    sb = None
    if not sem_sb and os.environ.get('SUPABASE_URL'):
        sb = Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
        for e in sb.todos('empresas', 'cnpj,razao_social'):
            base[re.sub(r'\D', '', e['cnpj'])] = e.get('razao_social') or ''
    log(f'{len(base)} empresas da base para procurar nos diários')

    edicoes = []
    for arq in sorted(glob.glob(os.path.join(pasta, '*.jsonl'))):
        mun = municipio_de(arq)
        for linha in open(arq, encoding='utf-8'):
            try: it = json.loads(linha)
            except Exception: continue
            for f in it.get('files') or []:
                edicoes.append(dict(municipio=mun, data=it.get('date'), edicao=it.get('edition_number') or '',
                                    extra=it.get('is_extra_edition'), url=f.get('url') or (it.get('file_urls') or [''])[0],
                                    caminho=f.get('path')))
    log(f'{len(edicoes)} edições baixadas')

    achados, resumo, t0, t_ocr = [], {}, time.time(), 0.0
    citados, pessoal, manifesto, aemerj, ambiental = [], [], [], {}, []
    raiz_arquivos = os.environ.get('FILES_STORE', 'data')
    for k, ed in enumerate(edicoes, 1):
        r = resumo.setdefault(ed['municipio'], dict(edicoes=0, com_texto=0, ocr=0, cnpj_base=0, termos=0))
        r['edicoes'] += 1
        pdf = os.path.join(raiz_arquivos, ed['caminho'] or '')
        txt = ''
        if ed['caminho'] and os.path.exists(pdf):
            seguir_link(pdf)
            try:
                txt = subprocess.run(['pdftotext', '-q', pdf, '-']   # sem -layout: -layout mistura colunas vizinhas (falso positivo em 09/11)
                                 , capture_output=True, timeout=120).stdout.decode('utf-8', 'ignore')
            except Exception: txt = ''
            if not txt.strip():
                if t_ocr / 60 < OCR_MAX_MIN:
                    t1 = time.time(); txt, lidas, tot = ocr(pdf); t_ocr += time.time() - t1
                    if txt.strip(): r['ocr'] += 1
                    log(f"OCR {ed['municipio']} {ed['data']}: {lidas} de {tot} página(s) lidas"
                        + (f' (limite de {OCR_MAX_PAG})' if tot > lidas else '') + f', {len(txt.strip())} caracteres')
                else:
                    log(f"OCR {ed['municipio']} {ed['data']}: pulado, limite de {OCR_MAX_MIN:.0f} min de OCR atingido")
        if txt.strip(): r['com_texto'] += 1
        cn = cnpjs_em(txt)
        if ed['caminho'] and os.path.exists(pdf):
            try:
                b = open(pdf, 'rb').read()
                manifesto.append(dict(data=ed['data'], fonte='DOM', ente=ed['municipio'], edicao=ed['edicao'], link=ed['url'],
                                      sha256=hashlib.sha256(b).hexdigest(), bytes=len(b), texto='sim' if txt.strip() else 'não',
                                      _k=k, _paginas=(paginas(pdf) or (txt.count('\f') + 1 if txt.strip() else None)),
                                      _extra=bool(ed.get('extra')), _arquivo=ed['caminho']))
            except Exception: pass
        for c in dict.fromkeys(c for c, _ in cn):
            i = next(i for cc, i in cn if cc == c)
            citados.append(dict(data=ed['data'], fonte='DOM', ente=ed['municipio'], cnpj=fmt(c), razao_receita=base.get(c, ''),
                                tipo='CNPJ citado', valor='', classe='INDÍCIO', link=ed['url'], trecho=mascara(trecho(txt, i)),
                                _k=k, _pag=txt.count('\f', 0, i) + 1, _cnpj=c, _pos=i,
                                _papel='; '.join(sorted({mm.group(0).lower() for mm in RX_TERMO.finditer(txt, max(0, i - JANELA), i + JANELA)}))))
        if ed['municipio'].startswith(('AEMERJ', 'Tribuna dos Munic')):   # quem publica no diário da AEMERJ (plano único: tirar da lista "sem robô")
            for m in re.finditer(r'(?:PREFEITURA|C[AÂ]MARA) MUNICIPAL DE ([A-ZÀ-Ú][A-ZÀ-Ú\- ]{2,40}?)(?=\s*(?:\n|[^A-ZÀ-Ú\- ]))', txt):
                aemerj[m.group(1).strip().title()] = aemerj.get(m.group(1).strip().title(), 0) + 1
        for m in RX_PESSOAL.finditer(txt):
            fim = RX_PESSOAL.search(txt, m.end()); fim = fim.start() if fim and fim.start() - m.start() < 400 else m.start() + 400
            t = mascara(re.sub(r'\s+', ' ', txt[m.start():fim]).strip())   # só o próprio ato (não pega o cargo do ato vizinho)
            pessoal.append(dict(data=ed['data'], fonte='DOM', ente=ed['municipio'], cnpj='', razao_receita='',
                                tipo=('ALTO ESCALÃO - ' if RX_ALTO.search(t) else '') + m.group(1).upper(), valor='', classe='INDÍCIO',
                                link=ed['url'], trecho=t, _k=k, _pag=txt.count('\f', 0, m.start()) + 1, _pos=m.start(),
                                _acao=m.group(1).upper(), _nome=nome_ato(t, m.group(1)), _cargo=cargo_ato(t), _alto=bool(RX_ALTO.search(t))))
        for cat, i in atos_ambientais(txt):
            perto = [c for c, j in cn if abs(j - i) <= JANELA]
            ambiental.append(dict(data=ed['data'], fonte='DOM', ente=ed['municipio'], cnpj=fmt(perto[0]) if perto else '', razao_receita='',
                                  tipo='AMBIENTAL - ' + cat, valor='', classe='INDÍCIO', link=ed['url'], trecho=mascara(trecho(txt, i, 400)),
                                  _k=k, _pag=txt.count('\f', 0, i) + 1, _pos=i, _cat=cat, _cnpj=perto[0] if perto else ''))
        # (a) CNPJ da nossa base citado no diário
        vistos = set()
        for c, i in cn:
            if c in base and c not in vistos:
                vistos.add(c); r['cnpj_base'] += 1
                achados.append(dict(tipo='CNPJ da base', cnpj=fmt(c), empresa=base[c], termo='', **{x: ed[x] for x in ('municipio', 'data', 'edicao', 'url')}, trecho=trecho(txt, i)))
        # (b) termos ambientais e CNPJs próximos
        for m in RX_TERMO.finditer(txt):
            r['termos'] += 1
            perto = [c for c, i in cn if abs(i - m.start()) <= JANELA]
            for c in dict.fromkeys(perto) or ['']:
                achados.append(dict(tipo='Termo ambiental' + (' + CNPJ' if c else ''), cnpj=fmt(c) if c else '', empresa=base.get(c, ''),
                                    termo=m.group(0), **{x: ed[x] for x in ('municipio', 'data', 'edicao', 'url')}, trecho=trecho(txt, m.start())))
        if k % 10 == 0 or k == len(edicoes):
            pct = k / len(edicoes) * 100; dec = time.time() - t0
            log(f'{pct:5.1f}% · {k}/{len(edicoes)} edições lidas · {dec/60:.1f} min · faltam ~{dec/k*(len(edicoes)-k)/60:.1f} min')

    # deduplica termos repetidos no mesmo trecho
    uniq, vis = [], set()
    for a in achados:
        ch = (a['tipo'], a['cnpj'], a['url'], a['trecho'][:80])
        if ch in vis: continue
        vis.add(ch); uniq.append(a)
    campos = ['tipo', 'municipio', 'data', 'edicao', 'cnpj', 'empresa', 'termo', 'trecho', 'url']
    with open(os.path.join(saida, 'achados_diarios_rj.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=';'); w.writeheader(); w.writerows(uniq)

    # formato comum do plano único (09/11/2026): data, fonte, ente, cnpj, razao_receita, tipo, valor, classe, link, trecho
    comum_cols = ['data', 'fonte', 'ente', 'cnpj', 'razao_receita', 'tipo', 'valor', 'classe', 'link', 'trecho']
    for nome, linhas_ in (('cnpjs_citados.csv', citados), ('nomeacoes_todas.csv', pessoal), ('atos_ambientais.csv', ambiental)):
        vis_ = set(); dd = []
        for a in linhas_:
            ch = (a['cnpj'], a['link'], a['tipo'], a['trecho'][:120])
            if ch not in vis_: vis_.add(ch); dd.append(a)
        with open(os.path.join(saida, nome), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=comum_cols, delimiter=';', extrasaction='ignore'); w.writeheader(); w.writerows(dd)
        log(f'{nome}: {len(dd)} linha(s)')
    with open(os.path.join(saida, 'manifesto.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['data', 'fonte', 'ente', 'edicao', 'link', 'sha256', 'bytes', 'texto'], delimiter=';', extrasaction='ignore')
        w.writeheader(); w.writerows(manifesto)
    gravar_comum(manifesto, citados, pessoal, base, ambiental)
    if aemerj: log('AEMERJ/Tribuna, entes que publicam: ' + ' · '.join(f'{k} ({v})' for k, v in sorted(aemerj.items(), key=lambda x: -x[1])[:60]))
    log(f"manifesto.csv: {len(manifesto)} edição(ões) com SHA-256; altos cargos: {sum(1 for a in pessoal if a['tipo'].startswith('ALTO'))}")

    # resumo em Markdown (vai para a página da execução no GitHub)
    linhas = ['# Diários oficiais municipais do RJ', '',
              f'Coleta em {hoje:%d/%m/%Y}. Fonte: sites das prefeituras, lidos com os raspadores abertos do Querido Diário (MIT). '
              'Tudo aqui é **INDÍCIO**: menção em diário não é condenação nem prova de irregularidade; leia o ato.', '',
              '| Município | Edições | Com texto | Por OCR | CNPJ da base | Termos ambientais |', '|---|---:|---:|---:|---:|---:|']
    for mun, r in sorted(resumo.items()):
        linhas.append(f"| {mun} | {r['edicoes']} | {r['com_texto']} | {r['ocr']} | {r['cnpj_base']} | {r['termos']} |")
    base_hits = [a for a in uniq if a['tipo'] == 'CNPJ da base']
    perto = [a for a in uniq if a['tipo'] == 'Termo ambiental + CNPJ']
    linhas += ['', f'**Empresas da base citadas:** {len(base_hits)} · **CNPJs perto de termo ambiental:** {len(perto)} · '
               f'**Trechos com termo ambiental:** {sum(1 for a in uniq if a["tipo"].startswith("Termo"))}', '']
    for a in (base_hits + perto)[:40]:
        linhas.append(f"- {a['municipio']} {a['data']} · {a['tipo']} · {a['cnpj']} {a['empresa']} · “{a['trecho'][:160]}…” · [PDF]({a['url']})")
    open(os.path.join(saida, 'resumo.md'), 'w', encoding='utf-8').write('\n'.join(linhas) + '\n')

    gravadas = 0
    # (a) vai para o banco como INDÍCIO (chave igual à da base do Radar: DOM|cnpj|data|link)
    if sb and base_hits:
        occ = [dict(chave=f"DOM|{a['cnpj']}|{a['data']}|{a['url']}", fonte='Diário Oficial Municipal (raspadores Querido Diário)',
                    orgao=f"PREFEITURA {a['municipio'].upper()}", tipo_documento='MENCAO NO DOM', numero=str(a['edicao']), processo='',
                    data_documento=a['data'], situacao='INDICIO - ler o ato', cnpj=a['cnpj'], nome=a['empresa'], municipio=a['municipio'],
                    descricao=a['trecho'], nivel='INDICIO', link_fonte=a['url'], ultima_coleta=hoje.isoformat(), origem='coletor-diarios')
               for a in base_hits]
        sb.upsert('ocorrencias', occ, 'chave'); gravadas += len(occ)
        log(f'{len(occ)} menção(ões) de empresa da base gravada(s) como INDÍCIO')

    # (b) CNPJ perto de termo ambiental (fora da base): possível cliente novo, com razão social conferida na Receita
    novos = {}
    for a in perto:
        if a['empresa']: continue                                  # já está na base: entrou em (a)
        if not RX_LEAD.search(a['termo']): continue                # só citou secretaria/INEA: não é indício sobre a empresa
        g = novos.setdefault((a['cnpj'], a['url']), dict(a, termos=set(), trechos=[]))
        g['termos'].add(a['termo'].lower()); g['trechos'].append(a['trecho'])
    if sb and novos:
        ja = {o['chave'] for o in sb.todos('ocorrencias', 'chave') if o['chave'].startswith('DOMT|')}
        cad, consultas, occ, publicos = {}, 0, [], 0
        for (c, url), g in novos.items():
            chave = f"DOMT|{c}|{g['data']}|{url}"
            if chave in ja: continue
            if c not in cad and consultas < CAD_MAX:
                consultas += 1; cad[c] = cadastro(c); time.sleep(1)
            r = cad.get(c)
            nat = re.sub(r'\D', '', str((r or {}).get('cod_nat') or ''))
            # natureza 1xxx = administração pública (fundo, prefeitura...); 2011 = empresa pública (ex.: Imprensa da Cidade,
            # cujo CNPJ sai no rodapé do D.O. Rio; falso positivo em 09/11). Sociedade de economia mista (2038) continua.
            if r and (nat.startswith('1') or nat == '2011'):
                publicos += 1; continue
            nome = mascara(r['razao_social']) if r else ''
            trechos = ' […] '.join(dict.fromkeys(g['trechos']))[:1500]
            # o nome da Receita precisa aparecer no trecho; se não aparece, pode ser CNPJ de outra parte citada no ato
            primeira = sem_acento(re.sub(r'[^A-Za-z0-9À-ú ]', ' ', nome)).split()[:1]
            confere = bool(primeira) and primeira[0] in sem_acento(trechos)
            occ.append(dict(chave=chave, fonte='Diário Oficial Municipal (raspadores Querido Diário)',
                            orgao=f"PREFEITURA {g['municipio'].upper()}", tipo_documento='TERMO AMBIENTAL NO DOM', numero=str(g['edicao']), processo='',
                            data_documento=g['data'], situacao='INDICIO - ler o ato', cnpj=c, nome=nome,
                            municipio=g['municipio'], assunto=', '.join(sorted(g['termos'])),
                            descricao=(f"Razão social: {r['fonte_cadastro']}. " if r else 'Razão social não conferida (Receita indisponível). ')
                                      + ('' if confere else 'ATENÇÃO: o nome da Receita não aparece no trecho; o CNPJ pode ser de outra parte do ato. ')
                                      + trechos,
                            nivel='INDICIO', link_fonte=url, ultima_coleta=hoje.isoformat(), origem='coletor-diarios'))
        if occ:
            sb.upsert('ocorrencias', occ, 'chave'); gravadas += len(occ)
        log(f'{len(occ)} CNPJ(s) novo(s) perto de termo ambiental gravado(s) como INDÍCIO ({consultas} consulta(s) à Receita; {publicos} órgão(s) público(s) fora)')

    # registro da execução (a coleta do IBAMA só olha as linhas da fonte IBAMA)
    if sb:
        sem_txt = [m for m, r in resumo.items() if r['edicoes'] and not r['com_texto']]
        sb.req('POST', '/coletas', dict(
            fonte='Diários oficiais municipais do RJ (raspadores abertos do Querido Diário, sites das prefeituras)',
            metodo=f'janela: {os.environ.get("DIAS", "?")}; pdftotext e OCR (tesseract por, até {OCR_MAX_PAG} pág./edição); CNPJ com DV válido; CPF mascarado; tudo INDÍCIO',
            status='ok', iniciada_em=dt.datetime.fromtimestamp(t0, dt.timezone.utc).isoformat(),
            terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(), autos_lidos=len(edicoes), autos_novos=gravadas,
            mensagem=(f'{len(edicoes)} edições de {sum(1 for r in resumo.values() if r["edicoes"])} município(s); '
                      f'{len(base_hits)} menção(ões) da base; {len(novos)} CNPJ(s) perto de termo ambiental; {gravadas} gravado(s) agora'
                      + (f'; sem texto mesmo com OCR: {", ".join(sorted(sem_txt))}' if sem_txt else ''))[:900]),
            {'Prefer': 'return=minimal'})
    log(f'FIM: {len(edicoes)} edições, {len(uniq)} achados (CSV e resumo em {saida})')
    print('\a')


if __name__ == '__main__':
    main()
