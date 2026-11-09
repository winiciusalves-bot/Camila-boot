#!/usr/bin/env python3
"""
Envio dos diários para a base comum (schema "comum" no Supabase), plano único dos diários do RJ (09/11/2026).

O mesmo formato serve aos dois projetos:
  - coletor dos municípios (este repositório, fonte QUERIDO_DIARIO);
  - Vigia e alerta do gabinete (DO_RIO, DCM_RIO, DOERJ, DOU, PNCP).
Cada lado grava o seu e lê o do outro. Nada é coletado duas vezes.

Grava pela função public.diarios_gravar (supabase/07_diarios_comum_rpc.sql), em lotes de 300 linhas.
Regras: CNPJ só com DV válido e sem pontuação; CPF nunca aberto (o banco recusa e a linha volta em
"rejeitados"); tudo é INDÍCIO até alguém ler o ato. Se o banco não responder, os CSVs da rodada
continuam valendo e o envio pode ser refeito depois (hash_ato não duplica).

Uso dentro de outro script:
    from comum_diarios import enviar
    res = enviar(sb, 'QUERIDO_DIARIO', 'diarios_rj.py', '1.0', 'github-actions', manifesto, citados, pessoal)
Uso solto (reenviar CSVs de uma rodada):
    python -I coletor/comum_diarios.py <pasta_com_csvs> QUERIDO_DIARIO
"""
import csv, datetime as dt, hashlib, os, re, sys

RX_CPF_FMT = re.compile(r'(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)')
RX_11 = re.compile(r'(?<![\d./-])\d{11}(?!\d)')


def sem_cpf(t):
    """Mais estrita que a máscara dos relatórios: o banco recusa QUALQUER padrão de CPF, com DV válido ou não."""
    t = RX_CPF_FMT.sub('***.***.***-**', t or '')
    return RX_11.sub('[11 dígitos omitidos]', t)


def dv_ok(c):
    c = re.sub(r'\D', '', c or '')
    if len(c) != 14 or len(set(c)) == 1: return False
    def d(base, pesos):
        s = sum(int(x) * p for x, p in zip(base, pesos)); r = s % 11
        return '0' if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return c[12] == d(c[:12], p1) and c[13] == d(c[:13], [6] + p1)


def iso(data):
    """'2026-11-09' ou '09/11/2026' -> '2026-11-09'."""
    data = (data or '').strip()[:10]
    if re.match(r'\d{2}/\d{2}/\d{4}$', data): return f'{data[6:]}-{data[3:5]}-{data[:2]}'
    return data


def slug(s):
    import unicodedata
    s = unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def hash_ato(sha_ou_link, chave, trecho):
    return hashlib.sha256(f'{sha_ou_link}|{chave}|{trecho}'.encode('utf-8')).hexdigest()


def montar(fonte, manifesto, citados, pessoal):
    """Converte as linhas dos CSVs do formato comum (data;fonte;ente;cnpj;razao_receita;tipo;valor;classe;link;trecho)
    e do manifesto (data;fonte;ente;edicao;link;sha256;bytes;texto) nas linhas das tabelas comum.*"""
    edicoes, por_link = [], {}
    for m in manifesto:
        ed = dict(fonte=fonte, ente=m.get('ente') or '', data=iso(m.get('data')), edicao=str(m.get('edicao') or ''),
                  parte=m.get('parte') or 'unica', link=m.get('link') or '', sha256=(m.get('sha256') or '').lower() or None,
                  bytes=m.get('bytes') or None, id_fonte=m.get('id_fonte'), arquivo=m.get('arquivo'))
        if not ed['data'] or not ed['link']: continue
        # duas partes do mesmo dia sem número de edição: o link separa
        ch = (ed['data'], ed['edicao'], ed['parte'], ed['ente'])
        if any((e['data'], e['edicao'], e['parte'], e['ente']) == ch and e['link'] != ed['link'] for e in edicoes):
            ed['parte'] = 'p' + hashlib.sha1(ed['link'].encode()).hexdigest()[:8]
        edicoes.append(ed); por_link[ed['link']] = ed
    atos = []
    for tipo, linhas in (('cnpj_citado', citados), ('pessoal', pessoal)):
        for l in linhas:
            link = l.get('link') or ''
            ed = por_link.get(link) or {}
            cnpj = re.sub(r'\D', '', l.get('cnpj') or '')
            if cnpj and not dv_ok(cnpj): continue
            trecho = sem_cpf(l.get('trecho') or '')[:500]   # plano grátis de 500 MB: o texto completo fica no link
            t_orig = (l.get('tipo') or '').upper()
            a = dict(fonte=fonte, ente=l.get('ente') or ed.get('ente') or '', data=iso(l.get('data')) or ed.get('data'),
                     edicao=ed.get('edicao', ''), parte=ed.get('parte', 'unica'), orgao=l.get('orgao'), tipo=tipo,
                     cnpj=cnpj or None, razao_receita=l.get('razao_receita') or None,
                     pessoa_nome=sem_cpf(l.get('pessoa_nome') or '') or None, cargo=l.get('cargo') or None,
                     valor=None, processo=l.get('processo') or None,
                     classe='FATO' if (l.get('classe') or '').upper().startswith('FATO') else 'INDICIO',
                     link=link, trecho=trecho)
            v = (l.get('valor') or '').strip()
            if v:
                v = v.replace('R$', '').strip()
                if ',' in v: v = v.replace('.', '').replace(',', '.')   # formato BR
                try: a['valor'] = float(v)
                except ValueError: pass
            if tipo == 'pessoal':
                a['nivel'] = 'alto' if 'ALTO' in t_orig else None
                a['acao'] = re.sub(r'^ALTO ESCAL[ÃA]O - ', '', t_orig) or None
            a['hash_ato'] = hash_ato(ed.get('sha256') or link, cnpj or a.get('pessoa_nome') or a.get('acao') or '', trecho)
            atos.append(a)
    return edicoes, atos


def enviar(sb, fonte, robo, versao, onde, manifesto, citados, pessoal, lote=300, log=print):
    edicoes, atos = montar(fonte, manifesto, citados, pessoal)
    ini = dt.datetime.now(dt.timezone.utc).isoformat()
    tot = dict(edicoes=0, atos_novos=0, atos_repetidos=0, rejeitados=[])
    coleta_id = None
    pedacos = [(edicoes[i:i + lote], []) for i in range(0, len(edicoes), lote)] + \
              [([], atos[i:i + lote]) for i in range(0, len(atos), lote)] or [([], [])]
    try:
        for k, (eds, ats) in enumerate(pedacos, 1):
            p = dict(edicoes=eds, atos=ats)
            if coleta_id: p['coleta_id'] = coleta_id
            else: p['coleta'] = dict(fonte=fonte, robo=robo, versao=versao, onde=onde, iniciou=ini, status='rodando')
            r = sb.req('POST', '/rpc/diarios_gravar', dict(p=p))
            coleta_id = r['coleta_id']
            for x in ('edicoes', 'atos_novos', 'atos_repetidos'): tot[x] += r.get(x, 0)
            tot['rejeitados'] += r.get('rejeitados') or []
            log(f'base comum: lote {k}/{len(pedacos)} ({100 * k // len(pedacos)}%)')
        status = 'ok' if not tot['rejeitados'] else 'parcial'
        sb.req('POST', '/rpc/diarios_gravar', dict(p=dict(coleta_id=coleta_id, coleta=dict(
            status=status, linhas=tot['atos_novos'],
            erro=(f"{len(tot['rejeitados'])} linha(s) recusada(s): " + '; '.join(x['motivo'] for x in tot['rejeitados'][:5])) if tot['rejeitados'] else None))))
    except Exception as e:
        log(f'base comum: envio falhou ({e}); os CSVs da rodada continuam valendo e o envio pode ser refeito (não duplica)')
        if coleta_id:
            try: sb.req('POST', '/rpc/diarios_gravar', dict(p=dict(coleta_id=coleta_id, coleta=dict(status='falhou', erro=str(e)[:500]))))
            except Exception: pass
        tot['erro'] = str(e)
    tot['coleta_id'] = coleta_id
    log(f"base comum ({fonte}): {tot['edicoes']} edição(ões), {tot['atos_novos']} ato(s) novo(s), "
        f"{tot['atos_repetidos']} já existiam, {len(tot['rejeitados'])} recusado(s)")
    return tot


def ler_csv(cam):
    if not os.path.exists(cam): return []
    with open(cam, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from coletar import Supabase
    pasta, fonte = sys.argv[1], sys.argv[2]
    sb = Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
    enviar(sb, fonte, 'comum_diarios.py', '1.0', 'reenvio manual', ler_csv(os.path.join(pasta, 'manifesto.csv')),
           ler_csv(os.path.join(pasta, 'cnpjs_citados.csv')), ler_csv(os.path.join(pasta, 'nomeacoes_todas.csv')))
