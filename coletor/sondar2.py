"""Reteste da API do Querido Diário (11/11/2026): TLS e o que existe do RJ (municípios e edições recentes)."""
import ssl, socket, urllib.request, json
H = 'api.queridodiario.ok.org.br'
try:
    with socket.create_connection((H, 443), timeout=20) as s:
        with ssl.create_default_context().wrap_socket(s, server_hostname=H) as t:
            print('TLS OK', t.version(), t.cipher()[0])
except Exception as e:
    print('TLS FALHA', type(e).__name__, str(e)[:160])
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=40)
        return r.status, json.loads(r.read())
    except Exception as e:
        return 0, f'{type(e).__name__}: {str(e)[:160]}'
st, cid = get(f'https://{H}/cities?city_name=')
rj = [c for c in cid.get('cities', []) if c.get('state_code') == 'RJ'] if isinstance(cid, dict) else []
print('cidades', st, len(rj) if rj else cid)
ok = [c for c in rj if str(c.get('level')) not in ('None', '0')]
print('RJ com nível>0:', len(ok), sorted(c['territory_name'] for c in ok))
for q in ['', '&published_since=2026-10-01']:
    st, g = get(f'https://{H}/gazettes?' + '&'.join('territory_ids=' + c['territory_id'] for c in rj) + f'&size=5&sort_by=descending_date{q}')
    print('gazettes', q, st, g.get('total_gazettes') if isinstance(g, dict) else g)
    if isinstance(g, dict):
        for x in g.get('gazettes', [])[:5]: print('  ', x.get('date'), x.get('territory_name'), x.get('url', '')[:90])
