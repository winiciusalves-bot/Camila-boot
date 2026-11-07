#!/usr/bin/env python3
"""
Ambiental Costa · Leitura dos diários oficiais municipais do RJ baixados pelos
raspadores abertos do Querido Diário (github.com/okfn-brasil/querido-diario, licença MIT).

Não usa a API do Querido Diário: os PDFs vêm direto dos sites das prefeituras.
Procura, em cada edição:
  (a) CNPJ de empresa que já está na nossa base (Supabase);
  (b) termos ambientais (licença, auto de infração, embargo...) e os CNPJs citados perto deles.
Tudo o que sai daqui é INDÍCIO: menção em diário não é condenação nem prova de irregularidade.
Só (a) vai para o banco (tabela ocorrencias, nivel INDICIO, não pontua). O resto fica no relatório CSV.

Uso: python -I coletor/diarios_rj.py <pasta_jsonl> <pasta_saida> [--sem-supabase]
"""
import csv, datetime as dt, glob, json, os, re, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from coletar import Supabase, dv_cnpj, mascara, sem_acento, log   # mesmas regras do coletor diário

TERMOS = [
    r'auto de infra[cç][aã]o', r'licen[cç]a ambiental', r'licenciamento ambiental', r'licen[cç]a (?:previa|pr[eé]via|de instala[cç][aã]o|de opera[cç][aã]o)',
    r'embargo', r'multa ambiental', r'infra[cç][aã]o ambiental', r'crime ambiental', r'dano ambiental', r'supress[aã]o de vegeta[cç][aã]o',
    r'termo de ajustamento de conduta', r'secretaria (?:municipal )?de (?:meio )?ambiente', r'\bINEA\b', r'interdi[cç][aã]o',
    r'notifica[cç][aã]o ambiental', r'compensa[cç][aã]o ambiental', r'\bPRAD\b', r'estudo de impacto ambiental', r'\bEIA\b',
]
RX_TERMO = re.compile('|'.join(TERMOS), re.I)
RX_CNPJ = re.compile(r'(?<!\d)(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?!\d)')
JANELA = 250


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


def municipio_de(arq):
    n = os.path.basename(arq).replace('.jsonl', '').replace('rj_', '')
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

    achados, resumo, t0 = [], {}, time.time()
    raiz_arquivos = os.environ.get('FILES_STORE', 'data')
    for k, ed in enumerate(edicoes, 1):
        r = resumo.setdefault(ed['municipio'], dict(edicoes=0, com_texto=0, cnpj_base=0, termos=0))
        r['edicoes'] += 1
        pdf = os.path.join(raiz_arquivos, ed['caminho'] or '')
        txt = ''
        if ed['caminho'] and os.path.exists(pdf):
            try:
                txt = subprocess.run(['pdftotext', '-layout', '-q', pdf, '-'], capture_output=True, timeout=120).stdout.decode('utf-8', 'ignore')
            except Exception: txt = ''
        if txt.strip(): r['com_texto'] += 1
        cn = cnpjs_em(txt)
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

    # resumo em Markdown (vai para a página da execução no GitHub)
    linhas = ['# Diários oficiais municipais do RJ', '',
              f'Coleta em {hoje:%d/%m/%Y}. Fonte: sites das prefeituras, lidos com os raspadores abertos do Querido Diário (MIT). '
              'Tudo aqui é **INDÍCIO**: menção em diário não é condenação nem prova de irregularidade; leia o ato.', '',
              '| Município | Edições | Com texto | CNPJ da base | Termos ambientais |', '|---|---:|---:|---:|---:|']
    for mun, r in sorted(resumo.items()):
        linhas.append(f"| {mun} | {r['edicoes']} | {r['com_texto']} | {r['cnpj_base']} | {r['termos']} |")
    base_hits = [a for a in uniq if a['tipo'] == 'CNPJ da base']
    perto = [a for a in uniq if a['tipo'] == 'Termo ambiental + CNPJ']
    linhas += ['', f'**Empresas da base citadas:** {len(base_hits)} · **CNPJs perto de termo ambiental:** {len(perto)} · '
               f'**Trechos com termo ambiental:** {sum(1 for a in uniq if a["tipo"].startswith("Termo"))}', '']
    for a in (base_hits + perto)[:40]:
        linhas.append(f"- {a['municipio']} {a['data']} · {a['tipo']} · {a['cnpj']} {a['empresa']} · “{a['trecho'][:160]}…” · [PDF]({a['url']})")
    open(os.path.join(saida, 'resumo.md'), 'w', encoding='utf-8').write('\n'.join(linhas) + '\n')

    # (a) vai para o banco como INDÍCIO (chave igual à da base do Radar: DOM|cnpj|data|link)
    if sb and base_hits:
        occ = [dict(chave=f"DOM|{a['cnpj']}|{a['data']}|{a['url']}", fonte='Diário Oficial Municipal (raspadores Querido Diário)',
                    orgao=f"PREFEITURA {a['municipio'].upper()}", tipo_documento='MENCAO NO DOM', numero=str(a['edicao']), processo='',
                    data_documento=a['data'], situacao='INDICIO - ler o ato', cnpj=a['cnpj'], nome=a['empresa'], municipio=a['municipio'],
                    descricao=a['trecho'], nivel='INDICIO', link_fonte=a['url'], ultima_coleta=hoje.isoformat(), origem='coletor-diarios')
               for a in base_hits]
        sb.upsert('ocorrencias', occ, 'chave')
        log(f'{len(occ)} menção(ões) gravada(s) como INDÍCIO na tabela ocorrencias')
    log(f'FIM: {len(edicoes)} edições, {len(uniq)} achados (CSV e resumo em {saida})')
    print('\a')


if __name__ == '__main__':
    main()
