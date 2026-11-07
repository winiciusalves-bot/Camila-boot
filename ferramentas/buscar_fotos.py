# Busca fotos de uso livre para o site (Wikimedia Commons e Unsplash), baixa em tamanho web e
# guarda a licença e o autor de cada uma. Roda no GitHub Actions (a nuvem do Claude não acessa esses sites).
import json, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw

UA = {'User-Agent': 'AmbientalCostaSite/1.0 (busca de fotos com licença livre)'}
OUT = sys.argv[1] if len(sys.argv) > 1 else 'fotos-candidatas'
os.makedirs(OUT, exist_ok=True)
BUSCAS = [l.strip() for l in open('ferramentas/fotos_buscas.txt', encoding='utf-8') if l.strip() and not l.startswith('#')]

def get(url, bin=False):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
    return r if bin else json.loads(r)

fichas = []
for linha in BUSCAS:
    fonte, q = linha.split('|', 1)
    try:
        if fonte == 'commons':
            u = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(dict(action='query', format='json', generator='search', gsrsearch='filetype:bitmap ' + q, gsrnamespace=6, gsrlimit=8, prop='imageinfo', iiprop='url|extmetadata|size', iiurlwidth=1600))
            for p in (get(u).get('query', {}).get('pages', {}) or {}).values():
                ii = p['imageinfo'][0]; md = ii.get('extmetadata', {})
                lic = md.get('LicenseShortName', {}).get('value', '')
                if ii.get('width', 0) < 1400 or not re.search(r'CC0|CC BY|Public domain', lic, re.I): continue
                fichas.append(dict(fonte='Wikimedia Commons', busca=q, url=ii.get('thumburl') or ii['url'], pagina=ii.get('descriptionurl'), licenca=lic,
                                   autor=re.sub('<[^>]+>', '', md.get('Artist', {}).get('value', ''))[:120], titulo=p['title']))
        else:
            u = 'https://unsplash.com/napi/search/photos?' + urllib.parse.urlencode(dict(query=q, per_page=8, orientation='landscape'))
            for r in get(u).get('results', []):
                if r.get('premium') or r.get('plus'): continue
                fichas.append(dict(fonte='Unsplash', busca=q, url=r['urls']['raw'] + '&w=1600&q=75&fm=jpg&fit=max', pagina=r['links']['html'], licenca='Unsplash License',
                                   autor=(r.get('user') or {}).get('name', ''), titulo=r.get('alt_description') or r.get('description') or ''))
    except Exception as e:
        print('falhou', linha, e)
    time.sleep(1)

ok = []
for i, f in enumerate(fichas):
    nome = f'{i:03d}.jpg'
    try:
        open(os.path.join(OUT, nome), 'wb').write(get(f['url'], bin=True)); f['arquivo'] = nome; ok.append(f)
    except Exception as e:
        print('não baixou', f['url'], e)
    time.sleep(0.5)
json.dump(ok, open(os.path.join(OUT, 'fotos.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# folhas de contato (24 por folha) para escolher
for k in range(0, len(ok), 24):
    folha = Image.new('RGB', (6 * 320, 4 * 230), 'white'); d = ImageDraw.Draw(folha)
    for j, f in enumerate(ok[k:k + 24]):
        try:
            im = Image.open(os.path.join(OUT, f['arquivo'])).convert('RGB'); im.thumbnail((310, 200))
            x, y = (j % 6) * 320 + 5, (j // 6) * 230 + 5
            folha.paste(im, (x, y)); d.text((x, y + 203), f['arquivo'] + ' ' + f['busca'][:30], fill='black')
        except Exception as e:
            print('folha', f['arquivo'], e)
    folha.save(os.path.join(OUT, f'folha-{k // 24 + 1}.jpg'), quality=80)
print(len(ok), 'fotos baixadas')
