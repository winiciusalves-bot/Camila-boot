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
