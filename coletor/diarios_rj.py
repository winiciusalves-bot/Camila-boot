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
import shutil, tempfile

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
            return '\n'.join(ex.map(um, imgs)), len(imgs), tot
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def municipio_de(arq):
    n = os.path.basename(arq).replace('.jsonl', '').replace('rj_', '').replace('_v2', '')
    if n == 'aemerj': return 'AEMERJ (vários municípios)'
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
    raiz_arquivos = os.environ.get('FILES_STORE', 'data')
    for k, ed in enumerate(edicoes, 1):
        r = resumo.setdefault(ed['municipio'], dict(edicoes=0, com_texto=0, ocr=0, cnpj_base=0, termos=0))
        r['edicoes'] += 1
        pdf = os.path.join(raiz_arquivos, ed['caminho'] or '')
        txt = ''
        if ed['caminho'] and os.path.exists(pdf):
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
            if r and str(r.get('cod_nat') or '').startswith('1'):    # natureza jurídica 1xxx = administração pública (fundo, prefeitura...)
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
            metodo=f'janela de {os.environ.get("DIAS", "?")} dia(s); pdftotext e OCR (tesseract por, até {OCR_MAX_PAG} pág./edição); CNPJ com DV válido; CPF mascarado; tudo INDÍCIO',
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
