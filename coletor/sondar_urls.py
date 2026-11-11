"""Testa, do GitHub Actions, uma lista de endereços achados por busca na web (10/11/2026): status, tamanho,
se é índice de pasta, quantos PDFs e exemplos. Só GET em página pública."""
import re, sys, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
URLS = [
 'https://plenussistemas.dioenet.com.br/list/angra-dos-reis',
 'https://plenussistemas.dioenet.com.br/list/barra-do-pirai',
 'https://plenussistemas.dioenet.com.br/list/barra-mansa',
 'https://plenussistemas.dioenet.com.br/list/bom-jesus-do-itabapoana',
 'https://plenussistemas.dioenet.com.br/list/cachoeiras-de-macacu',
 'https://plenussistemas.dioenet.com.br/list/cambuci',
 'https://plenussistemas.dioenet.com.br/list/cantagalo',
 'https://plenussistemas.dioenet.com.br/list/carapebus',
 'https://plenussistemas.dioenet.com.br/list/cardoso-moreira',
 'https://plenussistemas.dioenet.com.br/list/conceicao-de-macabu',
 'https://plenussistemas.dioenet.com.br/list/italva',
 'https://plenussistemas.dioenet.com.br/list/itaocara',
 'https://plenussistemas.dioenet.com.br/list/japeri',
 'https://plenussistemas.dioenet.com.br/list/laje-do-muriae',
 'https://plenussistemas.dioenet.com.br/list/macuco',
 'https://plenussistemas.dioenet.com.br/list/mage',
 'https://plenussistemas.dioenet.com.br/list/mangaratiba',
 'https://plenussistemas.dioenet.com.br/list/natividade',
 'https://plenussistemas.dioenet.com.br/list/paraty',
 'https://plenussistemas.dioenet.com.br/list/petropolis',
 'https://plenussistemas.dioenet.com.br/list/pinheiral',
 'https://plenussistemas.dioenet.com.br/list/pirai',
 'https://plenussistemas.dioenet.com.br/list/porciuncula',
 'https://plenussistemas.dioenet.com.br/list/porto-real',
 'https://plenussistemas.dioenet.com.br/list/resende',
 'https://plenussistemas.dioenet.com.br/list/rio-das-flores',
 'https://plenussistemas.dioenet.com.br/list/santa-maria-madalena',
 'https://plenussistemas.dioenet.com.br/list/santo-antonio-de-padua',
 'https://plenussistemas.dioenet.com.br/list/sao-jose-de-uba',
 'https://plenussistemas.dioenet.com.br/list/sao-sebastiao-do-alto',
 'https://plenussistemas.dioenet.com.br/list/silva-jardim',
 'https://plenussistemas.dioenet.com.br/list/teresopolis',
 'https://plenussistemas.dioenet.com.br/list/tres-rios',
 'https://plenussistemas.dioenet.com.br/list/valenca',
 'https://plenussistemas.dioenet.com.br/list/volta-redonda',
]
for u in URLS:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        b = r.read(3_000_000); st = r.status; fin = r.geturl()
        t = ('PDF ' + str(len(b)) + ' bytes ' + str(r.headers.get('Last-Modified'))) if b[:5] == b'%PDF-' else b.decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        t, st, fin = '', e.code, u
    except Exception as e:
        t, st, fin = f'{type(e).__name__}: {str(e)[:100]}', 0, u
    pdfs = re.findall(r'(?:href=["\']|"source_url":")([^"\']+?\.pdf)', t, re.I)
    tit = re.search(r'<title>(.*?)</title>', t, re.I | re.S)
    print(json.dumps({'url': u, 'st': st, 'final': fin, 'tam': len(t), 'titulo': (tit.group(1).strip()[:80] if tit else ''),
                      'indice': bool(re.search(r'Index of|Parent Directory', t)), 'n_pdf': len(pdfs),
                      'ex': [p.replace('\\/', '/') for p in pdfs[:4]], 'diario': list(dict.fromkeys(re.findall(r'href=["\']([^"\']*(?:diario|boletim|jornal-oficial|publicac)[^"\']*)', t, re.I)))[:5],
                      'inicio': t[:200] if st != 200 else '', 'json': t[:6000] if t.lstrip()[:1] in '[{' or 'controller' in t[:3000] else '', 'x': '' if t.lstrip()[:1] in '[{' else '', 'diar': list(dict.fromkeys(re.findall(r'.{0,120}[Dd]i[aá]rio.{0,160}', t)))[:12], 'storage': list(dict.fromkeys(re.findall(r'["\'](\S*(?:storage|arquivos|edicao|edicoes|download)\S*?)["\']', t, re.I)))[:8]}, ensure_ascii=False))
