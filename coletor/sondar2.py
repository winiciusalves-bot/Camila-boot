"""Paty do Alferes (10/11/2026): 255 edições lidas e 0 atos. Ver se o texto extraído do PDF é legível."""
import urllib.request, subprocess, re
U = 'https://patydoalferes.rj.gov.br/wp-content/uploads/auto-publication/diario-oficial/2026/D.O.%204852%20-%2009.11.2026.pdf'
b = urllib.request.urlopen(urllib.request.Request(U, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()
open('/tmp/p.pdf', 'wb').write(b)
print('bytes', len(b), b[:8])
print(subprocess.run(['pdfinfo', '/tmp/p.pdf'], capture_output=True, text=True).stdout)
t = subprocess.run(['pdftotext', '-q', '/tmp/p.pdf', '-'], capture_output=True).stdout.decode('utf-8', 'ignore')
print('chars', len(t), 'letras', len(re.findall(r'[A-Za-zÀ-ú]', t)), 'cnpj', len(re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', t)))
print(re.sub(r'\d', '#', re.sub(r'\s+', ' ', t))[:900])   # dígitos trocados por # (log é público)
