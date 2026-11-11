"""Testa, do GitHub Actions, uma lista de endereços achados por busca na web (10/11/2026): status, tamanho,
se é índice de pasta, quantos PDFs e exemplos. Só GET em página pública."""
import re, sys, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
URLS = [
 'https://sfi.diariooficial.pmsfi.rj.gov.br/api/v1/tenant/sfi/edicoes/94897c7a-d808-4be2-ac3d-6a1dbdd8eedd',
 'https://sfi.diariooficial.pmsfi.rj.gov.br/api/v1/tenant/sfi/edicoes?size=3&page=2',
 'https://sfi.diariooficial.pmsfi.rj.gov.br/api/v1/tenant/sfi/edicoes/94897c7a-d808-4be2-ac3d-6a1dbdd8eedd/pdf',
 'https://sfi.diariooficial.pmsfi.rj.gov.br/api/v1/tenant/sfi/edicoes/94897c7a-d808-4be2-ac3d-6a1dbdd8eedd/download',
 'https://www.araruama.rj.gov.br/publicacoes/diario-oficial?page=2',
 'https://guapimirim.rj.gov.br/wp-json/wp/v2/search?search=Diario&per_page=5',
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
                      'inicio': t[:200] if st != 200 else '', 'json': t[:1800] if t.lstrip()[:1] in '[{' else '', 'storage': list(dict.fromkeys(re.findall(r'["\'](\S*(?:storage|arquivos|edicao|edicoes|download)\S*?)["\']', t, re.I)))[:8]}, ensure_ascii=False))
