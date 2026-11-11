"""Testa, do GitHub Actions, uma lista de endereços achados por busca na web (10/11/2026): status, tamanho,
se é índice de pasta, quantos PDFs e exemplos. Só GET em página pública."""
import re, sys, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
URLS = [
 'https://guapimirim.rj.gov.br/wp-json/wp/v2/media?search=Diario&per_page=10&orderby=date&order=desc&_fields=date,title,source_url',
 'https://guapimirim.rj.gov.br/diario-oficial/',
 'https://mage.rj.gov.br/wp-content/uploads/BIO/2026/BIO751.pdf',
 'https://mage.rj.gov.br/wp-content/uploads/BIO/2026/BIO760.pdf',
 'https://mage.rj.gov.br/wp-content/uploads/BIO/2026/BIO780.pdf',
 'https://sjb.rj.gov.br/arquivos/diario_oficial/075_26_do-30042026-ed075.pdf',
 'https://sjb.rj.gov.br/diario-oficial',
 'https://sjb.rj.gov.br/',
 'https://www.petropolis.rj.gov.br/gap/diario-oficial/diarios/2026/janeiro/7318.pdf',
 'https://www.petropolis.rj.gov.br/gap/diario-oficial/',
]
for u in URLS:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        t = r.read(3_000_000) if 'pdf' not in (r.headers.get('Content-Type') or '') else ('PDF ' + str(r.headers.get('Content-Length')) + ' ' + str(r.headers.get('Last-Modified'))).decode('utf-8', 'replace'); st = r.status; fin = r.geturl()
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
