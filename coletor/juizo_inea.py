"""Juízo de licenciamento das notificações do Diário Eletrônico do INEA, ANTES de levar ao painel.

Pedido do usuário (13/11/2026): levar ao painel só as notificações (fiscalização e licenciamento) dos
últimos 90 dias, e só depois do juízo Alta/Média/Baixa/Fora. Este script NÃO grava no Supabase:
gera um relatório para conferência. É o mesmo juízo do painel (coletar.pontuar_occ + chance.chance),
com o cadastro público do CNPJ (minhareceita.org, BrasilAPI, publica.cnpj.ws).

Entrada: CSVs da opção [17] do Radar (04-Achados\\inea-diario\\fiscalizacao_*.csv e licenciamento_*.csv,
separador ';'), no formato da tabela ocorrencias.
Uso:  python juizo_inea.py --dias 90 --saida PASTA arquivo1.csv arquivo2.csv [--excluir excluir_cnpj.txt]
Cache do cadastro em PASTA\\cache_cadastro_inea.json (roda de novo sem refazer consultas).
Fora = CNPJ não ATIVO, órgão público, lista de exclusão (Petrobras) ou sem cadastro. Fora NÃO vai ao painel.
Notificação não é auto de infração nem multa; o juízo é COMERCIAL, não acusação.
"""
import argparse, csv, datetime as dt, json, os, re, sys, time
import importlib.util as _ilu

_aqui = os.path.dirname(os.path.abspath(__file__))
def _mod(nome):
    sp = _ilu.spec_from_file_location(nome, os.path.join(_aqui, nome + '.py'))
    m = _ilu.module_from_spec(sp); sp.loader.exec_module(m); return m
co = _mod('coletar')
ch = _mod('chance')

INICIO = time.time()


def progresso(i, n, txt=''):
    dec = time.time() - INICIO
    falta = dec / i * (n - i) if i else 0
    print(f'\r{100 * i / max(1, n):5.1f}%  {i}/{n}  decorrido {dec / 60:4.1f} min  previsão {falta / 60:4.1f} min  {txt[:40]:<40}', end='', flush=True)


def ler(arquivos, desde):
    occ = []
    for a in arquivos:
        with open(a, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter=';'):
                if not (r.get('chave') or '').startswith('INEA-'): continue
                if (r.get('data_documento') or '')[:10] < desde: continue
                c = re.sub(r'\D', '', r.get('cnpj') or '')
                if len(c) != 14 or not co.dv_cnpj(c): continue
                r['cnpj'] = co.fmt_cnpj(c)
                occ.append(r)
    vistos, uni = set(), []
    for o in occ:
        if o['chave'] in vistos: continue
        vistos.add(o['chave']); uni.append(o)
    return uni


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', nargs='+')
    ap.add_argument('--dias', type=int, default=90)
    ap.add_argument('--saida', default='.')
    ap.add_argument('--excluir', help='excluir_cnpj.txt (raízes de 8 dígitos); Petrobras sempre excluída')
    ap.add_argument('--hoje', help='AAAA-MM-DD (padrão: hoje)')
    a = ap.parse_args()
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else dt.date.today()
    desde = (hoje - dt.timedelta(days=a.dias)).isoformat()
    os.makedirs(a.saida, exist_ok=True)
    excl = {'33000167'}
    if a.excluir and os.path.exists(a.excluir):
        for l in open(a.excluir, encoding='utf-8-sig'):
            d = re.sub(r'\D', '', l.split('#')[0])
            if len(d) >= 8: excl.add(d[:8])

    occ = ler(a.csv, desde)
    por = {}
    for o in occ: por.setdefault(o['cnpj'], []).append(o)
    print(f'{len(occ)} notificações de PJ desde {desde} · {len(por)} empresas (CNPJ com DV válido)')

    arq_cache = os.path.join(a.saida, 'cache_cadastro_inea.json')
    cache = json.load(open(arq_cache, encoding='utf-8')) if os.path.exists(arq_cache) else {}
    linhas, n = [], len(por)
    for i, (c, docs) in enumerate(sorted(por.items()), 1):
        r = cache.get(c)
        if r is None or r.get('_falhou'):
            r = co.cadastro(c) or {'_falhou': True}
            cache[c] = r; time.sleep(0.5)
            if i % 20 == 0: json.dump(cache, open(arq_cache, 'w', encoding='utf-8'), ensure_ascii=False)
        progresso(i, n, (r.get('razao_social') or docs[0].get('nome') or ''))
        r = dict(r)
        nat, cod_nat = r.get('natureza_juridica') or '', str(r.get('cod_nat') or '')
        e = dict(cnpj=c, razao_social=co.mascara(r.get('razao_social') or docs[0].get('nome') or ''),
                 situacao_receita=r.get('situacao_receita') or '', natureza_juridica=nat, natureza_codigo=cod_nat,
                 individual=bool(r.get('mei')) or cod_nat == '2135' or 'Individual' in nat or 'Empresário' in nat,
                 atividade=r.get('atividade') or '', municipio_sede=r.get('municipio_sede') or '',
                 telefone=re.sub(r'[^\d /]', '', r.get('telefone') or ''), email=(r.get('email') or '').strip().lower(),
                 porte=r.get('porte') or '')
        p = co.pontuar_occ(e, docs, hoje, None, excl)
        if r.get('_falhou'):
            faixa, pts, mot = 'Fora', '', 'sem cadastro público hoje (tentar de novo)'
        elif p['prioridade'].startswith('X'):
            faixa, pts, mot = 'Fora', '', p['motivos'].split(';')[0].replace('descartada: ', '')
        else:
            jz = ch.chance(e, docs, hoje, p['prioridade'])
            faixa, pts, mot = jz['chance_licenciamento'], jz['chance_pontos'], jz['chance_motivo']
        fis = [o for o in docs if o['chave'].startswith('INEA-DE')]
        lic = [o for o in docs if o['chave'].startswith('INEA-DL')]
        ativ = sorted({o['assunto'].split(' · atividade ')[1] for o in docs if ' · atividade ' in (o.get('assunto') or '')})
        tit = sorted({o['assunto'].split(' · ')[0].replace('Licenciamento - ', '') for o in lic})
        linhas.append(dict(
            faixa=faixa, pontos=pts, cnpj=c, razao_social=e['razao_social'], situacao_receita=e['situacao_receita'],
            natureza_juridica=nat, porte=e['porte'] + (' (individual/MEI)' if e['individual'] else ''),
            sede=e['municipio_sede'], tem_telefone='sim' if e['telefone'] else 'não', tem_email='sim' if e['email'] else 'não',
            telefone=e['telefone'], email=e['email'],
            notif_fiscalizacao=len(fis), notif_fiscalizacao_veicular=sum('SERVCPV' in (o.get('assunto') or '') for o in fis),
            notif_licenciamento=len(lic), instrumentos_licenciamento=' | '.join(tit)[:300],
            ultima_publicacao=max(o['data_documento'][:10] for o in docs),
            atividades_inea=' | '.join(ativ)[:400], cnae_receita=e['atividade'],
            motivo=mot, numeros=' | '.join(sorted({o.get('numero') or '' for o in docs}))[:300],
            fonte='Diário Eletrônico do INEA (diarioeletronico.inea.rj.gov.br), edições citadas em cada notificação',
            fonte_cadastro=r.get('fonte_cadastro') or ''))
    json.dump(cache, open(arq_cache, 'w', encoding='utf-8'), ensure_ascii=False)
    print()

    ordem = {'Alta': 0, 'Média': 1, 'Baixa': 2, 'Fora': 3}
    linhas.sort(key=lambda l: (ordem[l['faixa']], -(l['pontos'] or 0), l['razao_social']))
    stamp = f'{hoje.isoformat()}_{time.strftime("%H%M")}'
    arq = os.path.join(a.saida, f'juizo_inea_{a.dias}dias_{stamp}.csv')
    with open(arq, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=';'); w.writeheader(); w.writerows(linhas)
    cont = {k: sum(1 for l in linhas if l['faixa'] == k) for k in ordem}
    motf = {}
    for l in linhas:
        if l['faixa'] == 'Fora': k = re.sub(r'\(.*', '', l['motivo']).strip(); motf[k] = motf.get(k, 0) + 1
    md = [f'# Juízo de licenciamento: notificações do INEA ({a.dias} dias, {desde} a {hoje.isoformat()})', '',
          f'{len(occ)} notificações de pessoa jurídica (CNPJ com DV válido) · {len(linhas)} empresas', '',
          f'**Alta {cont["Alta"]} · Média {cont["Média"]} · Baixa {cont["Baixa"]} · Fora {cont["Fora"]}**', '',
          'Fora (não vão ao painel): ' + '; '.join(f'{k}: {v}' for k, v in sorted(motf.items(), key=lambda x: -x[1])), '',
          'FATO: cada empresa teve notificação publicada no Diário Eletrônico do INEA. Notificação não é auto de infração nem multa;',
          'a de licenciamento é exigência num pedido de licença. Município do INEA = endereço do interessado.',
          'HIPÓTESE (comercial): faixa Alta/Média = mais chance de contratar assessoria de licenciamento. Não é acusação.', '']
    for fx in ('Alta', 'Média'):
        md += [f'## {fx}', '']
        for l in [l for l in linhas if l['faixa'] == fx]:
            md.append(f"- **{l['razao_social']}** ({l['cnpj']}) | {l['pontos']} pts | {l['sede']} | fisc {l['notif_fiscalizacao']} · lic {l['notif_licenciamento']} | última {l['ultima_publicacao']}")
            md.append(f"  - {l['motivo']}")
        md.append('')
    arq_md = arq[:-4] + '.md'
    open(arq_md, 'w', encoding='utf-8').write('\n'.join(md))
    print(f'Alta {cont["Alta"]} · Média {cont["Média"]} · Baixa {cont["Baixa"]} · Fora {cont["Fora"]}')
    print('Fora: ' + '; '.join(f'{k}: {v}' for k, v in motf.items()))
    print(f'Relatório: {arq}\n           {arq_md}')
    print(f'Tempo total: {(time.time() - INICIO) / 60:.1f} min')
    try:
        import winsound; winsound.MessageBeep()
    except Exception:
        print('\a', end='')


if __name__ == '__main__':
    main()
