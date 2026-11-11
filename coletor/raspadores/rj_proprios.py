# Robôs próprios da Ambiental Costa para municípios do RJ cujo site mudou e o robô do Querido Diário
# deixou de achar as edições (conferido em 07/11/2026 com a sonda de sites). Mesmo formato de saída
# do Querido Diário (item Gazette). Só leem páginas públicas; não contornam captcha, bloqueio ou login.
import re
from datetime import date, datetime

import scrapy

from gazette.items import Gazette
from gazette.spiders.base import BaseGazetteSpider

MESES = {m: i for i, m in enumerate(
    ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'], 1)}


def _sem_acento(s):
    return s.lower().replace('ç', 'c').replace('ã', 'a').replace('á', 'a').replace('é', 'e')


def data_extenso(dia, mes, ano):
    m = MESES.get(_sem_acento(mes))
    return date(int(ano), m, int(dia)) if m else None


def texto(html):
    t = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))


class _Base(BaseGazetteSpider):
    def dentro(self, d):
        return d is not None and self.start_date <= d <= self.end_date


class RjCamposProprioSpider(_Base):
    """Campos dos Goytacazes: a página nova lista os PDFs direto (DO-ONLINE-<nº>-<dia>-de-<mês>-de-<ano>...pdf)."""
    name = 'rj_campos_dos_goytacazes_v2'
    TERRITORY_ID = '3301009'
    allowed_domains = ['campos.rj.gov.br', 'www.campos.rj.gov.br']
    start_date = date(2013, 11, 1)
    start_urls = ['https://campos.rj.gov.br/diario-oficial/']
    RX = re.compile(r'href="([^"]*DO-ONLINE-(\d+)-(\d{1,2})-de-([a-zç]+)-de-(\d{4})([^"]*)\.pdf)"', re.I)

    def parse(self, response):
        vistos = set()
        for url, num, dia, mes, ano, resto in self.RX.findall(response.text):
            d = data_extenso(dia, mes, ano)
            if url in vistos or not self.dentro(d):
                continue
            vistos.add(url)
            yield Gazette(date=d, edition_number=num, is_extra_edition='suplemento' in resto.lower(),
                          file_urls=[response.urljoin(url)], power='executive')


class _NpiSpider(_Base):
    """Portais da NPI Brasil (diariooficial.php): lista 'Edição Nº N de DD de Mês de AAAA' e o PDF em
    arquivos_download.php?id=<id>&pg=diariooficial."""
    BASE = ''
    RX_TIT = re.compile(r'Edi[cç][aã]o N[ºo°]\s*(\d+)\s+de\s+(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})(.{0,40})', re.I)
    RX_ID = re.compile(r'diariooficial\.php\?id=(\d+)')

    async def start(self):
        yield scrapy.Request(self.BASE + '/diariooficial.php')

    def parse(self, response):
        html, ant, vistos = response.text, 0, set()
        for m in self.RX_ID.finditer(html):
            trecho, ant = texto(html[ant:m.start()]), m.end()
            t = list(self.RX_TIT.finditer(trecho))
            i = m.group(1)
            if not t or i in vistos:
                continue
            t = t[-1]
            d = data_extenso(t.group(2), t.group(3), t.group(4))
            if not self.dentro(d):
                continue
            vistos.add(i)
            yield Gazette(date=d, edition_number=t.group(1), is_extra_edition='extra' in t.group(5).lower(),
                          file_urls=[f'{self.BASE}/arquivos_download.php?id={i}&pg=diariooficial'],
                          power='executive_legislative' if 'LEGISLATIVO' in t.group(5).upper() else 'executive')


class RjCaboFrioProprioSpider(_NpiSpider):
    name = 'rj_cabo_frio_v2'
    TERRITORY_ID = '3300704'
    allowed_domains = ['portal.cabofrio.rj.gov.br']
    start_date = date(2020, 7, 29)
    BASE = 'https://portal.cabofrio.rj.gov.br'


class RjIguabaProprioSpider(_NpiSpider):
    name = 'rj_iguaba_grande_v2'
    TERRITORY_ID = '3301876'
    allowed_domains = ['portal.iguaba.rj.gov.br']
    start_date = date(2013, 1, 1)
    BASE = 'https://portal.iguaba.rj.gov.br'


class RjBuziosProprioSpider(_NpiSpider):
    name = 'rj_armacao_dos_buzios_v2'
    TERRITORY_ID = '3300233'
    allowed_domains = ['transparencia.buzios.rj.gov.br']
    start_date = date(2015, 9, 3)
    BASE = 'https://transparencia.buzios.rj.gov.br'


class RjArraialProprioSpider(_Base):
    """Arraial do Cabo: sistema novo desde 10/09/2025. Lista 'Diário Oficial 1801/2026 Data: 06/11/2026
    [Edição extra: Sim]' e o PDF em /diariooficial/diariopdf?id=<id>."""
    name = 'rj_arraial_do_cabo_v2'
    TERRITORY_ID = '3300258'
    allowed_domains = ['portal.arraial.rj.gov.br']
    start_date = date(2025, 9, 10)
    BASE = 'https://portal.arraial.rj.gov.br'
    RX_TIT = re.compile(r'Di[aá]rio Oficial\s+(\d+)/(\d{4})\s+Data:\s*(\d{2}/\d{2}/\d{4})(.{0,80}?)Visualizar', re.I)
    RX_ID = re.compile(r'diariopdf\?id=(\d+)')

    async def start(self):
        yield scrapy.Request(self.BASE + '/diariooficial', cb_kwargs=dict(pagina=1, anterior=None))

    def parse(self, response, pagina, anterior):
        html = response.text
        ids = [(m.start(), m.group(1)) for m in self.RX_ID.finditer(html)]
        # o texto do título fica entre tags; casa no texto limpo e acha o link na mesma ordem
        limpos = list(self.RX_TIT.finditer(texto(html)))
        mais_antiga = None
        for k, m in enumerate(limpos):
            if k >= len(ids):
                break
            d = datetime.strptime(m.group(3), '%d/%m/%Y').date()
            mais_antiga = d
            if not self.dentro(d):
                continue
            yield Gazette(date=d, edition_number=m.group(1), is_extra_edition='extra: sim' in m.group(4).lower(),
                          file_urls=[f'{self.BASE}/diariooficial/diariopdf?id={ids[k][1]}'], power='executive')
        primeiro = ids[0][1] if ids else None
        if mais_antiga and mais_antiga >= self.start_date and pagina < 60 and primeiro and primeiro != anterior:
            yield scrapy.Request(f'{self.BASE}/diariooficial?page={pagina + 1}', dont_filter=True,
                                 cb_kwargs=dict(pagina=pagina + 1, anterior=primeiro))


# ---- 10/11/2026: endereços achados pela sondagem por navegador (navegador-diarios.yml) ----
# Mesmo sistema "jornal.php" (aDiários layout 2) que Cordeiro e Quissamã já usam: só configuração.
from gazette.spiders.base.adiarios_v2 import BaseAdiariosV2Spider


class RjBuziosJornalSpider(BaseAdiariosV2Spider):
    """Búzios: o site novo da prefeitura aponta o Diário Oficial para transparencia.buzios.rj.gov.br/jornal.php."""
    name = 'rj_armacao_dos_buzios_v3'
    TERRITORY_ID = '3300233'
    allowed_domains = ['buzios.rj.gov.br']
    BASE_URL = 'https://transparencia.buzios.rj.gov.br'
    start_date = date(2017, 1, 1)


class RjSeropedicaJornalSpider(BaseAdiariosV2Spider):
    """Seropédica (não tinha robô): transparencia.seropedica.rj.gov.br/jornal.php."""
    name = 'rj_seropedica'
    TERRITORY_ID = '3305554'
    allowed_domains = ['seropedica.rj.gov.br']
    BASE_URL = 'https://transparencia.seropedica.rj.gov.br'
    start_date = date(2017, 1, 1)


from gazette.spiders.base.dioenet import BaseDioenetSpider


class RjAperibeDioenetSpider(BaseDioenetSpider):
    """Aperibé (não tinha robô): mesma plataforma Dioenet de Sumidouro, achada pela sondagem de 10/11/2026."""
    name = 'rj_aperibe'
    TERRITORY_ID = '3300159'
    start_date = date(2021, 1, 1)
    BASE_URL = 'https://plenussistemas.dioenet.com.br/list/aperibe'
    power = 'executive_legislative'


# ---- Robô genérico de "página com lista de PDFs" (sites WordPress e portais próprios) ----
RX_DATA_NUM = re.compile(r'(\d{1,2})[/.\-_](\d{1,2})[/.\-_](\d{4})')
RX_DATA_ISO = re.compile(r'(\d{4})[/.\-_](\d{2})[/.\-_](\d{2})')
RX_DATA_EXT = re.compile(r'(\d{1,2})\s*(?:de\s+)?(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*(?:de\s+)?(\d{4})', re.I)
RX_EDICAO = re.compile(r'(?:edi[cç][aã]o|n[ºo°]|n\.)\s*[ºo°]?\s*(\d{2,6})', re.I)


def achar_data(t):
    t = t or ''
    for rx, ordem in ((RX_DATA_NUM, 'dmy'), (RX_DATA_ISO, 'ymd')):
        for m in rx.finditer(t):
            try:
                d, mth, y = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if ordem == 'dmy' else (int(m.group(3)), int(m.group(2)), int(m.group(1)))
                if 2000 <= y <= 2100: return date(y, mth, d)
            except ValueError:
                continue
    m = RX_DATA_EXT.search(t)
    if m:
        try: return data_extenso(m.group(1), m.group(2).replace('ç', 'c'), m.group(3))
        except (ValueError, TypeError): return None
    return None


class _ListaPdfSpider(_Base):
    """Abre as páginas START_URLS e pega todo link de PDF que tenha data (no texto do link, no endereço ou logo ao
    lado). Serve para os sites que publicam o diário como lista de arquivos. Só lê página pública."""
    START_URLS = []
    custom_settings = {'ROBOTSTXT_OBEY': False}

    async def start(self):
        for u in self.START_URLS:
            yield scrapy.Request(u, callback=self.parse_lista)

    def parse_lista(self, response):
        vistos = set()
        for a in response.css('a[href]'):
            href = a.attrib.get('href', '')
            txt = ' '.join(a.css('::text').getall())
            if not (re.search(r'\.pdf($|\?)|download|arquivo|visualizar|documento', href, re.I) or re.search(r'\.pdf\b', txt, re.I)):
                continue
            viz = ' '.join(a.xpath('ancestor::*[position()<=3]//text()').getall())[:400]
            d = achar_data(txt) or achar_data(href) or achar_data(viz)
            url = response.urljoin(href)
            if not self.dentro(d) or url in vistos:
                continue
            vistos.add(url)
            m = RX_EDICAO.search(txt) or RX_EDICAO.search(href)
            yield Gazette(date=d, edition_number=m.group(1) if m else '', is_extra_edition=bool(re.search(r'extra|suplement', txt + href, re.I)),
                          file_urls=[url], power='executive')


def _lista(nome, territorio, urls):
    return type(f'Rj{nome.title().replace("_", "")}ListaSpider', (_ListaPdfSpider,),
                dict(name=f'rj_{nome}', TERRITORY_ID=territorio, START_URLS=urls, start_date=date(2015, 1, 1),
                     # a base do Querido Diário exige allowed_domains (sem isso o robô nem começa)
                     allowed_domains=sorted({'.'.join(re.sub(r'^https?://', '', u).split('/')[0].split(':')[0].split('.')[-4:]) for u in urls})))


# Endereços achados pela sondagem de 10/11/2026 (página inicial da prefeitura, link "Diário Oficial").
# Municípios que já tinham robô ganham sufixo _v3; os que não tinham, o nome simples.
RjMaricaLista = _lista('marica_v3', '3302700', ['https://www.marica.rj.gov.br/diario-oficial-de-marica/', 'https://www.marica.rj.gov.br/jornal-oficial-marica/'])
RjVoltaRedondaLista = _lista('volta_redonda', '3306305', ['https://www.voltaredonda.rj.gov.br/diario-oficial'])
# RjItaboraiLista = _lista('itaborai', '3301900', ['https://site.ib.itaborai.rj.gov.br/diario-oficial'])  # trocado por robô próprio (2ª sondagem)
RjAraruamaLista = _lista('araruama', '3300209', ['https://www.araruama.rj.gov.br/publicacoes/diario-oficial'])
# RjRioDasOstrasLista = _lista('rio_das_ostras', '3304524', ['https://www.riodasostras.rj.gov.br/jornal-oficial/'])  # trocado por robô próprio (2ª sondagem)
RjItatiaiaLista = _lista('itatiaia', '3302254', ['https://itatiaia.rj.gov.br/diariooficial-2'])
RjItaperunaLista = _lista('itaperuna', '3302205', ['https://itaperuna.rj.gov.br/pmi/jornal-oficial-2022'])
RjNilopolisLista = _lista('nilopolis', '3303203', ['https://nilopolis.rj.gov.br/diario-oficial-online/', 'https://nilopolis.rj.gov.br/diario-oficial-extra-online/'])
RjParacambiLista = _lista('paracambi', '3303609', ['https://paracambi.rj.gov.br/diario-oficial-eletronico-2026/'])
# RjPatyLista = _lista('paty_do_alferes', '3303856', ['https://patydoalferes.rj.gov.br/diario-oficial/'])
RjSaoFidelisLista = _lista('sao_fidelis', '3304805', ['https://saofidelis.rj.gov.br/diario-oficial-eletronico/', 'https://saofidelis.rj.gov.br/diariooficial'])
RjTrajanoLista = _lista('trajano_de_moraes', '3305901', ['https://www.trajanodemoraes.rj.gov.br/diario-oficial'])
RjNatividadeLista = _lista('natividade', '3303104', ['https://www.natividade.rj.gov.br/diario-oficial?category[0]=3&category_children=1'])
RjRioBonitoLista = _lista('rio_bonito', '3304300', ['https://diario-oficial.riobonito.rj.gov.br/'])
RjVarreSaiLista = _lista('varre_sai_v2', '3306156', ['https://varresai.rj.gov.br/diarios-oficiais'])
RjBarraPiraiLista = _lista('barra_do_pirai', '3300308', ['https://barradopirai.rj.gov.br/page/4edb08b8-3bae-4279-ad18-e8b88e798bda/diario-oficial-eletronico'])
# RjParaibaSulLista = _lista('paraiba_do_sul', '3303708', ['https://paraibadosul.rj.gov.br/page/3e364d6c-e018-47c3-aa46-db0c771424f6/diario-oficial'])  # trocado por robô próprio (2ª sondagem)
RjCaxiasLista = _lista('duque_de_caxias_v2', '3301702', ['https://transparencia.duquedecaxias.rj.gov.br/diario_oficial_busca.php'])
RjMiguelPereiraLista = _lista('miguel_pereira_v2', '3302908', ['https://transparencia.miguelpereira.rj.gov.br/?serv=113'])


# ---- Robôs a partir da 2ª sondagem com navegador (10/11/2026) ----
import json as _json


class RjRioDasOstrasApiSpider(_Base):
    """Rio das Ostras: a página do Jornal Oficial lê uma API pública em JSON (edicao, link do PDF, data)."""
    name = 'rj_rio_das_ostras'
    TERRITORY_ID = '3304524'
    allowed_domains = ['riodasostras.rj.gov.br']
    start_date = date(2015, 1, 1)
    API = 'https://appro.riodasostras.rj.gov.br/riodasostrasapp_server/api/jornais/search/site?&limit=600&offset=0&orderBy=data&orderDir=desc&ano={}'

    async def start(self):
        for ano in range(self.start_date.year, self.end_date.year + 1):
            yield scrapy.Request(self.API.format(ano), callback=self.parse_api)

    def parse_api(self, response):
        for j in _json.loads(response.text):
            try:
                d = date.fromisoformat(str(j.get('data', ''))[:10])
            except ValueError:
                continue
            if not self.dentro(d) or not j.get('link'):
                continue
            ed = j.get('edicao') or ''
            m = re.search(r'(\d{2,6})', ed)
            yield Gazette(date=d, edition_number=m.group(1) if m else '', is_extra_edition=bool(re.search(r'extra|suplement', ed, re.I)),
                          file_urls=[j['link']], power='executive')


class RjItaboraiDataSpider(_Base):
    """Itaboraí: os PDFs ficam em do.ib.itaborai.rj.gov.br/edicoes/AAAA/, pasta pública com a lista dos arquivos
    (AAAA-MM-DD.pdf; AAAA-MM-DDA.pdf, ...B.pdf para edições extras). O robô lê a lista de cada ano."""
    name = 'rj_itaborai'
    TERRITORY_ID = '3301900'
    allowed_domains = ['itaborai.rj.gov.br']
    start_date = date(2019, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}

    async def start(self):
        for ano in range(self.start_date.year, self.end_date.year + 1):
            yield scrapy.Request(f'https://do.ib.itaborai.rj.gov.br/edicoes/{ano}/', callback=self.parse_pasta)

    def parse_pasta(self, response):
        for href in dict.fromkeys(response.css('a::attr(href)').getall()):
            m = re.match(r'(?:.*/)?(\d{4})-(\d{2})-(\d{2})([A-Z]?)\.pdf$', href, re.I)
            if not m: continue
            try: d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError: continue
            if self.dentro(d):
                yield Gazette(date=d, edition_number='', is_extra_edition=bool(m.group(4)),
                              file_urls=[response.urljoin(href)], power='executive')


class RjParaibaDoSulDriveSpider(_Base):
    """Paraíba do Sul: a página do Diário Oficial lista cada edição como 'Diário Oficial Dia DD de <mês> de AAAA',
    com o PDF no Google Drive (link público). O robô pega a data do texto e baixa pelo link de download do Drive."""
    name = 'rj_paraiba_do_sul'
    TERRITORY_ID = '3303708'
    allowed_domains = ['paraibadosul.rj.gov.br', 'drive.google.com', 'drive.usercontent.google.com']
    start_date = date(2015, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}
    URL = 'https://paraibadosul.rj.gov.br/page/3e364d6c-e018-47c3-aa46-db0c771424f6/diario-oficial'

    async def start(self):
        yield scrapy.Request(self.URL, callback=self.parse_pag)

    def parse_pag(self, response):
        t = response.text.replace('\\u0026', '&').replace('\\/', '/')
        vistos = set()
        for m in re.finditer(r'drive\.google\.com/file/d/([\w-]{20,})', t):
            fid = m.group(1)
            if fid in vistos: continue
            viz = re.sub(r'<[^>]+>', ' ', t[max(0, m.start() - 600):m.end() + 600])
            datas = [(abs(x.start() - 600), x) for x in RX_DATA_EXT.finditer(viz)]
            if not datas: continue
            x = min(datas, key=lambda p: p[0])[1]
            try: d = data_extenso(x.group(1), x.group(2).replace('ç', 'c'), x.group(3))
            except (ValueError, TypeError): continue
            if not self.dentro(d): continue
            vistos.add(fid)
            yield Gazette(date=d, edition_number='', is_extra_edition=False,
                          file_urls=[f'https://drive.google.com/uc?export=download&id={fid}'], power='executive')


# Nilópolis: o site da prefeitura aponta "Edição Impressa" para vozdosmunicipios.com.br/atos-oficiais/, onde cada
# edição é .../atos-oficiais/AAAA/<Mês>/DD-MM-AAAA/prefeitura.pdf (também câmara e Previnil, o instituto de previdência).
RjNilopolisVozLista = _lista('nilopolis_v2', '3303203', ['https://vozdosmunicipios.com.br/atos-oficiais/'])


# ---- Rodada 3 (10/11/2026 tarde): achados pela varredura com navegador dos municípios sem coleta ----
RjSaoGoncaloLista = _lista('sao_goncalo', '3304904', ['https://do.pmsg.rj.gov.br/'])
# 0 edições no teste de 10/11 (lista montada por JS) — RjSaoJoseDeUbaLista = _lista('sao_jose_de_uba', '3305133', ['https://saojosedeuba.rj.gov.br/site/diarios_oficiais'])
RjRioClaroLista = _lista('rio_claro', '3304409', ['https://rioclaro-rj.portaltp.com.br/consultas/documentos.aspx?id=492'])


class RjCarmoGesdomSpider(_Base):
    """Carmo: a página do Diário (transparencia.carmo.rj.gov.br/diario) lê gesdom_api.php?acao=edicoes, um JSON público
    com EDICAO, DATA_EDICAO e ARQUIVO_ASSINADO; o PDF fica em gesdom.carmo.rj.gov.br/_lib/file/doc/pdf/<arquivo>."""
    name = 'rj_carmo'
    TERRITORY_ID = '3301207'
    allowed_domains = ['carmo.rj.gov.br']
    start_date = date(2021, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}

    async def start(self):
        yield scrapy.Request('https://transparencia.carmo.rj.gov.br/gesdom_api.php?acao=edicoes', callback=self.parse_api)

    def parse_api(self, response):
        from urllib.parse import quote
        for j in _json.loads(response.text):
            try:
                d = date.fromisoformat(str(j.get('DATA_EDICAO', ''))[:10])
            except ValueError:
                continue
            arq = j.get('ARQUIVO_ASSINADO') or ''
            if not self.dentro(d) or not arq:
                continue
            yield Gazette(date=d, edition_number=str(j.get('EDICAO') or ''), is_extra_edition=bool(re.search(r'extra|suplement', arq, re.I)),
                          file_urls=['https://gesdom.carmo.rj.gov.br/_lib/file/doc/pdf/' + quote(arq)], power='executive')


class RjPatyAjaxSpider(_Base):
    """Paty do Alferes: a página do Diário Oficial pergunta ao WordPress (admin-ajax.php, ação pública
    pdo_get_versions_by_date) as edições de cada dia; a resposta traz número e link do PDF."""
    name = 'rj_paty_do_alferes'
    TERRITORY_ID = '3303856'
    allowed_domains = ['patydoalferes.rj.gov.br']
    start_date = date(2020, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}

    async def start(self):
        from datetime import timedelta
        d = self.end_date
        while d >= self.start_date:
            if d.weekday() < 6:
                yield scrapy.FormRequest('https://patydoalferes.rj.gov.br/wp-admin/admin-ajax.php',
                                         formdata={'action': 'pdo_get_versions_by_date', 'date': d.isoformat()},
                                         callback=self.parse_dia, cb_kwargs={'d': d}, dont_filter=True)
            d -= timedelta(days=1)

    def parse_dia(self, response, d):
        try:
            j = _json.loads(response.text)
        except ValueError:
            return
        for v in ((j.get('data') or {}).get('versions') or []):
            if v.get('url'):
                yield Gazette(date=d, edition_number=str(v.get('edicao') or ''), is_extra_edition=bool(re.search(r'extra|suplement', (v.get('titulo') or '') + (v.get('desc') or ''), re.I)),
                              file_urls=[v['url']], power='executive')


class _BethaSpider(_Base):
    """Portal Betha: a lista (com links de PDF assinados por 24 h) é montada antes pelo coletor/navegador/betha.js,
    que abre a página pública como visitante. Aqui só lemos listas/betha_<NOME>.json e baixamos os PDFs."""
    NOME = ''
    allowed_domains = ['amazonaws.com', 'betha.cloud']
    start_date = date(2010, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}

    async def start(self):
        import json, os
        arq = os.path.join(os.environ.get('GITHUB_WORKSPACE', '.'), 'listas', f'betha_{self.NOME}.json')
        if not os.path.exists(arq):
            self.logger.error(f'lista {arq} não existe (o passo do navegador não rodou ou falhou)')
            return
        for it in json.load(open(arq)):
            d = date.fromisoformat(it['data'])
            if self.dentro(d) and it['urls']:
                yield Gazette(date=d, edition_number=it.get('edicao', ''), is_extra_edition=bool(it.get('extra')),
                              file_urls=it['urls'], power='executive')
        if False:
            yield


# Desligado em 10/11/2026: o login anônimo do portal Betha responde 403 ao navegador do GitHub (bloqueio; não contornar).
# Religar se rodar do Dell. 
_RjRioDasFloresBetha = None
class _RjRioDasFloresBethaSpider(_BethaSpider):
    """Rio das Flores: Boletim Municipal no portal Betha (consulta 5384), 665 edições em 10/11/2026, sem captcha."""
    nome_quando_religar = 'rj_rio_das_flores_betha'
    TERRITORY_ID = '3304508'
    NOME = 'rio_das_flores'


class RjSaoFranciscoDeItabapoanaApiSpider(_Base):
    """São Francisco de Itabapoana: diário próprio (sfi.diariooficial.pmsfi.rj.gov.br) com API pública de leitura:
    /api/v1/tenant/sfi/edicoes?size=&page= (id, numero_edicao, data_publicacao, tipo regular/suplemento);
    PDF em /api/v1/storage/sfi/final/<id>.pdf. Achado em 11/11/2026 (busca na web + navegador)."""
    name = 'rj_sao_francisco_de_itabapoana_api'
    TERRITORY_ID = '3304755'
    allowed_domains = ['sfi.diariooficial.pmsfi.rj.gov.br']
    start_date = date(2025, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}
    BASE = 'https://sfi.diariooficial.pmsfi.rj.gov.br'

    async def start(self):
        yield scrapy.Request(f'{self.BASE}/api/v1/tenant/sfi/edicoes?size=50&page=1', callback=self.parse_lista, cb_kwargs={'pagina': 1})

    def parse_lista(self, response, pagina):
        j = response.json(); itens = j.get('items') or []
        mais_velha = None
        for it in itens:
            try: d = date.fromisoformat(it['data_publicacao'][:10])
            except Exception: continue
            mais_velha = d
            if self.dentro(d):
                yield Gazette(date=d, edition_number=str(it.get('numero_edicao', '')), is_extra_edition=it.get('tipo') != 'regular',
                              file_urls=[f"{self.BASE}/api/v1/storage/sfi/final/{it['id']}.pdf"], power='executive')
        if itens and mais_velha and mais_velha >= self.start_date and pagina * 50 < (j.get('total') or 0):
            yield scrapy.Request(f'{self.BASE}/api/v1/tenant/sfi/edicoes?size=50&page={pagina + 1}', callback=self.parse_lista, cb_kwargs={'pagina': pagina + 1})


class RjGuapimirimSeqSpider(_Base):
    """Guapimirim: o Diário fica em guapimirim.rj.gov.br/wp-content/uploads/AAAA/MM/Diario-NNNN.pdf (número sequencial,
    pasta do mês do envio). A página de lista não abre e a API do WordPress pede login (401), então seguimos o número:
    para cada N testamos a pasta do mês atual e as vizinhas (±2 meses, HEAD); 40 números seguidos sem arquivo = fim.
    Âncora (busca na web, 11/11/2026): nº 1756 em 2025/11 e nº 1903 em 2026/07 (~9 por mês).
    DATA: é o Last-Modified do arquivo (dia do envio ao site), não lida do PDF. HIPÓTESE: coincide com a publicação."""
    name = 'rj_guapimirim_seq'
    TERRITORY_ID = '3301850'
    allowed_domains = ['guapimirim.rj.gov.br']
    start_date = date(2025, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}
    URL = 'https://guapimirim.rj.gov.br/wp-content/uploads/{a:04d}/{m:02d}/Diario-{n}.pdf'

    def _mes(self, a, m, k):
        m += k
        return (a + (m - 1) // 12, (m - 1) % 12 + 1)

    async def start(self):
        # ritmo visto: 1784 em 2026/01 e 1903 em 2026/07 (~20 por mês); 1756 em 2025/11
        meses = (self.start_date.year - 2026) * 12 + self.start_date.month - 7
        n = max(1000, int(1903 + 19.8 * meses) - 40)
        yield self._tenta(n, self.start_date.year, self.start_date.month, 0, 0)

    OFS = [0, 1, -1, 2, -2]   # pasta do mês: a atual, depois vizinhas

    def _tenta(self, n, a, m, k, faltas):
        aa, mm = self._mes(a, m, self.OFS[k])
        return scrapy.Request(self.URL.format(a=aa, m=mm, n=n), method='HEAD', callback=self.parse_head, dont_filter=True,
                              meta={'handle_httpstatus_list': [403, 404]}, cb_kwargs=dict(n=n, a=a, m=m, k=k, faltas=faltas))

    def parse_head(self, response, n, a, m, k, faltas):
        if response.status == 200:
            lm = response.headers.get('Last-Modified', b'').decode()
            try: d = datetime.strptime(lm[5:16], '%d %b %Y').date()
            except Exception: d = None
            aa, mm = self._mes(a, m, self.OFS[k])
            if d and self.dentro(d):
                yield Gazette(date=d, edition_number=str(n), is_extra_edition=False, file_urls=[response.url], power='executive')
            if d and d > self.end_date:
                return
            yield self._tenta(n + 1, aa, mm, 0, 0)
        elif k < len(self.OFS) - 1:
            yield self._tenta(n, a, m, k + 1, faltas)
        elif faltas < 40:
            yield self._tenta(n + 1, a, m, 0, faltas + 1)


class RjAraruamaListaSpider(_Base):
    """Araruama: lista pública em /publicacoes/diario-oficial?page=N (links '06-de-novembro-de-2026-ano-xix-no-1871');
    cada edição tem página própria com o PDF em /storage/content/publicacoes/diario-oficial/<id>/arquivos/<hash>.pdf.
    Achado pela sondagem por navegador em 11/11/2026."""
    name = 'rj_araruama_lista'
    TERRITORY_ID = '3300209'
    allowed_domains = ['www.araruama.rj.gov.br', 'araruama.rj.gov.br']
    start_date = date(2015, 1, 1)
    BASE = 'https://www.araruama.rj.gov.br'
    RX = re.compile(r'href=["\'](?:https?://www\.araruama\.rj\.gov\.br)?(/publicacoes/diario-oficial/'
                    r'(\d{1,2})-de-([a-z]+)-de-(\d{4})([a-z0-9-]*))["\']', re.I)

    async def start(self):
        yield scrapy.Request(self.BASE + '/publicacoes/diario-oficial', callback=self.parse_lista, cb_kwargs=dict(pagina=1, anterior=None))

    def parse_lista(self, response, pagina, anterior):
        vistos, mais_velha = [], None
        for m in self.RX.finditer(response.text):
            url = self.BASE + m.group(1)
            if url in vistos:
                continue
            vistos.append(url)
            d = data_extenso(m.group(2), m.group(3), m.group(4))
            if not d:
                continue
            mais_velha = d if not mais_velha or d < mais_velha else mais_velha
            if self.dentro(d):
                num = re.search(r'-no-(\d+)', m.group(5))
                yield scrapy.Request(url, callback=self.parse_edicao, cb_kwargs=dict(
                    d=d, num=num.group(1) if num else '', extra='extra' in m.group(5).lower()))
        if vistos and vistos[0] != anterior and mais_velha and mais_velha >= self.start_date and pagina < 600:
            yield scrapy.Request(f'{self.BASE}/publicacoes/diario-oficial?page={pagina + 1}', callback=self.parse_lista,
                                 dont_filter=True, cb_kwargs=dict(pagina=pagina + 1, anterior=vistos[0]))

    def parse_edicao(self, response, d, num, extra):
        pdfs = list(dict.fromkeys(re.findall(r'(/storage/content/publicacoes/diario-oficial/\d+/arquivos/[^"\'\s]+?\.pdf)', response.text)))
        if pdfs:
            yield Gazette(date=d, edition_number=num, is_extra_edition=extra,
                          file_urls=[self.BASE + p for p in pdfs], power='executive')


# São João da Barra e São José de Ubá: lidos por coletor/navegador/portalgov.js (o POST da lista dá 403 fora do navegador).


class RjNovaFriburgoDioenetSpider(BaseDioenetSpider):
    """Nova Friburgo: o site do diário (diario.novafriburgo) não abre de fora; as edições estão também na
    plataforma Dioenet (plenussistemas.dioenet.com.br/list/nova-friburgo), achada pela sondagem de 10/11/2026."""
    name = 'rj_nova_friburgo_dioenet'
    TERRITORY_ID = '3303401'
    start_date = date(2021, 1, 1)
    BASE_URL = 'https://plenussistemas.dioenet.com.br/list/nova-friburgo'
    power = 'executive'


class RjParatyApiSpider(_Base):
    """Paraty: a página pública multimidia/documentos lê a API JSON /API/API/Documentos (CategoriaId=6 = Diário Oficial),
    com Titulo 'Edição N°. 2138/2026', DataPublicacao e o PDF em DocumentoArquivoAtual. Achado em 11/11/2026."""
    name = 'rj_paraty_api'
    TERRITORY_ID = '3303807'
    allowed_domains = ['www.paraty.rj.gov.br']
    start_date = date(2015, 1, 1)
    BASE = 'https://www.paraty.rj.gov.br/API/API/Documentos?CategoriaId=6&Edicao=&PageSize=50&Palavra=&Tag=&Todos=&PageNumber={}'

    async def start(self):
        yield scrapy.Request(self.BASE.format(1), callback=self.parse_api, cb_kwargs={'pagina': 1}, headers=self.JSON)

    JSON = {'Accept': 'application/json'}   # a API (ASP.NET) responde XML se o pedido não disser que quer JSON

    def parse_api(self, response, pagina):
        itens = response.json() or []
        mais_velha = None
        for it in itens:
            try: d = datetime.strptime(it.get('DataPublicacao', ''), '%d/%m/%Y').date()
            except Exception: continue
            mais_velha = d
            arq = (it.get('DocumentoArquivoAtual') or {}).get('CaminhoLogicoArquivo')
            if not self.dentro(d) or not arq:
                continue
            tit = it.get('Titulo') or ''
            m = re.search(r'(\d+(?:-[A-Z])?)\s*/\s*\d{4}', tit)
            yield Gazette(date=d, edition_number=m.group(1) if m else tit[:30], is_extra_edition=bool(re.search(r'extra|-[A-Z]\b', tit, re.I)),
                          file_urls=[arq], power='executive')
        if itens and mais_velha and mais_velha >= self.start_date and pagina < 400:
            yield scrapy.Request(self.BASE.format(pagina + 1), callback=self.parse_api, cb_kwargs={'pagina': pagina + 1}, headers=self.JSON)


class RjBarraDoPiraiListaSpider(_Base):
    """Barra do Piraí: página 'Diário Oficial Eletrônico' com um link por ano (/page/<id>/boletim-municipal-AAAA);
    cada ano lista 'DOE 205 - Data 10-11.pdf' com o PDF em gestor.barradopirai.rj.gov.br/uploads/files/barradopirai/.
    Achado pela sondagem por navegador em 11/11/2026."""
    name = 'rj_barra_do_pirai_lista'
    TERRITORY_ID = '3300308'
    allowed_domains = ['barradopirai.rj.gov.br', 'gestor.barradopirai.rj.gov.br']
    start_date = date(2015, 1, 1)
    INICIO = 'https://barradopirai.rj.gov.br/page/4edb08b8-3bae-4279-ad18-e8b88e798bda/diario-oficial-eletronico'
    RX = re.compile(r'(https://gestor\.barradopirai\.rj\.gov\.br/uploads/files/barradopirai/[^"\'\s<>\\]+?\.pdf)'
                    r'[^<]{0,400}?>\s*(?:<[^>]+>\s*)*DOE\s*(\d+)\s*-\s*Data\s*(\d{1,2})-(\d{1,2})([^<]*)', re.I)

    async def start(self):
        yield scrapy.Request(self.INICIO, callback=self.parse_anos)

    def parse_anos(self, response):
        achou = 0
        for href, ano in set(re.findall(r'(/page/[0-9a-f-]{36}/boletim-municipal-(\d{4}))', response.text)):
            if self.start_date.year <= int(ano) <= self.end_date.year:
                achou += 1
                yield scrapy.Request(response.urljoin(href), callback=self.parse_ano, cb_kwargs={'ano': int(ano)})
        if not achou:
            self.logger.error('Barra do Piraí: links dos anos não vieram no HTML (página montada no navegador?)')

    def parse_ano(self, response, ano):
        n = 0
        for url, num, dia, mes, resto in self.RX.findall(response.text):
            try: d = date(ano, int(mes), int(dia))
            except ValueError: continue
            n += 1
            if self.dentro(d):
                yield Gazette(date=d, edition_number=num, is_extra_edition='extra' in (resto + url).lower(), file_urls=[url], power='executive')
        if not n:
            self.logger.error(f'Barra do Piraí {ano}: nenhuma edição no HTML')


class RjJaperiGeosiapSpider(_Base):
    """Japeri: Portal da Transparência GeoSiap, aba Publicações, tipo 7 = Diário Oficial. A própria página documenta a
    API de dados abertos: lista em api//publicacoes/publicacoes?id_publicacao_tipo=7&exercicio=AAAA e o arquivo em
    publicacoes/get_arquivo.anexo?...&id_publicacao=<id> (demais ids = 0). Achado em 11/11/2026."""
    name = 'rj_japeri_geosiap'
    TERRITORY_ID = '3302270'
    allowed_domains = ['japeri.geosiap.net.br']
    start_date = date(2015, 1, 1)
    API = 'https://japeri.geosiap.net.br/portal-transparencia/api/'
    ARQ = API + 'publicacoes/get_arquivo.anexo?id_subtipo=0&id_publicacao={}&id_publicacao_tipo=0&id_publicacao_sub_tipo=0&id_publicacao_periodo=0&exercicio=0&mes=0&id_relatorio=0'

    async def start(self):
        for ano in range(self.start_date.year, self.end_date.year + 1):
            yield scrapy.Request(f'{self.API}/publicacoes/publicacoes?id_publicacao_tipo=7&exercicio={ano}', callback=self.parse_lista)

    def parse_lista(self, response):
        for it in (response.json() or {}).get('publicacoes') or []:
            try: d = date.fromisoformat((it.get('dt_publicacao') or '')[:10])
            except ValueError: continue
            if not self.dentro(d) or not it.get('id_publicacao'):
                continue
            nome = it.get('nome_arquivo') or ''
            m = re.search(r'-\s*(\d{3,6})\s*-', nome)
            yield Gazette(date=d, edition_number=m.group(1) if m else '', is_extra_edition='extra' in nome.lower(),
                          file_urls=[self.ARQ.format(it['id_publicacao'])], power='executive')


class RjNatividadeListaSpider(_Base):
    """Natividade: página /diario-oficial (Joomla) lista 'Edição 402 de 31/10/2026'; o botão 'Baixar pdf' chama
    handleDownloadClick('/diario-oficial/<id>-edicao-<n>-de-<ddmmaaaa>/file?category_id=..'), endereço público do PDF.
    Achado pela sondagem por navegador em 11/11/2026. Segue os links de página (start=) que a própria lista mostra."""
    name = 'rj_natividade_lista'
    TERRITORY_ID = '3303104'
    allowed_domains = ['www.natividade.rj.gov.br', 'natividade.rj.gov.br']
    start_date = date(2015, 1, 1)
    BASE = 'https://www.natividade.rj.gov.br'
    RX = re.compile(r"(/diario-oficial/\d+-edicao-(\d+)[a-z0-9-]*?-de-(\d{2})(\d{2})(\d{4})[a-z0-9-]*/file\?category_id=\d+)", re.I)

    async def start(self):
        yield scrapy.Request(self.BASE + '/diario-oficial?category[0]=3&category_children=1', callback=self.parse_lista)

    def parse_lista(self, response):
        mais_velha = None
        for url, num, dd, mm, aa in set(self.RX.findall(response.text.replace('&amp;', '&'))):
            try: d = date(int(aa), int(mm), int(dd))
            except ValueError: continue
            mais_velha = d if not mais_velha or d < mais_velha else mais_velha
            if self.dentro(d):
                yield Gazette(date=d, edition_number=num, is_extra_edition='extra' in url.lower(), file_urls=[self.BASE + url], power='executive')
        if mais_velha and mais_velha >= self.start_date:
            for prox in set(re.findall(r'href="([^"]*[?&](?:start|limitstart)=\d+[^"]*)"', response.text)):
                yield response.follow(prox.replace('&amp;', '&'), callback=self.parse_lista)


class RjSantaMariaMadalenaListaSpider(_Base):
    """Santa Maria Madalena: página /diario_oficial_eletronico lista as edições por mês com o PDF em
    /transparencia/publicacoes_oficiais/diario_oficial_eletronico/AAAA/mes/EDIÇÃO_-_354_-_..._-_23-10_A_31-10.pdf.
    A pasta em si dá 403 (não contornamos); só seguimos os links que a página mostra. Achado em 11/11/2026.
    DATA: o nome traz o período (ex.: 23-10 a 31-10); usamos o ÚLTIMO dia do período. HIPÓTESE: é o dia da publicação."""
    name = 'rj_santa_maria_madalena_lista'
    TERRITORY_ID = '3304607'
    allowed_domains = ['www.pmsmm.rj.gov.br', 'pmsmm.rj.gov.br']
    start_date = date(2020, 5, 1)
    BASE = 'https://www.pmsmm.rj.gov.br'
    RX = re.compile(r'href="([^"]*/diario_oficial_eletronico/(\d{4})/[^"/]+/[^"]+?\.pdf)"', re.I)
    RX_NUM = re.compile(r'EDI(?:%C3%87%C3%83O|ÇÃO|CAO)_-_(\d+)', re.I)
    RX_PER = re.compile(r'(\d{2})-(\d{2})_A_(\d{2})-(\d{2})', re.I)

    async def start(self):
        yield scrapy.Request(self.BASE + '/diario_oficial_eletronico', callback=self.parse_lista)

    def parse_lista(self, response):
        html = response.text.replace('&amp;', '&')
        for url, ano in set(self.RX.findall(html)):
            per = self.RX_PER.search(url); num = self.RX_NUM.search(url)
            if not per:
                continue
            try: d = date(int(ano), int(per.group(4)), int(per.group(3)))
            except ValueError: continue
            if self.dentro(d):
                yield Gazette(date=d, edition_number=num.group(1) if num else '', is_extra_edition='extra' in url.lower(),
                              file_urls=[response.urljoin(url)], power='executive')
        for prox in set(re.findall(r'href="([^"]*diario_oficial_eletronico\?[^"]+)"', html)):
            m = re.search(r'ano=(\d{4})', prox)
            if not m or self.start_date.year <= int(m.group(1)) <= self.end_date.year:
                yield response.follow(prox, callback=self.parse_lista)
