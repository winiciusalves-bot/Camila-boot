"""Testa, do GitHub Actions, uma lista de endereços achados por busca na web (10/11/2026): status, tamanho,
se é índice de pasta, quantos PDFs e exemplos. Só GET em página pública."""
import re, sys, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
URLS = [
 'https://sjb.rj.gov.br/arquivos/diario_oficial/075_26_do-30042026-ed075.pdf',
 'https://sjb.rj.gov.br/arquivos/diario_oficial/',
 'https://sjb.rj.gov.br/diario-oficial',
 'https://sjb.rj.gov.br/diario_oficial',
 'https://sjb.rj.gov.br/',
 'https://pmsfi.rj.gov.br/wp-json/wp/v2/media?search=DO&per_page=10&orderby=date&order=desc&_fields=date,title,source_url',
 'https://pmsfi.rj.gov.br/',
 'https://guapimirim.rj.gov.br/',
 'https://guapimirim.rj.gov.br/wp-content/uploads/2026/07/Diario-1903.pdf',
 'https://www.campos.rj.gov.br/app/assets/diario-oficial/link/7723',
 'https://araruama.rj.gov.br/storage/content/publicacoes/diario-oficial/39588/arquivos/6a91798935506w83oh.pdf',
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
                      'inicio': t[:200] if st != 200 else '', 'json': t[:1800] if t.lstrip().startswith('[') else '', 'storage': list(dict.fromkeys(re.findall(r'["\'](\S*(?:storage|arquivos|edicao|edicoes|download)\S*?)["\']', t, re.I)))[:8]}, ensure_ascii=False))
