"""Testa, do GitHub Actions, uma lista de endereços achados por busca na web (10/11/2026): status, tamanho,
se é índice de pasta, quantos PDFs e exemplos. Só GET em página pública."""
import re, sys, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
URLS = [
 'https://tribunadosmunicipios.com.br/wp-json/wp/v2/media?mime_type=application/pdf&per_page=5',
 'https://tribunadosmunicipios.com.br/',
 'https://tribunadosmunicipios.com.br/wp-content/uploads/2026/06/',
 'https://resende.rj.gov.br/conteudo/boletim_oficial/2026/',
 'https://resende.rj.gov.br/',
 'https://www.resende.rj.gov.br/boletim-oficial',
 'https://mage.rj.gov.br/wp-content/uploads/BIO/2026/',
 'https://mage.rj.gov.br/wp-json/wp/v2/media?search=BIO&per_page=5',
 'https://mage.rj.gov.br/',
 'https://transparencia.pirai.rj.gov.br/documentos/boletins_informativos/',
 'https://transparencia.pirai.rj.gov.br/',
 'https://www.araruama.rj.gov.br/publicacoes/diario-oficial',
 'https://pmnf.rj.gov.br/',
 'https://www.pmnf.rj.gov.br/diario-oficial',
 'https://sig.petropolis.rj.gov.br/',
 'https://www.petropolis.rj.gov.br/',
 'https://www.teresopolis.rj.gov.br/diario-oficial/',
 'https://www.teresopolis.rj.gov.br/wp-json/wp/v2/media?search=diario&per_page=5',
 'https://valenca.rj.gov.br/wp-json/wp/v2/media?mime_type=application/pdf&per_page=5',
 'https://digital.correiodamanha.com.br/',
]
for u in URLS:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        t = r.read(3_000_000).decode('utf-8', 'replace'); st = r.status; fin = r.geturl()
    except urllib.error.HTTPError as e:
        t, st, fin = '', e.code, u
    except Exception as e:
        t, st, fin = f'{type(e).__name__}: {str(e)[:100]}', 0, u
    pdfs = re.findall(r'(?:href=["\']|"source_url":")([^"\']+?\.pdf)', t, re.I)
    tit = re.search(r'<title>(.*?)</title>', t, re.I | re.S)
    print(json.dumps({'url': u, 'st': st, 'final': fin, 'tam': len(t), 'titulo': (tit.group(1).strip()[:80] if tit else ''),
                      'indice': bool(re.search(r'Index of|Parent Directory', t)), 'n_pdf': len(pdfs),
                      'ex': [p.replace('\\/', '/') for p in pdfs[:4]], 'diario': list(dict.fromkeys(re.findall(r'href=["\']([^"\']*(?:diario|boletim|jornal-oficial|publicac)[^"\']*)', t, re.I)))[:5],
                      'inicio': t[:200] if st != 200 else ''}, ensure_ascii=False))
