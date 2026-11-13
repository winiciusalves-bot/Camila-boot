#!/usr/bin/env python3
"""
Ambiental Costa · Diário Eletrônico do INEA (https://diarioeletronico.inea.rj.gov.br/).

O que é lido: a EDIÇÃO DO DIA, a mesma lista que a página usa para montar o PDF do botão "Exportar para PDF".
Sem login e sem captcha. A pesquisa com filtros da página tem reCAPTCHA e NÃO é usada aqui.
Primeira edição: 29/08/2023. Conferido no navegador do usuário em 13/11/2026.

Pedido do usuário (13/11/2026): ficar só com as NOTIFICAÇÕES, de fiscalização e de licenciamento.
  - NOTIFICAÇÃO DE FISCALIZAÇÃO -> ocorrencias (chave INEA-DE|...), tipo "NOTIFICACAO INEA (FISCALIZACAO)".
  - NOTIFICAÇÃO DE LICENCIAMENTO (exigência num pedido de licença) -> ocorrencias (chave INEA-DL|...),
    tipo "NOTIFICACAO INEA (LICENCIAMENTO)". Não é infração: é pendência num processo de licença.
  Ambas: PJ com DV do CNPJ válido, nivel FATO, situacao VALIDO; a coleta diária transforma em empresa da base.
  Notificação NÃO é auto de infração nem multa. Licença emitida e pedido (requerimento) são lidos só para a contagem
  e descartados.
Regras: CPF nunca é gravado (pessoa física fica fora); nomes passam pela máscara de CPF; registro de teste do INEA
é descartado; o município é o do ENDEREÇO do interessado, não o do local fiscalizado (fica dito na descrição).
O campo "Autuado" do sistema NÃO é auto de infração (só vem marcado nos pedidos) e não é usado.

Uso:
  python -I coletor/inea_diario.py                      # últimos 10 dias, grava
  python -I coletor/inea_diario.py --dias 30 --sem-supabase --amostra
  python -I coletor/inea_diario.py --desde 2023-08-29   # carga do histórico (cerca de 1 chamada por segundo)
"""
import argparse, collections, datetime as dt, json, os, re, sys, time, urllib.error, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from coletar import Supabase, dv_cnpj, fmt_cnpj, mascara, log, UA   # mesmas regras do coletor diário

SITE = 'https://diarioeletronico.inea.rj.gov.br/'
API = SITE + 'DiarioEletronico.Api/Processo/BuscaProcessosDiaAnterior'
PRIMEIRA = dt.date(2023, 8, 29)
PAUSA = 1.0          # segundos entre um dia e outro (não pesar no servidor do INEA)

CAT_FISC, CAT_NOTLIC, CAT_EMIT, CAT_PED = 'NOTIFICACAO DE FISCALIZACAO', 'NOTIFICACAO DE LICENCIAMENTO', 'DOCUMENTO EMITIDO', 'REQUERIMENTO'


def edicao(d):
    """Número da edição, pela mesma conta da página (dias desde 29/08/2023 + 1)."""
    return (d - PRIMEIRA).days + 1


def ler_dia(d, tentativas=4):
    corpo = json.dumps({'date': d.isoformat()}).encode()
    for i in range(tentativas):
        try:
            r = urllib.request.Request(API, data=corpo, method='POST', headers={
                'User-Agent': UA, 'Accept': 'application/json', 'Content-Type': 'application/json',
                'Origin': SITE.rstrip('/'), 'Referer': SITE})
            with urllib.request.urlopen(r, timeout=60) as resp:
                dados = json.loads(resp.read().decode('utf-8') or '[]')
                if not isinstance(dados, list): raise ValueError(f'resposta inesperada: {str(dados)[:200]}')
                return dados
        except Exception as e:
            espera = 2 ** (i + 1)
            log(f'{d.isoformat()}: falhou ({e}); nova tentativa em {espera} s')
            time.sleep(espera)
    return None


def categoria(x):
    tipo = x.get('Tipo')
    if tipo == 2: return CAT_PED
    if tipo == 0: return CAT_EMIT
    if re.search(r'fiscaliza', x.get('Descricao_Instrumento_Titulo') or '', re.I): return CAT_FISC
    return CAT_NOTLIC


def limpo(v, n=200):
    v = re.sub(r'\s+', ' ', str(v or '')).strip()
    return '' if v.lower() in ('null', 'none', 'n/a') else v[:n]


def converter(x, d, hoje):
    """Devolve (destino, linha) ou (motivo_descarte, None)."""
    doc = re.sub(r'\D', '', x.get('Documento') or '')
    nome = limpo(x.get('Nome_Requerente'))
    if re.search(r'\bTESTE\b', nome, re.I): return 'teste do INEA', None
    if len(doc) == 11: return 'pessoa física (fora)', None
    if len(doc) != 14 or not dv_cnpj(doc): return 'sem CNPJ válido', None
    cat = categoria(x)
    titulo = limpo(x.get('Descricao_Instrumento_Titulo')).replace(' ()', '')
    numero = limpo(x.get('Numero_Documento'), 80)
    processo = limpo(x.get('Processo'), 80)
    setor = limpo(x.get('Setor_Sigla'), 40)
    data_pub = limpo(x.get('Data_Publicacao'))[:10] or d.isoformat()
    mun = limpo(x.get('Municipio'), 80)
    if mun.lower().startswith('todos'): mun = ''
    atividade = limpo(x.get('Atividade'), 150)
    cod_ativ = limpo(x.get('Codigo_Atividade'), 20)
    ident = numero or f"{x.get('IdRequerimento') or ''}-{processo}-{titulo}"
    link = f'{SITE} (edição nº {edicao(d)} de {d.strftime("%d/%m/%Y")})'
    if cat not in (CAT_FISC, CAT_NOTLIC): return 'licença emitida ou pedido (descartado)', None
    fisc = cat == CAT_FISC
    veicular = fisc and setor.upper().endswith('SERVCPV')
    if fisc: assunto = 'Fiscalização - poluição veicular (INEA/SERVCPV)' if veicular else 'Fiscalização'
    else: assunto = f'Licenciamento - {titulo}' if titulo else 'Licenciamento'
    if atividade: assunto += f' · atividade {cod_ativ} {atividade}'.rstrip()
    natureza = ('Notificação não é auto de infração nem multa; o que foi exigido está no processo (SEI). ' if fisc else
                'Notificação de exigência num pedido de licença: não é infração; o que falta entregar está no processo (SEI). ')
    return 'ocorrencias', dict(
        chave=f"{'INEA-DE' if fisc else 'INEA-DL'}|{ident}|{doc}"[:300],
        fonte='Diário Eletrônico do INEA', orgao='INEA',
        tipo_documento='NOTIFICACAO INEA (FISCALIZACAO)' if fisc else 'NOTIFICACAO INEA (LICENCIAMENTO)',
        numero=numero, processo=processo, data_documento=data_pub,
        data_documento_status='data de publicação no Diário Eletrônico', data_ciencia=None,
        prazo_defesa_fim_estimado=None, prazo_defesa_status='',
        situacao='VALIDO', cnpj=fmt_cnpj(doc), nome=mascara(nome), municipio=mun.title() if mun.isupper() else mun,
        cod_ibge='', valor_indicado_rs_nao_e_dano=None, assunto=assunto[:200],
        descricao=mascara(
            f'Notificação publicada no Diário Eletrônico do INEA nº {edicao(d)} de {d.strftime("%d/%m/%Y")}. '
            f'Setor: {setor or "não informado"}. Processo: {processo or "não informado"}. ' + natureza +
            'Município do endereço do interessado, não necessariamente do local da atividade.'),
        nivel='FATO', link_fonte=link, ultima_coleta=hoje.isoformat(), origem='coletor-online')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dias', type=int, default=10, help='dias para trás (padrão 10)')
    ap.add_argument('--desde', help='AAAA-MM-DD: lê de uma data até ontem (carga do histórico)')
    ap.add_argument('--ate', help='AAAA-MM-DD: último dia (padrão: hoje)')
    ap.add_argument('--sem-supabase', action='store_true')
    ap.add_argument('--amostra', action='store_true')
    a = ap.parse_args()

    hoje = dt.date.today()
    fim = dt.date.fromisoformat(a.ate) if a.ate else hoje
    ini = max(PRIMEIRA, dt.date.fromisoformat(a.desde) if a.desde else fim - dt.timedelta(days=a.dias))
    dias = [ini + dt.timedelta(days=k) for k in range((fim - ini).days + 1)]
    sb = None if a.sem_supabase else Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
    t0 = dt.datetime.now(dt.timezone.utc)
    log(f'Diário Eletrônico do INEA: {len(dias)} dia(s), de {ini:%d/%m/%Y} a {fim:%d/%m/%Y}')

    # teste de conexão antes de rodar tudo (regra: nunca rodar horas com erro)
    if ler_dia(fim - dt.timedelta(days=1), tentativas=2) is None:
        msg = 'site do INEA não respondeu ao teste de conexão; nada foi lido'
        log('ERRO: ' + msg)
        if sb: sb.req('POST', '/coletas', dict(fonte=f'Diário Eletrônico do INEA {SITE}', metodo='edição diária (JSON da página)',
                                             status='erro', iniciada_em=t0.isoformat(), terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(),
                                             mensagem=msg), {'Prefer': 'return=minimal'})
        sys.exit(1)

    occ, cont, por_cat, falhas, lidos = {}, collections.Counter(), collections.Counter(), [], 0
    for k, d in enumerate(dias):
        lista = ler_dia(d)
        if lista is None: falhas.append(d.isoformat()); continue
        lidos += len(lista)
        for x in lista:
            por_cat[categoria(x)] += 1
            destino, linha = converter(x, d, hoje)
            if linha is None: cont[destino] += 1; continue
            occ[linha['chave']] = linha
        if k % 5 == 0 or k == len(dias) - 1:
            log(f'{d:%d/%m/%Y}: {len(lista)} publicação(ões) · acumulado {lidos}', 100 * (k + 1) / len(dias))
        if k < len(dias) - 1: time.sleep(PAUSA)

    occ = list(occ.values())
    nf = [o for o in occ if o['chave'].startswith('INEA-DE|')]
    nl = [o for o in occ if o['chave'].startswith('INEA-DL|')]
    log(f'{lidos} publicação(ões) lidas · por tipo: ' + ', '.join(f'{c} {n}' for c, n in por_cat.most_common()))
    log(f'fora: ' + (', '.join(f'{c} {n}' for c, n in cont.most_common()) or 'nenhuma'))
    log(f'{len(nf)} notificação(ões) de fiscalização de PJ ({sum(1 for o in nf if "SERVCPV" in o["assunto"])} de poluição veicular) · '
        f'{len(nl)} notificação(ões) de licenciamento de PJ · {len({o["cnpj"] for o in occ})} CNPJ')
    if falhas: log(f'ATENÇÃO: {len(falhas)} dia(s) sem resposta: {", ".join(falhas[:20])}')

    resumo = f'{lidos} publicações; {len(nf)} notificações de fiscalização e {len(nl)} de licenciamento de PJ; dias sem resposta: {len(falhas)}'
    if sb:
        ja = {o['chave'] for o in sb.todos('ocorrencias', 'chave') if o['chave'].startswith(('INEA-DE|', 'INEA-DL|'))}
        sb.upsert('ocorrencias', occ, 'chave')
        novas = sum(1 for o in occ if o['chave'] not in ja)
        sb.req('POST', '/coletas', dict(
            fonte=f'Diário Eletrônico do INEA {SITE}',
            metodo='edição diária (mesma lista do PDF da página, sem captcha); só notificações (fiscalização e licenciamento) de PJ com DV válido -> ocorrencias; licenças e pedidos descartados; CPF fora',
            status='ok' if not falhas else 'parcial', iniciada_em=t0.isoformat(), terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(),
            autos_lidos=lidos, autos_novos=novas, mensagem=resumo[:900]), {'Prefer': 'return=minimal'})
        log(f'{novas} notificação(ões) nova(s) gravada(s) em ocorrencias')

    if a.amostra:
        for o in nf[:10] + nl[:8]:
            log(f"   {'FISC' if o['chave'].startswith('INEA-DE') else 'LIC '} {o['data_documento']} · {o['cnpj']} · {o['nome'][:45]} · {o['municipio']} · nº {o['numero']} · {o['assunto'][:60]}")
        mun = collections.Counter(o['municipio'] for o in occ)
        log('   municípios (endereço): ' + ', '.join(f'{m or "?"} {n}' for m, n in mun.most_common(12)))
    log('FIM', 100)
    print('\a')
    if falhas and len(falhas) == len(dias): sys.exit(1)


if __name__ == '__main__':
    main()
