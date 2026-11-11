"""Testa, do GitHub Actions, uma lista de endereços achados por busca na web (10/11/2026): status, tamanho,
se é índice de pasta, quantos PDFs e exemplos. Só GET em página pública."""
import re, sys, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
URLS = [
 'https://www.pmsmm.rj.gov.br/transparencia/publicacoes_oficiais/diario_oficial_eletronico/',
 'https://www.pmsmm.rj.gov.br/transparencia/publicacoes_oficiais/diario_oficial_eletronico/2026/',
 'https://www.pmsmm.rj.gov.br/transparencia/publicacoes_oficiais/diario_oficial_eletronico/2026/outubro/',
 'https://www.pmsmm.rj.gov.br/',
 'https://ssalto.rj.gov.br/',
 'https://ssalto.rj.gov.br/diario-oficial/',
 'https://ssalto.rj.gov.br/wp-json/wp/v2/pages?search=oficial&per_page=10&_fields=link,title',
 'https://www.cambuci.rj.gov.br.br/',
 'https://cambuci.rj.gov.br/',
 'https://macuco.rj.gov.br/',
 'https://lajedomuriae.rj.gov.br/',
 'https://www.pmlm.rj.gov.br/',
 'https://bomjesus.rj.gov.br/',
 'https://www.bomjesus.rj.gov.br/',
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
                      'inicio': t[:200] if st != 200 else '', 'json': t[:6000] if t.lstrip()[:1] in '[{' or 'controller' in t[:3000] else '', 'x': '' if t.lstrip()[:1] in '[{' else '', 'diar': list(dict.fromkeys(re.findall(r'href=["\']([^"\']+)|<loc>([^<]+)', t)))[:200], 'storage': list(dict.fromkeys(re.findall(r'["\'](\S*(?:storage|arquivos|edicao|edicoes|download)\S*?)["\']', t, re.I)))[:8]}, ensure_ascii=False))
