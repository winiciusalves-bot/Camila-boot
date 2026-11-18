"""Fila "Diários a conferir" (pedido do usuário em 18/11/2026).

1) sincronizar(): os achados dos diários municipais (auto de infração, embargo, interdição; últimos 12 meses)
   entram na tabela fila_diarios como INDÍCIO, com uma PRÉ-TRIAGEM automática do trecho.
   A pré-triagem só ordena a fila; ela NÃO decide nada (regra: palavra-chave não é decisão).
2) promover(): o que uma pessoa conferiu lendo o ato e marcou "É FATO" vira ocorrência FATO (chave DOMF|...),
   e a coleta passa a tratar o CNPJ como empresa da base (cadastro, pontuação, chance, painel).
   "Descartado" não volta para a fila.
"""
import re
import unicodedata

RX_ALVO = re.compile(r'auto de infra|embargo|interdi', re.I)

# fiscalização que não é ambiental (posturas, vigilância sanitária, fazenda, trânsito, consumidor, obras sem tema ambiental)
RX_NAO_AMB = re.compile(
    r'postura|sanit[aá]ri|vigil[aâ]ncia|fazend[aá]ri|tribut|\bISS\b|\bIPTU\b|\bICMS\b|procon|consumidor|tr[aâ]nsito|'
    r'estacionamento rotativo|alvar[aá] de funcionamento|c[oó]digo de obras|fiscal de obras|habite-se|licita[cç]|preg[aã]o|'
    r'ata de registro de pre[cç]os|contrato n|aditivo|recurso volunt|contribuinte|cr[eé]dito tribut|d[ií]vida ativa', re.I)
# contexto ambiental perto do auto
RX_AMB = re.compile(
    r'meio ambiente|ambienta|sustentabilidade|\bSEMA\b|\bSEMMA|\bSEMAM|\bSMMA|SEMMATRAN|/MA/|\bINEA\b|licen[cç]a ambiental|licenciamento|'
    r'3\.?467|9\.?605|6\.?514|polui|res[ií]duo|efluente|esgoto|vegeta|supress|desmat|\bAPP\b|preserva[cç][aã]o permanente|'
    r'fauna|flora|recursos h[ií]dricos|ru[ií]do|sonora|emiss[aã]o|aterro|terraplen|extra[cç][aã]o mineral|areia|saibro|'
    r'unidade de conserva|\bAPA\b|parque natural|manguez|restinga|c[oó]rrego|corte de [aá]rvore|poda de [aá]rvore', re.I)
RX_NOME_FORA = re.compile(r'o nome da Receita n[aã]o aparece no trecho', re.I)


# número com cara de CPF (000.000.000-00) sai mascarado no trecho da fila mesmo com dígito verificador inválido
RX_CPF_FORMATO = re.compile(r'(?<![\d./-])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d/])')


def mascara_trecho(t):
    return RX_CPF_FORMATO.sub('[CPF omitido]', str(t or ''))


def sem_acento(s):
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()


def pretriagem(trecho, assunto=''):
    """('provavel' | 'duvidoso' | 'provavel_falso', motivo). Só ordena a fila; quem decide é quem lê o ato."""
    t = f'{assunto or ""} {trecho or ""}'
    amb = RX_AMB.findall(t)
    nao = RX_NAO_AMB.findall(t)
    nome_fora = bool(RX_NOME_FORA.search(t))
    if nao and not amb:
        return 'provavel_falso', 'fiscalização não ambiental no trecho: ' + ', '.join(sorted({x.lower() for x in nao})[:3])
    if amb and not nome_fora and not nao:
        return 'provavel', 'contexto ambiental no trecho: ' + ', '.join(sorted({x.lower().strip() for x in amb})[:3])
    motivos = []
    if amb: motivos.append('tem contexto ambiental (' + ', '.join(sorted({x.lower().strip() for x in amb})[:2]) + ')')
    if nao: motivos.append('mas cita ' + ', '.join(sorted({x.lower() for x in nao})[:2]))
    if nome_fora: motivos.append('o nome da empresa não aparece no trecho (o CNPJ pode ser de outra parte)')
    if not motivos: motivos.append('sem contexto ambiental claro no trecho')
    return 'duvidoso', '; '.join(motivos)


def tabela_existe(sb):
    try:
        sb.req('GET', '/fila_diarios?select=chave&limit=1'); return True
    except Exception:
        return False


def sincronizar(sb, hoje, log=print):
    """Põe na fila os achados novos (INDÍCIO) e preenche a pré-triagem dos que ainda não têm."""
    import datetime as dt
    if not tabela_existe(sb):
        log('fila de diários: tabela fila_diarios ainda não existe (rode supabase/10_fila_diarios.sql)'); return 0
    corte = (hoje - dt.timedelta(days=365)).isoformat()
    occ = sb.todos('ocorrencias', 'chave,cnpj,nome,municipio,orgao,data_documento,assunto,link_fonte,descricao,nivel,origem')
    na_fila = {x['chave']: x for x in sb.todos('fila_diarios', 'chave,pretriagem')}
    novas = []
    for o in occ:
        if o.get('origem') != 'coletor-diarios' or o.get('nivel') != 'INDICIO' or not str(o.get('chave', '')).startswith('DOMT|'): continue
        if not RX_ALVO.search(o.get('assunto') or '') or str(o.get('data_documento') or '')[:10] < corte: continue
        f = na_fila.get(o['chave'])
        if f and f.get('pretriagem'): continue
        p, m = pretriagem(o.get('descricao'), o.get('assunto'))
        linha = dict(chave=o['chave'], cnpj=o['cnpj'], nome=o.get('nome'), municipio=o.get('municipio'), orgao=o.get('orgao'),
                     data_documento=o.get('data_documento'), assunto=o.get('assunto'), link_fonte=o.get('link_fonte'),
                     trecho=mascara_trecho(o.get('descricao')), pretriagem=p, pretriagem_motivo=m)
        novas.append(linha)
    if novas:
        # merge só nas colunas enviadas: status/decisão de quem conferiu ficam como estão
        sb.upsert('fila_diarios', novas, 'chave')
    log(f'fila de diários: {len(novas)} achado(s) novo(s) ou pré-triado(s) agora; {len(na_fila)} já estavam na fila')
    return len(novas)


TIPO_DOC = {'auto de infração ambiental': ('AUTO DE INFRACAO', 'VALIDO'),
            'embargo': ('TERMO DE EMBARGO', 'VIGENTE'),
            'interdição': ('TERMO DE INTERDICAO', 'VALIDO'),
            'notificação ambiental': ('NOTIFICACAO', 'VALIDO')}


def promover(sb, hoje, log=print):
    """Conferidos como FATO viram ocorrência FATO (DOMF|chave). Devolve as ocorrências gravadas."""
    if not tabela_existe(sb): return []
    fatos = [x for x in sb.todos('fila_diarios', '*') if x.get('status') == 'fato' and x.get('tipo_confirmado') in TIPO_DOC]
    occ = []
    for x in fatos:
        tipo, sit = TIPO_DOC[x['tipo_confirmado']]
        quem = f"conferido no diário por {x.get('autor_email') or 'usuário'} em {str(x.get('conferido_em') or '')[:10]}"
        occ.append(dict(
            chave='DOMF|' + x['chave'][5:], fonte='Diário Oficial Municipal (conferido por pessoa)', orgao=x.get('orgao'),
            tipo_documento=tipo, numero=x.get('numero_ato') or '', processo='',
            data_documento=x.get('data_ato') or x.get('data_documento'),
            data_documento_status='data do ato' if x.get('data_ato') else 'data da edição do diário (data do ato não informada)',
            situacao=sit, cnpj=x['cnpj'], nome=x.get('nome'), municipio=x.get('municipio'),
            assunto=x['tipo_confirmado'], descricao=(f"{quem}. " + (f"Nota: {x['nota']}. " if x.get('nota') else '') + mascara_trecho(x.get('trecho')))[:2000],
            nivel='FATO', link_fonte=x.get('link_fonte'), ultima_coleta=hoje.isoformat(), origem='fila-diarios'))
    if occ: sb.upsert('ocorrencias', occ, 'chave')
    log(f'fila de diários: {len(occ)} conferido(s) como FATO entram na base de empresas')
    return occ
