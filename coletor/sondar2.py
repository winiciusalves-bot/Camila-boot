"""Sondagem 3 (10/11/2026): Magé (links de boletim na home), Nova Friburgo (subdomínio do diário com cadeia SSL incompleta;
o Scrapy já não verifica certificado, então leitura igual à do robô), Tribuna dos Municípios (quais prefeituras publicam lá)."""
import re, ssl, json, urllib.request, io, subprocess, sys, collections
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
SEM = ssl._create_unverified_context()
def get(u, n=4_000_000, ctx=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40, context=ctx)
        return r.status, r.read(n), r.geturl()
    except urllib.error.HTTPError as e: return e.code, b'', u
    except Exception as e: return 0, str(e)[:150].encode(), u
st, b, _ = get('https://mage.rj.gov.br/'); t = b.decode('utf-8', 'replace')
print('MAGE links', st, list(dict.fromkeys(re.findall(r'href=["\']([^"\']*(?:bio|boletim|oficial|BIO)[^"\']*)', t, re.I)))[:15])
for u in ['https://diario.novafriburgo.rj.gov.br/diario-oficial', 'https://diario.novafriburgo.rj.gov.br/']:
    st, b, fin = get(u, ctx=SEM); t = b.decode('utf-8', 'replace')
    print('NF', u, st, fin, len(t), re.search(r'<title>(.*?)</title>', t, re.S).group(1)[:80] if '<title>' in t else '')
    print('   pdf/links', list(dict.fromkeys(re.findall(r'(?:href|src|url)=?["\']?([^"\'\s>]*(?:\.pdf|download|edicao|edicoes|api/|arquivo)[^"\'\s>]*)', t, re.I)))[:20])
    print('   trecho', re.sub(r'\s+', ' ', re.sub(r'<script.*?</script>|<style.*?</style>|<[^>]+>', ' ', t, flags=re.S))[:600])
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'pypdf'], check=False)
from pypdf import PdfReader
st, b, _ = get('https://tribunadosmunicipios.com.br/wp-content/uploads/2026/11/edicao-digital-3507.pdf', 60_000_000)
print('TRIBUNA', st, len(b))
if b[:5] == b'%PDF-':
    txt = '\n'.join((p.extract_text() or '') for p in PdfReader(io.BytesIO(b)).pages)
    print('  paginas/texto', len(txt))
    c = collections.Counter(m.upper() for m in re.findall(r'(?:PREFEITURA|MUNIC[IÍ]PIO|C[AÂ]MARA MUNICIPAL)\s+(?:MUNICIPAL\s+)?D[EOA]S?\s+([A-ZÀ-Ú][A-Za-zÀ-ú]+(?:\s+(?:d[eoa]s?\s+)?[A-ZÀ-Ú][A-Za-zÀ-ú]+){0,3})', txt))
    print('  entes citados', c.most_common(30))
    print('  cnpjs', len(re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', txt)), ' editais/avisos', len(re.findall(r'AVISO|EDITAL|EXTRATO', txt)))
