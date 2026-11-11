"""Sonda 11/11/2026: acha no código público (JS) do portal GeoSiap de Japeri o endereço de download das publicações,
e lê a página do VR Destaque (Volta Redonda). Só GET em página pública."""
import re, urllib.request, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40)
        return r.status, r.read(8_000_000).decode('utf-8', 'replace')
    except Exception as e:
        return 0, str(e)[:200]
B = 'https://japeri.geosiap.net.br/portal-transparencia/'
st, h = get(B + 'publicacoes?id_publicacao_tipo=7')
for s in re.findall(r'src="([^"]+\.js)"', h):
    st2, js = get(B + s.lstrip('/') if not s.startswith('http') else s)
    for m in re.finditer(r'publicac', js):
        print(json.dumps({'js': s, 'trecho': js[max(0, m.start() - 150): m.start() + 200]}, ensure_ascii=False))
for u in ['http://www2.voltaredonda.rj.gov.br/vrdestaque/13-interno/94-vrdestaque/', 'https://www2.voltaredonda.rj.gov.br/vrdestaque/13-geral/94-vrdestaque']:
    st, h = get(u)
    print(json.dumps({'url': u, 'st': st, 'tam': len(h), 'links': list(dict.fromkeys(re.findall(r'href="([^"]+)"', h)))[:80],
                      'texto': re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))[:1500]}, ensure_ascii=False))
