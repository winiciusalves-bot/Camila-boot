"""Cabo Frio: testa se arquivos_download.php?id=N&pg=diariooficial entrega o PDF direto (sem captcha) e o que vem no cabeçalho.
Padrão indicado pelo usuário em 10/11/2026. Só GET de link público; se aparecer captcha/bloqueio, para."""
import urllib.request, re, json
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
for i in [2054, 2024, 2055, 2056, 2060, 2070, 2000, 1900, 1700]:
    u = f'https://portal.cabofrio.rj.gov.br/arquivos_download.php?id={i}&pg=diariooficial'
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40)
        b = r.read(400_000); h = dict(r.headers); st = r.status
    except urllib.error.HTTPError as e:
        b, h, st = b'', dict(e.headers or {}), e.code
    except Exception as e:
        b, h, st = str(e).encode(), {}, 0
    eh_pdf = b[:5] == b'%PDF-'
    datas = re.findall(rb'(\d{2}/\d{2}/\d{4})', b[:200_000])[:3] if eh_pdf else []
    print(json.dumps({'id': i, 'st': st, 'tipo': h.get('Content-Type'), 'disp': h.get('Content-Disposition'),
        'tam': h.get('Content-Length') or len(b), 'pdf': eh_pdf, 'captcha': bool(re.search(rb'captcha|recaptcha|cf-chl', b, re.I)),
        'inicio': '' if eh_pdf else b[:300].decode('utf-8', 'replace'), 'datas_texto_cru': [d.decode() for d in datas]}, ensure_ascii=False))
