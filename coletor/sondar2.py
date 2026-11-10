"""Reteste da API do Querido Diário (10/11/2026), do GitHub: handshake TLS, versão/cifra e uma consulta."""
import ssl, socket, urllib.request, json
for host in ['api.queridodiario.ok.org.br', 'queridodiario.ok.org.br', 'docs.queridodiario.ok.org.br']:
    try:
        with socket.create_connection((host, 443), timeout=20) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname=host) as t:
                print('TLS OK', host, t.version(), t.cipher()[0])
    except Exception as e:
        print('TLS FALHA', host, type(e).__name__, str(e)[:160])
for u in ['https://api.queridodiario.ok.org.br/gazettes?territory_ids=3304557&size=1', 'https://queridodiario.ok.org.br/api/gazettes?territory_ids=3304557&size=1', 'https://api.queridodiario.ok.org.br/docs']:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30)
        print('HTTP', r.status, u, r.read(400).decode('utf-8', 'replace').replace('\n', ' '))
    except Exception as e:
        print('HTTP FALHA', u, type(e).__name__, str(e)[:160])
