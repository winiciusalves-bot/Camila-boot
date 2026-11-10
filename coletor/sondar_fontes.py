"""
Sondagem de fontes alternativas para os diários oficiais dos 92 municípios do RJ (10/11/2026).

Para cada município, testa (só leitura, sem login, sem captcha, sem contornar bloqueio):
  1. PNCP (Portal Nacional de Contratações Públicas, Lei 14.133): contratações publicadas nos últimos 30 dias,
     por órgão municipal. Dados estruturados, com CNPJ do órgão. É fonte federal, não depende do site da prefeitura.
  2. Site da prefeitura: abre a página inicial e procura links de "diário oficial", "boletim oficial", "jornal oficial".
  3. Plataformas que atendem várias prefeituras: Dioenet (Plenus), ADM Executivo, Portal da Transparência
     (rj.portaldatransparencia.com.br) e o padrão transparencia.<municipio>.rj.gov.br.

Saída: relatorio/fontes_municipios.csv e um resumo em Markdown.
"""
import csv, datetime as dt, json, os, re, sys, unicodedata
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

UA = 'Mozilla/5.0 (compatible; AmbientalCosta-Coletor/1.0; levantamento em dados abertos)'
RX_DIARIO = re.compile(r'(di[aá]rio\s+oficial|boletim\s+oficial|jornal\s+oficial|imprensa\s+oficial|\bJOM\b|\bDOM\b|di[aá]rio\s+eletr[oô]nico)', re.I)
RX_LINK = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def get(url, timeout=25, maxb=1_500_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read(maxb).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:
        return 0, url, f'ERRO {type(e).__name__}: {str(e)[:120]}'


def slug(nome, sep=''):
    s = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[^a-z0-9 ]", '', s)
    return s.replace(' ', sep)


def links_diario(base, html):
    out = []
    for href, txt in RX_LINK.findall(html or ''):
        t = re.sub(r'<[^>]+>', ' ', txt)
        if RX_DIARIO.search(t) or re.search(r'diario|boletim|jornal-oficial|\bjom\b|\bdom\b', href, re.I):
            out.append(urllib.parse.urljoin(base, href))
    return list(dict.fromkeys(out))[:5]


def desafio(html):
    return bool(re.search(r'cf-chl|turnstile|g-recaptcha|hcaptcha|captcha', html or '', re.I))


def municipios():
    """API do IBGE; se cair, a lista guardada (territories.csv do Querido Diário, códigos IBGE, RJ)."""
    st, _, txt = get('https://servicodados.ibge.gov.br/api/v1/localidades/estados/33/municipios', timeout=60)
    if st == 200:
        return [(str(m['id']), m['nome']) for m in json.loads(txt)]
    print(f'IBGE fora ({st} {txt[:80]}); usando coletor/municipios_rj.csv')
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'municipios_rj.csv'), encoding='utf-8') as f:
        return [(r['id'], r['name']) for r in csv.DictReader(f) if r['id'].startswith('33') and len(r['id']) == 7]


def pncp(dias=30):
    """{codigo_ibge: {'n': contratações, 'orgaos': {cnpj: nome}}} das esferas municipais do RJ."""
    fim = dt.date.today(); ini = fim - dt.timedelta(days=dias)
    res, log = {}, []
    for mod in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
        pag = 1
        while pag <= 40:
            q = urllib.parse.urlencode(dict(dataInicial=ini.strftime('%Y%m%d'), dataFinal=fim.strftime('%Y%m%d'),
                                            codigoModalidadeContratacao=mod, uf='RJ', pagina=pag, tamanhoPagina=50))
            st, _, txt = get(f'https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?{q}', timeout=60, maxb=20_000_000)
            if st == 204 or (st == 200 and not txt.strip()): break
            if st != 200:
                log.append(f'modalidade {mod} pág. {pag}: HTTP {st} {txt[:80]}'); break
            j = json.loads(txt)
            for c in j.get('data', []):
                u, o = c.get('unidadeOrgao') or {}, c.get('orgaoEntidade') or {}
                if o.get('esferaId') != 'M': continue
                r = res.setdefault(str(u.get('codigoIbge')), {'n': 0, 'orgaos': {}})
                r['n'] += 1; r['orgaos'][o.get('cnpj')] = o.get('razaoSocial')
            if pag >= (j.get('totalPaginas') or 1): break
            pag += 1
    return res, log


def sondar(m):
    cod, nome = m
    s, s_ = slug(nome), slug(nome, '-')
    r = {'codigo_ibge': cod, 'municipio': nome}
    # site da prefeitura
    for url in (f'https://www.{s}.rj.gov.br', f'https://{s}.rj.gov.br', f'https://prefeitura{s}.rj.gov.br'):
        st, fin, html = get(url)
        if st == 200:
            r.update(site=fin, site_captcha=desafio(html), site_links_diario=' | '.join(links_diario(fin, html))); break
        r['site'] = f'{url} -> {st or html[:60]}'
    # plataformas
    plats = {'dioenet': f'https://plenussistemas.dioenet.com.br/list/{s_}',
             'aexecutivo': f'https://{s}.aexecutivo.com.br',
             'portaldatransparencia': f'https://rj.portaldatransparencia.com.br/prefeitura/{s}/',
             'transparencia_sub': f'https://transparencia.{s}.rj.gov.br'}
    for k, url in plats.items():
        st, fin, html = get(url)
        ok = st == 200 and len(html) > 2000 and slug(nome)[:6] in slug(html[:200000])
        r[k] = f'{st}{" OK" if ok else ""}{" captcha" if desafio(html) else ""}'
    return r


def main(saida='relatorio'):
    os.makedirs(saida, exist_ok=True)
    ms = municipios()
    print(f'{len(ms)} municípios do RJ (IBGE)')
    pn, log = pncp()
    print(f'PNCP: {sum(v["n"] for v in pn.values())} contratações municipais em {len(pn)} municípios (30 dias)')
    for l in log[:10]: print('  PNCP', l)
    with ThreadPoolExecutor(12) as ex:
        linhas = list(ex.map(sondar, ms))
    for r in linhas:
        p = pn.get(r['codigo_ibge'], {'n': 0, 'orgaos': {}})
        r['pncp_30d'] = p['n']; r['pncp_orgaos'] = ' | '.join(f'{k} {v}' for k, v in list(p['orgaos'].items())[:4])
    cols = ['codigo_ibge', 'municipio', 'pncp_30d', 'pncp_orgaos', 'site', 'site_captcha', 'site_links_diario',
            'dioenet', 'aexecutivo', 'portaldatransparencia', 'transparencia_sub']
    with open(f'{saida}/fontes_municipios.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore'); w.writeheader(); w.writerows(linhas)
    com_pncp = sum(1 for r in linhas if r['pncp_30d'])
    com_link = sum(1 for r in linhas if r.get('site_links_diario'))
    md = [f'# Fontes alternativas — {dt.date.today()}', '',
          f'- Municípios: {len(linhas)}', f'- Com contratações no PNCP (30 dias): {com_pncp}',
          f'- Site da prefeitura com link de diário oficial: {com_link}', '',
          '| Município | PNCP 30d | Link de diário no site | Dioenet | ADM Exec. | Portal Transp. | transparencia. |', '|---|---:|---|---|---|---|---|']
    for r in sorted(linhas, key=lambda x: x['municipio']):
        md.append(f"| {r['municipio']} | {r['pncp_30d']} | {(r.get('site_links_diario') or '—')[:140]} | {r['dioenet']} | {r['aexecutivo']} | {r['portaldatransparencia']} | {r['transparencia_sub']} |")
    open(f'{saida}/fontes_municipios.md', 'w', encoding='utf-8').write('\n'.join(md))
    print('\n'.join(md))


if __name__ == '__main__':
    main(*(sys.argv[1:2] or []))
