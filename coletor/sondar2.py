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
for s_ in re.findall(r'src="([^"]+\.js)"', h):
    st2, js = get(B + s_.lstrip('/'))
    for m in re.finditer(r'\b15:"([0-9a-f]{16,24})"', js):
        for nome in ['15.' + m.group(1) + '.js', '15-es2015.' + m.group(1) + '.js', '15-es5.' + m.group(1) + '.js']:
            st3, ch = get(B + nome)
            print(json.dumps({'js': nome, 'trecho': 'st=%s tam=%s' % (st3, len(ch))}))
            for k in re.finditer(r'download|arquivo|/api|window.open|\.pdf', ch):
                print(json.dumps({'js': nome, 'trecho': ch[max(0, k.start() - 200): k.start() + 200]}, ensure_ascii=False))
