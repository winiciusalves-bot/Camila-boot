"""Coletor diário da Ambiental Costa (roda no GitHub Actions; só biblioteca padrão do Python).

Fonte: IBAMA Dados Abertos, Fiscalização: Auto de Infração (auto_infracao_csv.zip).
Cadastro: base pública do CNPJ (BrasilAPI; reservas: minhareceita.org e publica.cnpj.ws).
Destino: Supabase (tabelas empresas, autos e coletas).

Regras: só UF = RJ, últimos 365 dias e pessoa jurídica com DV do CNPJ válido; CPF
mascarado em todo texto (inclusive nome de MEI e de sócios); sócios só com nome e qualificação; valor do
auto não é dano nem condenação; nada de captcha, login ou bloqueio contornado.

Uso local de teste:  python coletar.py --csv arquivo.csv --sem-supabase --sem-cadastro
Variáveis no Actions: SUPABASE_URL e SUPABASE_SERVICE_KEY (em Secrets, nunca no código).
"""
import argparse, csv, datetime as dt, io, json, os, re, sys, tempfile, time, unicodedata, urllib.request, urllib.error, zipfile
import importlib.util as _ilu   # coletor/chance.py (o workflow roda com python -I, que não põe a pasta do script no sys.path)
_sp = _ilu.spec_from_file_location('chance', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chance.py'))
_ch = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ch); chance_licenciamento = _ch.chance
csv.field_size_limit(2**31 - 1)   # descrições muito longas em alguns CSVs do IBAMA

FONTE_URL = 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/SIFISC/auto_infracao/auto_infracao/auto_infracao_csv.zip'
FONTE_NOME = 'IBAMA Dados Abertos - Fiscalização: Auto de Infração (auto_infracao_csv.zip)'
UA = 'AmbientalCosta-Coletor/1.0 (dados abertos)'
INICIO = time.time()

# Nomes possíveis de cada coluna no CSV do IBAMA (o primeiro que existir é usado).
COLS = {
    'data':      ['DAT_HORA_AUTO_INFRACAO', 'DT_AUTO_INFRACAO', 'DATA_AUTO', 'DAT_AUTO_INFRACAO'],
    'uf':        ['UF', 'SG_UF', 'UF_AUTO'],
    'municipio': ['MUNICIPIO', 'NOME_MUNICIPIO', 'NO_MUNICIPIO', 'MUNICIPIO_AUTO'],
    'nome':      ['NOME_INFRATOR', 'NO_INFRATOR', 'NOME_AUTUADO'],
    'doc':       ['CPF_CNPJ_INFRATOR', 'NU_CPF_CNPJ_INFRATOR', 'CPF_CNPJ', 'CPFCNPJ_INFRATOR'],
    'n_auto':    ['NUM_AUTO_INFRACAO', 'NU_AUTO_INFRACAO', 'COD_AUTO_INFRACAO'],
    'processo':  ['NU_PROCESSO_FORMATADO', 'NUM_PROCESSO', 'NU_PROCESSO', 'PROCESSO'],
    'valor':     ['VAL_AUTO_INFRACAO', 'VALOR_AUTO', 'VL_AUTO_INFRACAO'],
    'tipo':      ['TIPO_INFRACAO', 'DES_TIPO_INFRACAO', 'TP_INFRACAO'],
    'descricao': ['DES_AUTO_INFRACAO', 'DESCRICAO', 'DS_AUTO_INFRACAO'],
    'gravidade': ['GRAVIDADE_INFRACAO', 'DES_GRAVIDADE', 'GRAVIDADE'],
    'cancelado': ['SIT_CANCELADO', 'CANCELADO', 'ST_CANCELADO'],
    'situacao':  ['DES_STATUS_FORMULARIO', 'STATUS_FORMULARIO', 'SITUACAO_FORMULARIO'],
    'sit_aie':   ['DS_SIT_AUTO_AIE'],
    'tp_pessoa': ['TP_PESSOA_INFRATOR'],
    'cod_mun':   ['COD_MUNICIPIO'],
    'ciencia':   ['DAT_CIENCIA_AUTUACAO'],
    'serie':     ['SER_AUTO_INFRACAO'],
    'seq':       ['SEQ_AUTO_INFRACAO'],
}
LINK_AUTOS = 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao'
LINK_EMB = 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-termo-de-embargo'
FONTE_OC = 'IBAMA Dados Abertos'

def ocorrencia(**k):
    """Linha da base única (mesmas colunas do ocorrencias_pj.csv da v5.1)."""
    base = dict(chave=None, fonte=FONTE_OC, orgao='IBAMA', tipo_documento=None, numero='', processo='', data_documento=None,
                data_documento_status='', data_ciencia=None, prazo_defesa_fim_estimado=None, prazo_defesa_status='',
                situacao='', cnpj=None, nome='', municipio='', cod_ibge='', valor_indicado_rs_nao_e_dano=None,
                assunto='', descricao='', nivel='FATO', link_fonte='', ultima_coleta=None, origem='coletor-online')
    base.update(k); return base
# Colunas do termo de embargo (conferidas na v5 do Radar-Ambiental, 06/11/2026)
EMB_URL = 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/TERMOS_DE_EMBARGO/TERMO_EMBARGO/termo_de_embargo.csv'
EMB_COLS = {'data': ['DAT_EMBARGO'], 'doc': ['CPF_CNPJ_EMBARGADO'], 'num': ['NUM_TAD'], 'uf': ['UF'],
            'cancelado': ['SIT_CANCELADO'], 'status': ['DES_STATUS_FORMULARIO'], 'desemb': ['SIT_DESEMBARGO'],
            'dt_desemb': ['DAT_DESEMBARGO'], 'tipo_area': ['TIPO_AREA'], 'municipio': ['MUNICIPIO'], 'cod_mun': ['COD_MUNICIPIO'],
            'seq': ['SEQ_TAD'], 'ser': ['SER_TAD'], 'proc': ['NUM_PROCESSO'], 'desc': ['DES_TAD'], 'nome': ['NOME_EMBARGADO']}
OBRIGATORIAS = ['data', 'uf', 'doc', 'n_auto']


def log(msg, pct=None):
    dec = time.time() - INICIO
    extra = ''
    if pct is not None and pct > 0:
        resta = dec / pct * (100 - pct)
        extra = f' | {pct:5.1f}% | previsão de término em {resta/60:.1f} min'
    print(f'[{dec/60:5.1f} min]{extra} {msg}', flush=True)


# ---------- validações ----------
def dv_cnpj(c):
    c = re.sub(r'\D', '', c or '')
    if len(c) != 14 or len(set(c)) == 1: return False
    def d(b, p):
        r = sum(int(x) * y for x, y in zip(b, p)) % 11
        return '0' if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return c[12] == d(c[:12], p1) and c[13] == d(c[:13], [6] + p1)

def dv_cpf(c):
    c = [int(x) for x in c]
    if len(set(c)) == 1: return False
    for n in (9, 10):
        if (sum(c[i] * (n + 1 - i) for i in range(n)) * 10) % 11 % 10 != c[n]: return False
    return True

CPF_RE = re.compile(r'(?<![\d./-])(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-.\s]?(\d{2})(?!\d|[./-]\d)')   # pega também CPF no fim de frase e com ponto no lugar do traço (123.456.789.01, visto em Tanguá 10/11/2026)
CPF_ROTULO = re.compile(r'(C\.?\s?P\.?\s?F\.?\s*(?:/MF)?\s*(?:n[ºo°.]*)?\s*[:-]?\s*)[\d.\s/-]{9,16}\d', re.I)   # depois de "CPF", mascara sempre (mesmo com dígito errado)
def mascara(t):
    t = CPF_ROTULO.sub(lambda m: m.group(1) + '[CPF omitido]', t or '')
    return CPF_RE.sub(lambda m: '[CPF omitido]' if dv_cpf(''.join(m.groups())) else m.group(0), t).strip()

def fmt_cnpj(c):
    c = re.sub(r'\D', '', c); return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}'

def sem_acento(s):
    return unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().upper()

PALAVRAS_VAZIAS = {'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'CIA', 'COMPANHIA', 'DE', 'DA', 'DO', 'DAS', 'DOS', 'E', 'EM',
                   'LIMITADA', 'SOCIEDADE', 'EMPRESA', 'EMPRESARIA', 'MEI', 'SPE'}
def tokens(s):
    s = sem_acento(s).replace('S/A', ' ')
    return {w for w in re.split(r'[^A-Z0-9]+', s) if len(w) >= 3 and w not in PALAVRAS_VAZIAS}

def semelhanca(a, b):
    """Regra v5: tokens em comum / tamanho do menor conjunto (0 se algum vazio)."""
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0

def nomes_divergem(nome_doc, razao, fantasia=''):
    """INDÍCIO, não fato: semelhança < 0,5 com a razão social E com o nome fantasia."""
    if not nome_doc: return False
    return max(semelhanca(nome_doc, razao), semelhanca(nome_doc, fantasia or '')) < 0.5

def data_iso(v):
    v = (v or '').strip()
    for f in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try: return dt.datetime.strptime(v[:len(dt.datetime.now().strftime(f))], f).date()
        except ValueError: pass
    try: return dt.date.fromisoformat(v[:10])
    except ValueError: return None

def valor(v):
    v = (v or '').strip()
    if not v: return None
    if ',' in v: v = v.replace('.', '').replace(',', '.')
    try: return float(v)
    except ValueError: return None


# ---------- leitura do IBAMA ----------
def baixar(url, destino, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=120) as r, open(destino, 'wb') as f:
                total = int(r.headers.get('Content-Length') or 0); lido = 0; ult = 0
                while True:
                    b = r.read(1 << 20)
                    if not b: break
                    f.write(b); lido += len(b)
                    if total and lido / total * 100 - ult >= 10:
                        ult = lido / total * 100; log(f'baixando {lido/1e6:.0f} de {total/1e6:.0f} MB', ult * 0.4)
            return
        except Exception as e:
            log(f'falha no download ({e}); tentativa {i+1} de {tentativas}')
            time.sleep(2 ** (i + 1))
    raise RuntimeError('Não foi possível baixar o arquivo do IBAMA')

def abrir_csv(binario):
    amostra = binario[:200000]
    enc = 'cp1252'                          # anos antigos vêm em Windows-1252
    try: binario.decode('utf-8-sig'); enc = 'utf-8-sig'
    except UnicodeDecodeError: pass
    texto = binario.decode(enc, errors='replace')
    sep = ';' if texto[:5000].count(';') >= texto[:5000].count(',') else ','
    return csv.DictReader(io.StringIO(texto), delimiter=sep)

def mapear(cabecalho, cols=None, obrig=None):
    cols, obrig = cols or COLS, obrig or OBRIGATORIAS
    cab = {c.strip().strip('\ufeff').upper(): c for c in cabecalho if c}
    m = {k: next((cab[n] for n in nomes if n in cab), None) for k, nomes in cols.items()}
    faltam = [k for k in obrig if not m[k]]
    if faltam:
        raise RuntimeError(f'Colunas obrigatórias não encontradas: {faltam}. Cabeçalho do IBAMA: {list(cab)}')
    return m

def ler_autos(arquivos, hoje):
    corte = hoje - dt.timedelta(days=365)
    autos, lidos, nome_mun, occ = {}, 0, {}, {}
    for i, (nome, binario) in enumerate(arquivos):
        leitor = abrir_csv(binario)
        m = mapear(leitor.fieldnames or [])
        g = lambda row, k: (row.get(m[k]) or '').strip() if m[k] else ''
        for row in leitor:
            lidos += 1
            if g(row, 'uf').upper() != 'RJ': continue
            if g(row, 'tp_pessoa').upper() == 'PF': continue
            d = data_iso(g(row, 'data'))
            if not d or d < corte or d > hoje: continue
            doc = re.sub(r'\D', '', g(row, 'doc'))
            if len(doc) != 14 or not dv_cnpj(doc): continue       # só PJ com DV válido
            st = sem_acento(g(row, 'sit_aie') + ' ' + g(row, 'situacao'))
            canc = g(row, 'cancelado').upper() in ('S', 'SIM') or 'EXCLU' in st or 'CANCEL' in st
            cod = g(row, 'cod_mun')
            mun = nome_mun.setdefault(cod, g(row, 'municipio').title()) if cod else g(row, 'municipio').title()
            ci = data_iso(g(row, 'ciencia'))
            n_auto = g(row, 'n_auto')
            if not n_auto: continue
            autos[n_auto] = dict(
                n_auto=n_auto, cnpj=fmt_cnpj(doc), data_auto=d.isoformat(),
                municipio=mun, nome_no_auto=mascara(g(row, 'nome')),
                processo=g(row, 'processo'), valor_auto=valor(g(row, 'valor')),
                tipo_infracao=g(row, 'tipo'), descricao=mascara(g(row, 'descricao')),
                gravidade=g(row, 'gravidade'), cancelado=canc,
                situacao_formulario=' / '.join(filter(None, [g(row, 'sit_aie'), g(row, 'situacao')])),
                data_ciencia=ci.isoformat() if ci else None,
                prazo_defesa_estimado=(ci + dt.timedelta(days=20)).isoformat() if ci else None,
                data_coleta=hoje.isoformat())
            ser = g(row, 'serie'); prazo = (ci + dt.timedelta(days=20)) if ci else None
            ch = 'IBAMA-AUTO|' + (f'{n_auto}/{ser}' if n_auto else g(row, 'seq'))
            occ[ch] = ocorrencia(chave=ch, tipo_documento='AUTO DE INFRACAO', numero=f'{n_auto} {ser}'.strip(),
                processo=g(row, 'processo'), data_documento=d.isoformat(), data_ciencia=ci.isoformat() if ci else None,
                prazo_defesa_fim_estimado=prazo.isoformat() if prazo else None,
                prazo_defesa_status=('' if not prazo else 'ABERTO (estimado)' if prazo >= hoje else 'ENCERRADO (estimado)'),
                situacao='CANCELADO/EXCLUIDO' if canc else 'VALIDO', cnpj=fmt_cnpj(doc), nome=mascara(g(row, 'nome')),
                municipio=mun, cod_ibge=cod, valor_indicado_rs_nao_e_dano=valor(g(row, 'valor')), assunto=g(row, 'tipo'),
                descricao=mascara(g(row, 'descricao'))[:400], link_fonte=LINK_AUTOS, ultima_coleta=hoje.isoformat())
        log(f'{nome}: lido', 40 + 20 * (i + 1) / len(arquivos))
    return list(autos.values()), lidos, list(occ.values())

def ler_embargos(binario, hoje):
    leitor = abrir_csv(binario)
    m = mapear(leitor.fieldnames or [], EMB_COLS, ['data', 'doc', 'num', 'uf'])
    g = lambda row, k: (row.get(m[k]) or '').strip() if m[k] else ''
    out, occ = {}, {}
    for row in leitor:
        if g(row, 'uf').upper() != 'RJ': continue
        doc = re.sub(r'\D', '', g(row, 'doc'))
        if len(doc) != 14 or not dv_cnpj(doc): continue
        st = sem_acento(g(row, 'status'))
        d = data_iso(g(row, 'data')); dd = data_iso(g(row, 'dt_desemb'))
        if g(row, 'cancelado').upper() == 'S' or 'CANCEL' in st or 'EXCLU' in st: status = 'CANCELADO'
        elif g(row, 'desemb').upper() == 'S' or dd: status = 'DESEMBARGADO'
        else: status = 'VIGENTE'
        num = g(row, 'num')
        if not num: continue
        out[num] = dict(num_tad=num, cnpj=fmt_cnpj(doc), data_embargo=d.isoformat() if d else None,
                        municipio=g(row, 'municipio').title(), tipo_area=g(row, 'tipo_area'), status=status,
                        data_desembargo=dd.isoformat() if dd else None, data_coleta=hoje.isoformat())
        ch = 'IBAMA-EMB|' + (g(row, 'seq') or f"{num}-{g(row, 'ser')}")
        occ[ch] = ocorrencia(chave=ch, tipo_documento='TERMO DE EMBARGO', numero=f"{num} {g(row, 'ser')}".strip(),
            processo=g(row, 'proc'), data_documento=d.isoformat() if d else None, situacao=status, cnpj=fmt_cnpj(doc),
            nome=mascara(g(row, 'nome')), municipio=g(row, 'municipio').title(), cod_ibge=g(row, 'cod_mun'),
            assunto=g(row, 'tipo_area'), descricao=mascara(g(row, 'desc'))[:400], link_fonte=LINK_EMB, ultima_coleta=hoje.isoformat())
    return list(out.values()), list(occ.values())


OUTRAS_FONTES = {   # chave: (prefixo da chave, tipo_documento, URL)
    'notificacao': ('IBAMA-NOT', 'NOTIFICACAO', 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/FISCALIZACAO_NOTIFICACAO/fiscalizacao_notificacao.csv'),
    'suspensao':   ('IBAMA-SUS', 'TERMO DE SUSPENSAO', 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/TERMOS/TERMO_SUSPENSAO/termo_de_suspensao.csv'),
    # URLs e colunas conferidas no c6 da v5.1 (Dell, 06/11/2026)
    'demolicao':   ('IBAMA-DEM', 'TERMO DE DEMOLICAO', 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/TERMOS/TERMO_DEMOLICAO/termo_de_demolicao.csv'),
    'apreensao':   ('IBAMA-APR', 'TERMO DE APREENSAO', 'https://dadosabertos.ibama.gov.br/dados/SIFISC/termo_apreensao/apreensao/apreensao_csv.zip'),
}
JANELA_DIAS = {'IBAMA-DEM': 3650}   # demolição pontua sem limite de tempo; guardamos 10 anos. As demais: 12 meses.
def ler_outros(binario, hoje, prefixo, tipo, link):
    """Notificações / termos de suspensão: colunas detectadas por padrão (regra da opção 8 / c10 da v5.1).
    Devolve ocorrências de PJ no RJ dentro da janela (canceladas marcadas como tal). Aceita CSV ou ZIP com CSV."""
    if binario[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(binario)) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith('.csv')]
            if not nomes: raise RuntimeError('zip sem CSV')
            binario = z.read(nomes[0])
    leitor = abrir_csv(binario)
    cab = [c for c in (leitor.fieldnames or []) if c]
    up = {c: c.strip().strip('\ufeff').upper() for c in cab}
    achar = lambda pads, excl=None: next((c for p in pads for c in cab if re.search(p, up[c]) and not (excl and re.search(excl, up[c]))), None)
    c_uf = achar([r'^UF$', r'^SIG_UF$', r'^SG_UF$']); c_doc = achar([r'CPF_CNPJ', r'CNPJ', r'CPF'])
    c_dt = achar([r'^DAT_NOTIFICACAO', r'^DT_NOTIFICACAO', r'^DAT_TAD$', r'^DT_APREENSAO$', r'^DAT_TERMO', r'^DAT_SUSPENSAO', r'^DAT_LAVRATURA', r'^DAT_EMISSAO', r'^DAT_HORA', r'^DAT_', r'^DT_'])
    c_can = achar([r'^SIT_CANCELADO$', r'^ST_CANCELADO$']); c_st = achar([r'STATUS', r'^DS_SIT', r'SITUACAO'])
    c_seq = achar([r'^SEQ_TAD$', r'^SEQ_NOTIFICACAO$', r'^FID$']); c_num = achar([r'^NUM_TAD$', r'^CD_TAD$', r'^NUM_NOTIFICACAO$'])
    c_ser = achar([r'^SER_TAD$', r'^CD_SERIE_TAD$', r'^SER_NOTIFICACAO$']); c_proc = achar([r'^(NUM|NU)_PROCESSO'])
    c_nome = achar([r'^(NOME|NOM_|NO_PESSOA)'], r'MUNIC|IMOVEL|FANTASIA'); c_des = achar([r'^DES_TAD$', r'^DS_TAD$', r'^DES_', r'^DS_'], r'STATUS|LOCAL|JUSTIF|ENQUADR|AUTO_INFRACAO')
    c_mun = achar([r'^MUNICIPIO$', r'^NOM_MUNICIPIO', r'^NO_MUNICIPIO$', r'MUNICIPIO'], r'^(CD|COD)_'); c_cod = achar([r'^COD_MUNICIPIO$', r'^CD_MUNICIPIO$'])
    log(f'{tipo}: colunas detectadas UF={c_uf} doc={c_doc} data={c_dt} seq={c_seq} num={c_num} cancelado={c_can} status={c_st}')
    if not (c_uf and c_doc and c_dt): raise RuntimeError(f'colunas não reconhecidas: {cab}')
    g = lambda row, c: (row.get(c) or '').strip() if c else ''
    corte, out = hoje - dt.timedelta(days=JANELA_DIAS.get(prefixo, 365)), {}
    for row in leitor:
        if g(row, c_uf).upper() != 'RJ': continue
        doc = re.sub(r'\D', '', g(row, c_doc))
        if len(doc) != 14 or not dv_cnpj(doc): continue
        d = data_iso(g(row, c_dt))
        if not d or d < corte or d > hoje: continue
        st = sem_acento(g(row, c_st))
        canc = g(row, c_can).upper() == 'S' or 'CANCEL' in st or 'EXCLU' in st
        idd = g(row, c_seq) or g(row, c_num) or f'{doc}|{d.isoformat()}'
        ch = f'{prefixo}|{idd}'
        out[ch] = ocorrencia(chave=ch, tipo_documento=tipo, numero=f'{g(row, c_num)} {g(row, c_ser)}'.strip(),
            processo=g(row, c_proc), data_documento=d.isoformat(), situacao='CANCELADO/EXCLUIDO' if canc else 'VALIDO',
            cnpj=fmt_cnpj(doc), nome=mascara(g(row, c_nome)), municipio=g(row, c_mun).title(), cod_ibge=g(row, c_cod),
            descricao=mascara(g(row, c_des))[:400], link_fonte=link, ultima_coleta=hoje.isoformat())
    return list(out.values())


INVALIDAS = ('CANCELADO', 'EXCLUIDO', 'DESEMBARGADO')
def pontuar_occ(e, occs, hoje, status_contato, excluidas):
    """Pontuação 0-100 (regra v5.1 do Radar-Ambiental), sobre a base única de ocorrências de TODAS as fontes.
    Indica prioridade de contato; NÃO indica culpa nem dano. INDÍCIOS (menções em diário) não pontuam."""
    fatos = [o for o in occs if (o.get('nivel') or 'FATO') == 'FATO']
    val = [o for o in fatos if not any(t in sem_acento(o.get('situacao') or '') for t in INVALIDAS) and o.get('data_documento')]
    dias = lambda o: (hoje - dt.date.fromisoformat(str(o['data_documento'])[:10])).days
    tipo = lambda o: sem_acento(o.get('tipo_documento') or '')
    pts, mot = 0, []
    if val:
        dmin = min(dias(o) for o in val)
        p = 25 if dmin <= 30 else 18 if dmin <= 90 else 10 if dmin <= 180 else 5 if dmin <= 365 else 0
        if p: pts += p; mot.append(f'documento mais recente há {dmin} dias (+{p})')
    autos = [o for o in val if 'AUTO DE INFRACAO' in tipo(o)]
    prazos = sorted(str(o['prazo_defesa_fim_estimado'])[:10] for o in autos if o.get('prazo_defesa_fim_estimado') and str(o['prazo_defesa_fim_estimado'])[:10] >= hoje.isoformat())
    if prazos: pts += 15; mot.append(f'prazo de defesa estimado até {prazos[0]} (+15)')
    elif any(not o.get('data_ciencia') and dias(o) <= 45 for o in autos): pts += 8; mot.append('auto recente sem ciência registrada (+8)')
    vig = [o for o in fatos if 'EMBARGO' in tipo(o) and sem_acento(o.get('situacao') or '') == 'VIGENTE']
    if any(o.get('data_documento') and dias(o) <= 365 for o in vig): pts += 20; mot.append('embargo vigente lavrado em 12 meses (+20)')
    elif vig: pts += 8; mot.append('embargo vigente antigo (+8)')
    def tem(pal, prazo_d, p, txt):
        nonlocal pts
        if any(pal in tipo(o) and dias(o) <= prazo_d for o in val): pts += p; mot.append(f'{txt} (+{p})')
    tem('SUSPENSAO', 365, 15, 'termo de suspensão em 12 meses')
    tem('NOTIFICACAO', 365, 8, 'notificação em 12 meses')
    tem('DEMOLICAO', 99999, 15, 'termo de demolição')
    tem('APREENSAO', 365, 10, 'termo de apreensão em 12 meses')
    tem('ACIDENTE', 730, 10, 'acidente ambiental em 24 meses')
    # notificação do Diário Eletrônico do INEA não é penalidade: pontua só como notificação (+8, acima)
    inea = [o for o in val if sem_acento(o.get('orgao') or '') == 'INEA' and 'NOTIFICACAO' not in tipo(o)]
    if any(dias(o) <= 365 for o in inea): pts += 15; mot.append('penalidade do INEA em 12 meses (+15)')
    elif inea: pts += 5; mot.append('penalidade do INEA antiga (+5)')
    if any('LICENCA' in tipo(o) for o in fatos): pts += 3; mot.append('licença federal registrada (+3)')
    n = len(val)
    if n >= 4: pts += 10; mot.append(f'{n} documentos (+10)')
    elif n >= 2: pts += 5; mot.append(f'{n} documentos (+5)')
    v = sum(float(o.get('valor_indicado_rs_nao_e_dano') or 0) for o in autos)
    p = 15 if v >= 1e6 else 10 if v >= 1e5 else 5 if v >= 1e4 else 2 if v > 0 else 0
    if p: pts += p; mot.append(f'valor indicado nos autos (não é dano) R$ {v:,.0f} (+{p})'.replace(',', '.'))
    porte = sem_acento(e.get('porte') or '')
    p = 5 if 'DEMAIS' in porte else 4 if 'PEQUENO' in porte or porte == 'EPP' else 2 if 'MICRO' in porte or porte == 'ME' else 0
    if p: pts += p; mot.append(f'porte {e.get("porte")} (+{p})')
    if e.get('telefone') or e.get('email'): pts += 5; mot.append('tem contato cadastral (+5)')
    pts = min(pts, 100)
    pri = 'A' if pts >= 55 else 'B' if pts >= 35 else 'C'
    nat = sem_acento(e.get('natureza_juridica') or '')
    if (e.get('situacao_receita') or '') != 'ATIVA': pri = 'X'; mot.insert(0, 'descartada: não está ATIVA na Receita')
    elif str(e.get('natureza_codigo') or '').startswith('1') or any(t in nat for t in ('ORGAO PUBLICO', 'AUTARQUIA', 'FUNDACAO PUBLICA', 'MUNICIPIO', 'ESTADO', 'UNIAO')):
        pri = 'X'; mot.insert(0, 'descartada: órgão público')
    elif re.sub(r'\D', '', e['cnpj'])[:8] in excluidas: pri = 'X'; mot.insert(0, 'descartada: lista de exclusão')
    elif status_contato in ('nao_contatar', 'sem_interesse', 'cliente'): pri = 'X'; mot.insert(0, f'descartada: status {status_contato}')
    if e.get('nome_divergente') and pri != 'X': pri += ' (conferir nome)'
    return dict(pontos=pts, prioridade=pri, motivos='; '.join(mot), embargos_vigentes=len(vig),
                prazo_defesa_ate=prazos[0] if prazos else None)


def arquivos_do_zip(caminho, ano_min=None):
    """CSVs do zip. Com ano_min, pula os arquivos anuais antigos (auto_infracao_1999.csv etc.): a janela é de 365 dias."""
    with zipfile.ZipFile(caminho) as z:
        for n in z.namelist():
            if not n.lower().endswith('.csv'): continue
            m = re.search(r'(19|20)\d{2}', os.path.basename(n))
            if ano_min and m and int(m.group(0)) < ano_min: continue
            yield n, z.read(n)


# ---------- cadastro do CNPJ (fontes públicas, com reservas) ----------
def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

def cadastro(cnpj):
    c = re.sub(r'\D', '', cnpj)
    fontes = [
        ('minhareceita.org', f'https://minhareceita.org/{c}'),      # 1ª: traz e-mail
        ('BrasilAPI', f'https://brasilapi.com.br/api/cnpj/v1/{c}'),
        ('publica.cnpj.ws', f'https://publica.cnpj.ws/cnpj/{c}'),
    ]
    for nome, url in fontes:
        try:
            j = get_json(url)
        except Exception:
            time.sleep(1); continue
        if nome == 'publica.cnpj.ws':
            est = j.get('estabelecimento') or {}
            nat = (j.get('natureza_juridica') or {}).get('descricao', '')
            tel = ' / '.join(f"{est.get(f'ddd{i}') or ''}{est.get(f'telefone{i}') or ''}" for i in (1, 2) if est.get(f'telefone{i}'))
            r = dict(razao_social=j.get('razao_social'), nome_fantasia=est.get('nome_fantasia'),
                     situacao_receita=(est.get('situacao_cadastral') or '').upper(), natureza_juridica=nat,
                     atividade=(est.get('atividade_principal') or {}).get('descricao'),
                     municipio_sede=f"{(est.get('cidade') or {}).get('nome', '')}/{(est.get('estado') or {}).get('sigla', '')}",
                     telefone=tel, email=est.get('email') or '', mei=bool((j.get('simples') or {}).get('mei') == 'Sim'),
                     porte=(j.get('porte') or {}).get('descricao'),
                     socios=[(x.get('nome'), (x.get('qualificacao_socio') or {}).get('descricao')) for x in (j.get('socios') or [])],
                     cod_nat=str((j.get('natureza_juridica') or {}).get('id') or '').replace('-', ''))
        else:
            tel = ' / '.join(t for t in [j.get('ddd_telefone_1') or '', j.get('ddd_telefone_2') or ''] if t.strip())
            r = dict(razao_social=j.get('razao_social'), nome_fantasia=j.get('nome_fantasia'),
                     situacao_receita=(j.get('descricao_situacao_cadastral') or '').upper(),
                     natureza_juridica=j.get('natureza_juridica'), atividade=j.get('cnae_fiscal_descricao'),
                     municipio_sede=f"{j.get('municipio') or ''}/{j.get('uf') or ''}",
                     telefone=tel, email=j.get('email') or '', mei=bool(j.get('opcao_pelo_mei')),
                     porte=j.get('porte') or j.get('descricao_porte'),
                     socios=[(x.get('nome_socio'), x.get('qualificacao_socio')) for x in (j.get('qsa') or [])],
                     cod_nat=str(j.get('codigo_natureza_juridica') or '').replace('-', ''))
        if not r.get('razao_social'): continue
        r['fonte_cadastro'] = nome
        return r
    return None


# ---------- e-mail de contato (todo CNPJ que chega e ainda não tem e-mail) ----------
# Achado no PC em 06/11/2026: minhareceita respondeu 499 CNPJs com e-mail vazio e a BrasilAPI não traz o campo.
# Por isso o e-mail vem de duas fontes públicas, alternadas: publica.cnpj.ws e receitaws.com.br (3 consultas/min cada).
EMAIL_FONTES = {
    'publica.cnpj.ws': 'https://publica.cnpj.ws/cnpj/{c}',
    'receitaws.com.br': 'https://receitaws.com.br/v1/cnpj/{c}',
}
EMAIL_INTERVALO = 21      # segundos entre chamadas da MESMA fonte
EMAIL_REVISITA = 180      # dias até reconsultar um CNPJ que veio sem e-mail
RX_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[a-z]{2,}$', re.I)


def email_de(fonte, j):
    """Devolve (email, socios[(nome, qualificação)]) ou None se a fonte disse que o CNPJ não existe."""
    if fonte == 'publica.cnpj.ws':
        est = j.get('estabelecimento') or {}
        soc = [(x.get('nome'), (x.get('qualificacao_socio') or {}).get('descricao')) for x in (j.get('socios') or [])]
        return (est.get('email') or '').strip().lower(), soc
    if (j.get('status') or '').upper() == 'ERROR':
        return None
    return (j.get('email') or '').strip().lower(), [(x.get('nome'), x.get('qual')) for x in (j.get('qsa') or [])]


def gravar_lotes(sb, linhas):
    # o PostgREST exige as mesmas colunas em todas as linhas de um lote: agrupa por conjunto de colunas
    grupos = {}
    for l in linhas: grupos.setdefault(tuple(sorted(l)), []).append(l)
    for g in grupos.values(): sb.upsert('empresas', g, 'cnpj')


def buscar_emails(sb, hoje, minutos=40, so=None):
    """Etapa incremental: consulta os CNPJs sem e-mail (novos primeiro) até o tempo acabar; o resto fica para amanhã."""
    corte = (hoje - dt.timedelta(days=EMAIL_REVISITA)).isoformat()
    base = sb.todos('empresas', 'cnpj,email,socios,email_busca_em,data_coleta,prioridade')
    fila = [e for e in base if not (e.get('email') or '').strip()
            and (not e.get('email_busca_em') or e['email_busca_em'] < corte) and (so is None or e['cnpj'] in so)]
    # nunca consultados e mais recentes primeiro; depois prioridade A > B > C
    fila.sort(key=lambda e: (bool(e.get('email_busca_em')), -(int(re.sub(r'\D', '', e.get('data_coleta') or '0') or 0)),
                             (e.get('prioridade') or 'Z')[0]))
    log(f'e-mail: {len(fila)} CNPJ(s) sem e-mail na fila; limite de {minutos} min nesta execução')
    if not fila: return dict(consultados=0, achados=0, restantes=0)
    t0, ultimo, descanso, falhas = time.time(), {f: 0.0 for f in EMAIL_FONTES}, {f: 0.0 for f in EMAIL_FONTES}, {f: 0 for f in EMAIL_FONTES}
    ativas, consultados, achados, sem_email_seguidos, gravar = list(EMAIL_FONTES), 0, 0, 0, []
    repetidos, k = set(), 0
    while fila and ativas and time.time() - t0 < minutos * 60:
        e = fila.pop(0)
        fonte = ativas[k % len(ativas)]; k += 1
        espera = max(ultimo[fonte] + EMAIL_INTERVALO, descanso[fonte]) - time.time()
        if espera > 0: time.sleep(espera)
        ultimo[fonte] = time.time()
        c = re.sub(r'\D', '', e['cnpj'])
        try:
            res = email_de(fonte, get_json(EMAIL_FONTES[fonte].format(c=c)))
            falhas[fonte] = 0
        except urllib.error.HTTPError as err:
            if err.code == 404: res = None
            else:
                if err.code == 429: descanso[fonte] = time.time() + 65
                else: falhas[fonte] += 1
                if e['cnpj'] not in repetidos: repetidos.add(e['cnpj']); fila.append(e)   # volta para a fila uma vez
                if falhas[fonte] >= 6: ativas.remove(fonte); log(f'e-mail: {fonte} saiu desta execução (6 falhas seguidas)')
                continue
        except Exception:
            falhas[fonte] += 1
            if e['cnpj'] not in repetidos: repetidos.add(e['cnpj']); fila.append(e)
            if falhas[fonte] >= 6: ativas.remove(fonte); log(f'e-mail: {fonte} saiu desta execução (6 falhas seguidas)')
            continue
        consultados += 1
        linha = dict(cnpj=e['cnpj'], email_busca_em=hoje.isoformat())
        if res:
            em, soc = res
            if em and RX_EMAIL.match(em):
                linha.update(email=em, email_fonte=f'{fonte} ({hoje:%d/%m/%Y})'); achados += 1; sem_email_seguidos = 0
            else:
                sem_email_seguidos += 1
            if soc and not (e.get('socios') or '').strip():
                linha['socios'] = '; '.join(mascara(f"{n} ({q})" if q else n) for n, q in soc if n)
        else:
            linha['email_fonte'] = f'{fonte}: CNPJ não encontrado ({hoje:%d/%m/%Y})'
        gravar.append(linha)
        if len(gravar) >= 10: gravar_lotes(sb, gravar); gravar = []
        dec = time.time() - t0
        log(f'e-mail: {consultados} consultado(s), {achados} com e-mail · {dec/60:.1f} min · fila {len(fila)} · '
            f'faltam ~{len(fila) * dec / max(1, consultados) / 60:.0f} min no total')
        if sem_email_seguidos >= 40:
            log('e-mail: 40 respostas seguidas sem e-mail. Parei para não gastar consultas; conferir se a fonte mudou o formato.')
            break
    if gravar: gravar_lotes(sb, gravar)
    log(f'e-mail: fim desta execução. {consultados} consultado(s), {achados} e-mail(s) novo(s), {len(fila)} para a próxima')
    return dict(consultados=consultados, achados=achados, restantes=len(fila))


# ---------- site da empresa: contatos publicados por ela mesma ----------
# Pedido do usuário (07/11/2026): além do e-mail da Receita, abrir o site da empresa e trazer as formas de contato.
# Como achar o site sem buscador: o domínio do e-mail da Receita (quando não é e-mail gratuito).
# Só páginas públicas, respeitando o robots.txt; nada de formulário, login ou captcha.
GRATUITOS = {'gmail.com', 'hotmail.com', 'outlook.com', 'live.com', 'yahoo.com', 'yahoo.com.br', 'bol.com.br', 'uol.com.br',
             'terra.com.br', 'ig.com.br', 'icloud.com', 'msn.com', 'globo.com', 'globomail.com', 'oi.com.br', 'r7.com',
             'zipmail.com.br', 'outlook.com.br', 'hotmail.com.br', 'protonmail.com', 'me.com', 'gmx.com', 'aol.com',
             'yandex.com', 'mail.com', 'live.com.br', 'superig.com.br', 'click21.com.br', 'pop.com.br'}
SITE_PAGINAS = ['', 'contato', 'fale-conosco', 'contatos', 'contact', 'sobre', 'quem-somos']
RX_MAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
RX_TEL = re.compile(r'(?<!\d)\(?(?:\+?55\s?)?\(?([1-9]{2})\)?[\s.-]?(9?\d{4})[\s.-]?(\d{4})(?!\d)')
RX_WA = re.compile(r'(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|whatsapp\.com/send\?phone=)\+?(\d{10,13})', re.I)
RX_REDE = re.compile(r'https?://(?:www\.)?(instagram\.com|facebook\.com|linkedin\.com/company|linkedin\.com/in|youtube\.com|tiktok\.com)/[A-Za-z0-9_.\-/]+', re.I)


def rdap_titular(dominio):
    """Registro.br RDAP (API pública JSON, sem captcha). Devolve o CNPJ (14 dígitos) do titular, '' se pessoa física/sem dado, None se não existe."""
    if not dominio.endswith('.br'): return ''
    try:
        j = get_json(f'https://rdap.registro.br/domain/{dominio}')
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        if e.code == 429: time.sleep(60)
        return ''
    except Exception:
        return ''
    finally:
        time.sleep(3)
    for ent in j.get('entities') or []:
        for pid in ent.get('publicIds') or []:
            d = re.sub(r'\D', '', str(pid.get('identifier') or ''))
            if len(d) == 14: return d
    return ''


def baixar_texto(url, limite=600_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=20) as r:
        if 'html' not in (r.headers.get('Content-Type') or 'html'): return '', r.geturl()
        return r.read(limite).decode('utf-8', 'ignore'), r.geturl()


def robots_permite(base, caminho):
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    try:
        t, _ = baixar_texto(base + '/robots.txt', 100_000); rp.parse(t.splitlines())
    except Exception:
        return True       # sem robots.txt: livre
    return rp.can_fetch(UA, base + '/' + caminho)


def contatos_do_site(dominio, cnpj, razao, fantasia):
    base = 'https://' + dominio
    achado = dict(emails=set(), telefones=set(), whatsapp=set(), redes=set(), paginas=[])
    confirma = ''
    c14 = re.sub(r'\D', '', cnpj)
    paginas = list(SITE_PAGINAS)
    try:
        h0, _ = baixar_texto(base + '/')
        for href in re.findall(r'href=["\']([^"\'#]+)["\']', h0, re.I):
            if re.search(r'contat|fale|atendimento', href, re.I):
                rel = re.sub(r'^https?://[^/]+', '', href).lstrip('/')
                if rel and not rel.startswith(('mailto:', 'tel:', 'javascript:')) and rel not in paginas: paginas.append(rel)
                if len(paginas) >= len(SITE_PAGINAS) + 5: break
    except Exception:
        pass
    for pg in paginas:
        if not robots_permite(base, pg): continue
        try:
            html, final = baixar_texto(f'{base}/{pg}')
        except Exception:
            if pg == '':
                try: html, final = baixar_texto(f'http://{dominio}/')
                except Exception: return None
            else: continue
        if not html: continue
        achado['paginas'].append(final)
        txt = re.sub(r'<[^>]+>', ' ', html)
        if c14 in re.sub(r'\D', '', txt) and not confirma: confirma = 'CNPJ aparece no site'
        for m in RX_MAIL.findall(html):
            m = m.lower().strip('.')
            if not re.search(r'\.(png|jpe?g|gif|svg|webp|css|js)$', m) and 'sentry' not in m and 'example' not in m:
                achado['emails'].add(m)
        for ddd, a, b in RX_TEL.findall(txt):
            achado['telefones'].add(f'{ddd}{a}{b}')
        for n in RX_WA.findall(html):
            achado['whatsapp'].add(re.sub(r'^55', '', n))
        for m in RX_REDE.finditer(html):
            u = m.group(0).rstrip('/')
            if not re.search(r'/(sharer|share|plugins|tr\b|dialog|intent)', u): achado['redes'].add(u)
        time.sleep(1)
    if not achado['paginas']: return None
    if not confirma:
        confirma = 'NÃO CONFIRMADO: o site não mostra o CNPJ'
    return dict(site=base, confirmacao=confirma,
                contatos={k: sorted(v)[:15] if isinstance(v, set) else v[:7] for k, v in achado.items()})


def buscar_sites(sb, hoje, minutos=15):
    corte = (hoje - dt.timedelta(days=EMAIL_REVISITA)).isoformat()
    base = sb.todos('empresas', 'cnpj,email,razao_social,nome_fantasia,site_busca_em,data_coleta')
    fila = []
    for e in base:
        if e.get('site_busca_em') and e['site_busca_em'] >= corte: continue
        email = (e.get('email') or '').lower()
        dom = email.split('@')[-1].strip() if '@' in email else ''
        if dom in GRATUITOS or re.match(r'(contab|contad|escritorio|assessoria)', dom): dom = ''
        palpites = []
        if e.get('nome_fantasia') or e.get('razao_social'):
            w = [x.lower() for x in re.split(r'[^A-Za-z0-9]+', sem_acento(e.get('nome_fantasia') or e['razao_social'])) if x and x not in PALAVRAS_VAZIAS and len(x) > 2]
            palpites = list(dict.fromkeys(filter(None, [''.join(w) + '.com.br' if w else '', ''.join(w[:2]) + '.com.br' if len(w) > 1 else '', (w[0] + '.com.br') if w else ''])))
        fila.append((e, dom, palpites))
    log(f'site: {len(fila)} empresa(s) para conferir (domínio do e-mail ou nome, decididos pelo Registro.br); limite de {minutos} min')
    t0, feitos, com, gravar = time.time(), 0, 0, []
    for e, dom, palpites in fila:
        if time.time() - t0 > minutos * 60: break
        c14 = re.sub(r'\D', '', e['cnpj']); r = None; via = ''
        # o domínio do e-mail só vale se o titular no Registro.br não for OUTRO CNPJ (ex.: contador)
        if dom:
            tit = rdap_titular(dom)
            if tit and tit[:8] != c14[:8]: dom = ''; via = 'domínio do e-mail é de terceiro (provável contador)'
            elif tit and tit[:8] == c14[:8]: via = 'Registro.br: titular é o próprio CNPJ'
        # sem domínio útil: testa endereços prováveis pelo nome, aceitos só se o titular tiver a mesma raiz de CNPJ
        if not dom:
            for pal in palpites:
                tit = rdap_titular(pal)
                if tit and tit[:8] == c14[:8]: dom, via = pal, 'Registro.br: titular é o próprio CNPJ'; break
        try: r = contatos_do_site(dom, e['cnpj'], '', '') if dom else None
        except Exception: r = None
        if r and via.startswith('Registro.br') and r['confirmacao'].startswith('NÃO'): r['confirmacao'] = via
        feitos += 1
        linha = dict(cnpj=e['cnpj'], site_busca_em=hoje.isoformat())
        if not r and via: linha.update(site_confirmacao=via)
        if r:
            com += 1
            # telefone/e-mail do site são do próprio site; CPF nunca entra (máscara em todo texto)
            r['contatos'] = {k: [mascara(x) for x in v] for k, v in r['contatos'].items()}
            linha.update(site=r['site'], site_confirmacao=r['confirmacao'], site_contatos=r['contatos'])
        gravar.append(linha)
        dec = time.time() - t0
        log(f'site: {feitos}/{len(fila)} ({feitos/len(fila)*100:.0f}%) · {com} com site · {dec/60:.1f} min · faltam ~{(len(fila)-feitos)*dec/feitos/60:.0f} min')
        if len(gravar) >= 10: gravar_lotes(sb, gravar); gravar = []
    if gravar: gravar_lotes(sb, gravar)
    log(f'site: fim. {feitos} conferido(s), {com} com site aberto')


# ---------- Supabase (REST) ----------
class Supabase:
    def __init__(self, url, chave):
        self.url, self.h = url.rstrip('/') + '/rest/v1', {'apikey': chave, 'Content-Type': 'application/json'}
        if chave.startswith('eyJ'): self.h['Authorization'] = f'Bearer {chave}'   # chave antiga (JWT); as novas sb_secret_ vão só no apikey

    def req(self, metodo, caminho, corpo=None, extra=None):
        h = dict(self.h, **(extra or {}))
        dados = json.dumps(corpo, ensure_ascii=False).encode() if corpo is not None else None
        r = urllib.request.Request(self.url + caminho, data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                t = resp.read().decode()
                return json.loads(t) if t else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Supabase {metodo} {caminho}: {e.code} {e.read().decode()[:300]}')

    def todos(self, tabela, colunas):
        out, ini = [], 0
        while True:
            lote = self.req('GET', f'/{tabela}?select={colunas}', extra={'Range': f'{ini}-{ini+999}'})
            out += lote
            if len(lote) < 1000: return out
            ini += 1000

    def upsert(self, tabela, linhas, chave):
        for i in range(0, len(linhas), 500):
            self.req('POST', f'/{tabela}?on_conflict={chave}', linhas[i:i+500],
                     {'Prefer': 'resolution=merge-duplicates,return=minimal'})


# ---------- principal ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', help='usar um CSV/ZIP local em vez de baixar do IBAMA (teste)')
    ap.add_argument('--sem-supabase', action='store_true', help='não grava; salva saida-teste.json')
    ap.add_argument('--sem-cadastro', action='store_true', help='não consulta o CNPJ (teste)')
    ap.add_argument('--minutos-email', type=int, default=40, help='tempo máximo da busca de e-mail (0 = pular)')
    ap.add_argument('--embargos', help='CSV local de termos de embargo (teste)')
    a = ap.parse_args()
    hoje = dt.date.today()
    if not a.sem_supabase:
        chave = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
        tipo = 'vazia' if not chave else 'publishable' if chave.startswith('sb_publishable_') else 'secret' if chave.startswith('sb_secret_') else ''
        if chave.startswith('eyJ'):
            try:
                import base64
                carga = chave.split('.')[1]; carga += '=' * (-len(carga) % 4)
                tipo = json.loads(base64.urlsafe_b64decode(carga)).get('role', '?')   # só o papel; a chave nunca é exibida
            except Exception: tipo = 'jwt ilegível'
        log(f'tipo da chave em SUPABASE_SERVICE_KEY: {tipo} (precisa ser secret ou service_role)')
        if tipo not in ('secret', 'service_role'):
            sys.exit('ERRO: SUPABASE_SERVICE_KEY não é a chave secret/service_role. No Supabase: Project Settings > API Keys > Secret keys.')
    sb = None if a.sem_supabase else Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
    if sb and os.environ.get('GITHUB_EVENT_NAME') == 'schedule':
        # horário de reserva: só roda se a coleta não rodou hoje depois dos diários
        inicio = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M:%S')
        if sb.req('GET', f'/coletas?select=id&status=eq.ok&fonte=like.IBAMA*&iniciada_em=gte.{inicio}&limit=1'):
            log('coleta de hoje já rodou depois dos diários; reserva não precisa rodar'); return
        log('reserva: a coleta não rodou depois dos diários hoje; rodando agora')
    reg = dict(fonte=FONTE_NOME + ' ' + FONTE_URL,
               metodo='UF=RJ; últimos 365 dias; só CNPJ com DV válido; CPF mascarado em todo texto; cadastro: BrasilAPI > minhareceita > cnpj.ws')
    id_coleta = None
    if sb:
        id_coleta = sb.req('POST', '/coletas', dict(reg, status='rodando'), {'Prefer': 'return=representation'})[0]['id']
    try:
        # 1) fonte
        if a.csv:
            arqs = list(arquivos_do_zip(a.csv)) if a.csv.endswith('.zip') else [(a.csv, open(a.csv, 'rb').read())]
        else:
            tmp = os.path.join(tempfile.gettempdir(), 'auto_infracao_csv.zip')
            log('baixando o arquivo do IBAMA', 0.1); baixar(FONTE_URL, tmp)
            arqs = list(arquivos_do_zip(tmp, hoje.year - 1))
        autos, lidos, occ = ler_autos(arqs, hoje)
        embargos = []
        if a.embargos:
            embargos, oe = ler_embargos(open(a.embargos, 'rb').read(), hoje); occ += oe
        elif not a.csv:
            tmp_e = os.path.join(tempfile.gettempdir(), 'termo_de_embargo.csv')
            try:
                log('baixando os termos de embargo', 58); baixar(EMB_URL, tmp_e); embargos, oe = ler_embargos(open(tmp_e, 'rb').read(), hoje); occ += oe
            except Exception as e:
                log(f'embargos indisponíveis hoje ({e}); seguindo só com os autos')
        log(f'{len(embargos)} termos de embargo de PJ no RJ', 59)
        if not a.csv:
            for chave, (pref, tipo_doc, url) in OUTRAS_FONTES.items():
                tmp_o = os.path.join(tempfile.gettempdir(), chave + '.csv')
                try:
                    baixar(url, tmp_o); oo = ler_outros(open(tmp_o, 'rb').read(), hoje, pref, tipo_doc, url); occ += oo
                    log(f'{chave}: {len(oo)} documento(s) de PJ no RJ em 12 meses')
                except Exception as e:
                    log(f'{chave} indisponível hoje ({e}); a pontuação segue sem ela')
        log(f'{lidos} linhas lidas; {len(autos)} autos de PJ no RJ nos últimos 365 dias', 60)

        # 2) o que já existe no banco
        existentes_autos = {x['n_auto'] for x in sb.todos('autos', 'n_auto')} if sb else set()
        empresas_bd = {x['cnpj']: x for x in sb.todos('empresas', '*')} if sb else {}
        contatos = sb.todos('contatos', 'cnpj,status,criado_em') if sb else []
        excluidas = {x['cnpj_raiz'] for x in sb.todos('exclusoes', 'cnpj_raiz')} if sb else {'33000167'}
        novos = [x for x in autos if x['n_auto'] not in existentes_autos]
        # outras fontes oficiais gravadas por coletores próprios (coletor/inea.py: INEA; coletor/dou.py: editais do DOU)
        # também viram empresa da base quando o documento é FATO, válido e dos últimos 12 meses
        corte_out = (hoje - dt.timedelta(days=365)).isoformat()
        occ_inea = [o for o in (sb.todos('ocorrencias', 'chave,cnpj,nome,data_documento,nivel,situacao') if sb else [])
                    if o['chave'].startswith(('INEA-', 'DOU3|')) and (o.get('nivel') or 'FATO') == 'FATO' and o.get('situacao') == 'VALIDO'
                    and str(o.get('data_documento') or '')[:10] >= corte_out and dv_cnpj(o.get('cnpj'))]

        # 3) cadastro: empresas novas ou com cadastro de mais de 30 dias
        corte12 = (hoje - dt.timedelta(days=365)).isoformat()
        cnpjs = sorted({x['cnpj'] for x in autos} | {x['cnpj'] for x in embargos
                        if x['status'] == 'VIGENTE' and x['data_embargo'] and x['data_embargo'] >= corte12}
                       | {o['cnpj'] for o in occ if o['tipo_documento'] not in ('AUTO DE INFRACAO', 'TERMO DE EMBARGO')
                          and o['situacao'] == 'VALIDO'}
                       | {o['cnpj'] for o in occ_inea})
        precisa = [c for c in cnpjs if c not in empresas_bd or not empresas_bd[c].get('cadastro_atualizado_em')
                   or dt.date.fromisoformat(empresas_bd[c]['cadastro_atualizado_em']) < hoje - dt.timedelta(days=30)]
        nome_auto = {}
        for x in sorted(autos, key=lambda x: x['data_auto']): nome_auto[x['cnpj']] = x['nome_no_auto']
        for o in occ:
            if o['nome']: nome_auto.setdefault(o['cnpj'], o['nome'])
        for o in occ_inea:
            if o.get('nome'): nome_auto.setdefault(o['cnpj'], o['nome'])
        for c in cnpjs: nome_auto.setdefault(c, '')
        empresas, sem_cad = [], 0
        for i, c in enumerate(precisa):
            r = None if a.sem_cadastro else cadastro(c)
            if not a.sem_cadastro: time.sleep(0.4)
            if r is None:
                sem_cad += 1
                if c in empresas_bd: continue          # mantém o cadastro antigo
                if not nome_auto[c]: continue           # só embargo e sem cadastro hoje: tenta amanhã
                r = dict(razao_social=nome_auto[c], situacao_receita='', fonte_cadastro='nome do auto (cadastro indisponível)', telefone='', email='', mei=False)
            nat = r.get('natureza_juridica') or ''
            cod_nat = r.pop('cod_nat', '') or ''
            individual = (bool(r.pop('mei', False)) or cod_nat == '2135' or 'Individual' in nat or 'Empresário' in nat
                          or bool(re.search(r'\d{11}', re.sub(r'[.\-]', '', r['razao_social'] or ''))))
            div = nomes_divergem(nome_auto[c], r['razao_social'] or '', r.get('nome_fantasia') or '')
            empresas.append(dict(
                cnpj=c, razao_social=mascara(r['razao_social']), nome_fantasia=mascara(r.get('nome_fantasia') or ''),
                situacao_receita=r.get('situacao_receita') or '', natureza_juridica=nat, individual=individual,
                atividade=r.get('atividade') or '', municipio_sede=r.get('municipio_sede') or '',
                # Pedido do usuário (06/11/2026): MEI e empresário individual entram na prospecção, com contato.
                telefone=re.sub(r'[^\d /]', '', r.get('telefone') or ''),
                email=(r.get('email') or '').strip().lower() or (empresas_bd.get(c) or {}).get('email') or '',
                socios='; '.join(mascara(f"{n} ({q})" if q else n) for n, q in (r.get('socios') or []) if n),
                nome_divergente=div,
                alerta='; '.join(filter(None, [
                    'Nome no auto difere da razão social atual: conferir (INDÍCIO)' if div else '',
                    f"Empresa {r['situacao_receita']} na Receita" if r.get('situacao_receita') and r['situacao_receita'] != 'ATIVA' else ''])),
                porte=r.get('porte') or '',
                natureza_codigo=cod_nat,
                fonte_cadastro=r.get('fonte_cadastro'), cadastro_atualizado_em=hoje.isoformat(), data_coleta=hoje.isoformat()))
            if i % 5 == 0: log(f'cadastro {i+1} de {len(precisa)}', 60 + 30 * (i + 1) / max(1, len(precisa)))

        # 4) pontuação de todas as empresas da base (novas e antigas)
        todas = dict(empresas_bd); todas.update({e['cnpj']: e for e in empresas})
        ult = {}
        for ct in sorted(contatos, key=lambda x: x['criado_em']): ult[ct['cnpj']] = ct['status']
        # base única: o que veio hoje + o que já está no banco (inclui o enviado pelo Radar do PC: INEA, DOU etc.)
        if sb:
            sb.upsert('ocorrencias', occ, 'chave')          # primeira_coleta fica com o default/valor antigo
            occ_todas = sb.todos('ocorrencias', 'cnpj,orgao,tipo_documento,data_documento,data_ciencia,prazo_defesa_fim_estimado,situacao,nivel,valor_indicado_rs_nao_e_dano,descricao,assunto')
        else:
            occ_todas = occ
        por_o = {}
        for o in occ_todas: por_o.setdefault(o['cnpj'], []).append(o)
        pont = [dict(cnpj=c, **pontuar_occ(e, por_o.get(c, []), hoje, ult.get(c), excluidas)) for c, e in todas.items()]
        # 4b) chance de contratar licenciamento (pedido do usuário, 11/11/2026: sempre antes de atualizar o painel)
        tem_chance = True
        if sb:
            try: sb.req('GET', '/empresas?select=chance_licenciamento&limit=1')
            except Exception: tem_chance = False; log('AVISO: colunas de chance ainda não existem: rode supabase/07_chance_licenciamento.sql', 92)
        for p in pont:
            c = chance_licenciamento(todas[p['cnpj']], por_o.get(p['cnpj'], []), hoje, p['prioridade'])
            if tem_chance: p.update(c)
            else: p['_chance'] = c['chance_licenciamento']
        log('chance de licenciamento: ' + ', '.join(f"{k} {sum(1 for p in pont if (p.get('chance_licenciamento') or p.get('_chance')) == k)}" for k in ('Alta', 'Média', 'Baixa')), 92)
        for p in pont: p.pop('_chance', None)
        dist = {}
        for p in pont: dist[p['prioridade'][0]] = dist.get(p['prioridade'][0], 0) + 1
        log(f'prioridades: {dist}', 95)

        # 5) gravar (empresas antes dos autos, por causa da chave estrangeira)
        if sb:
            sb.upsert('empresas', empresas, 'cnpj')
            sb.upsert('empresas', pont, 'cnpj')
            sb.upsert('autos', autos, 'n_auto')
            sb.upsert('embargos', [x for x in embargos if x['cnpj'] in todas], 'num_tad')
            sb.req('PATCH', f'/coletas?id=eq.{id_coleta}', dict(
                status='ok', terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(), autos_lidos=lidos,
                autos_rj_pj=len(autos), autos_novos=len(novos),
                empresas_novas=len([e for e in empresas if e['cnpj'] not in empresas_bd]),
                empresas_atualizadas=len([e for e in empresas if e['cnpj'] in empresas_bd]),
                mensagem=f'{sem_cad} CNPJ(s) sem cadastro disponível hoje'), {'Prefer': 'return=minimal'})
        else:
            for e in empresas: e.update(next(p for p in pont if p['cnpj'] == e['cnpj']))
            json.dump(dict(empresas=empresas, autos=autos, embargos=embargos, ocorrencias=occ), open('saida-teste.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        if sb and a.minutos_email > 0 and not a.sem_cadastro:
            try: buscar_emails(sb, hoje, a.minutos_email)
            except Exception as e: log(f'e-mail: etapa interrompida ({e}); os dados da coleta já estão gravados')
            try: buscar_sites(sb, hoje)
            except Exception as e: log(f'site: etapa interrompida ({e})')
        log(f'FIM: {len(autos)} autos ({len(novos)} novos), {len(empresas)} empresas gravadas/atualizadas', 100)
        print('\a', end='')
    except Exception as e:
        log(f'ERRO: {e}')
        if sb and id_coleta:
            try: sb.req('PATCH', f'/coletas?id=eq.{id_coleta}', dict(status='erro', terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(), mensagem=str(e)[:900]), {'Prefer': 'return=minimal'})
            except Exception: pass
        sys.exit(1)

if __name__ == '__main__':
    main()
