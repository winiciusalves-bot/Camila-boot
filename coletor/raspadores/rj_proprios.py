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
            if not re.search(r'\.pdf($|\?)|download|arquivo|visualizar', href, re.I):
                continue
            txt = ' '.join(a.css('::text').getall())
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
                dict(name=f'rj_{nome}', TERRITORY_ID=territorio, START_URLS=urls, start_date=date(2015, 1, 1)))


# Endereços achados pela sondagem de 10/11/2026 (página inicial da prefeitura, link "Diário Oficial").
# Municípios que já tinham robô ganham sufixo _v3; os que não tinham, o nome simples.
RjMaricaLista = _lista('marica_v3', '3302700', ['https://www.marica.rj.gov.br/diario-oficial-de-marica/', 'https://www.marica.rj.gov.br/jornal-oficial-marica/'])
RjVoltaRedondaLista = _lista('volta_redonda', '3306305', ['https://www.voltaredonda.rj.gov.br/diario-oficial'])
RjItaboraiLista = _lista('itaborai', '3301900', ['https://site.ib.itaborai.rj.gov.br/diario-oficial'])
RjAraruamaLista = _lista('araruama', '3300209', ['https://www.araruama.rj.gov.br/publicacoes/diario-oficial'])
RjRioDasOstrasLista = _lista('rio_das_ostras', '3304524', ['https://www.riodasostras.rj.gov.br/jornal-oficial/'])
RjItatiaiaLista = _lista('itatiaia', '3302254', ['https://itatiaia.rj.gov.br/diariooficial-2'])
RjItaperunaLista = _lista('itaperuna', '3302205', ['https://itaperuna.rj.gov.br/pmi/jornal-oficial-2022'])
RjNilopolisLista = _lista('nilopolis', '3303203', ['https://nilopolis.rj.gov.br/diario-oficial-online/', 'https://nilopolis.rj.gov.br/diario-oficial-extra-online/'])
RjParacambiLista = _lista('paracambi', '3303609', ['https://paracambi.rj.gov.br/diario-oficial-eletronico-2026/'])
RjPatyLista = _lista('paty_do_alferes', '3303856', ['https://patydoalferes.rj.gov.br/diario-oficial/'])
RjSaoFidelisLista = _lista('sao_fidelis', '3304805', ['https://saofidelis.rj.gov.br/diario-oficial-eletronico/', 'https://saofidelis.rj.gov.br/diariooficial'])
RjTrajanoLista = _lista('trajano_de_moraes', '3305901', ['https://www.trajanodemoraes.rj.gov.br/diario-oficial'])
RjNatividadeLista = _lista('natividade', '3303104', ['https://www.natividade.rj.gov.br/diario-oficial?category[0]=3&category_children=1'])
RjRioBonitoLista = _lista('rio_bonito', '3304300', ['https://diario-oficial.riobonito.rj.gov.br/'])
RjVarreSaiLista = _lista('varre_sai_v2', '3306156', ['https://varresai.rj.gov.br/diarios-oficiais'])
RjBarraPiraiLista = _lista('barra_do_pirai', '3300308', ['https://barradopirai.rj.gov.br/page/4edb08b8-3bae-4279-ad18-e8b88e798bda/diario-oficial-eletronico'])
RjParaibaSulLista = _lista('paraiba_do_sul', '3303708', ['https://paraibadosul.rj.gov.br/page/3e364d6c-e018-47c3-aa46-db0c771424f6/diario-oficial'])
RjCaxiasLista = _lista('duque_de_caxias_v2', '3301702', ['https://transparencia.duquedecaxias.rj.gov.br/diario_oficial_busca.php'])
RjMiguelPereiraLista = _lista('miguel_pereira_v2', '3302908', ['https://transparencia.miguelpereira.rj.gov.br/?serv=113'])
