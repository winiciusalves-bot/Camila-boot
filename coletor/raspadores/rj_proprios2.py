# Robôs da 2ª leva (10/11/2026): municípios do RJ que estavam sem diário na base comum.
# Mesmo formato de saída do Querido Diário (item Gazette). Só leem páginas e APIs públicas, as mesmas que o
# navegador usa ao abrir o site. Não contornam captcha, bloqueio, WAF nem login: se o site recusar, a falha
# fica no log e o município vai para a coleta pelo PC do usuário ou para o pedido de PDF.
import json
import re
from datetime import date, datetime

import scrapy

from gazette.items import Gazette
from gazette.spiders.base import BaseGazetteSpider


class _Base2(BaseGazetteSpider):
    def dentro(self, d):
        return d is not None and self.start_date <= d <= self.end_date

    def meses(self):
        a, m = self.start_date.year, self.start_date.month
        while (a, m) <= (self.end_date.year, self.end_date.month):
            yield a, m
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)


class RjDuqueDeCaxiasApiSpider(_Base2):
    """Duque de Caxias: a página diario_oficial_busca.php lê uma lista JSON por mês (POST mesano=MM/AAAA) e
    o PDF sai em diario_oficial_get_anexo.php?codigo=<Codigo_ANEXO>. Conferido em 10/11/2026."""
    name = 'rj_duque_de_caxias_v3'
    TERRITORY_ID = '3301702'
    allowed_domains = ['transparencia.duquedecaxias.rj.gov.br']
    start_date = date(2021, 1, 1)
    BASE = 'https://transparencia.duquedecaxias.rj.gov.br'

    async def start(self):
        for a, m in self.meses():
            yield scrapy.FormRequest(f'{self.BASE}/diario_oficial_get.php', formdata={'mesano': f'{m:02d}/{a}', 'pagina': '1'},
                                     callback=self.parse_mes, dont_filter=True)

    def parse_mes(self, response):
        try:
            itens = json.loads(response.text)
        except ValueError:
            self.logger.error(f'resposta não é JSON: {response.text[:200]!r}')
            return
        for it in itens:
            if str(it.get('HABILITADO', 'S')).upper() != 'S' or not it.get('Codigo_ANEXO'):
                continue
            try:
                d = datetime.strptime(it['Data_Formatada'], '%d/%m/%Y').date()
            except (KeyError, ValueError):
                continue
            if not self.dentro(d):
                continue
            desc = f"{it.get('ANEXO') or ''} {it.get('DESCRICAO') or ''}"
            n = re.search(r'(\d{3,6})', desc)
            yield Gazette(date=d, edition_number=n.group(1) if n else '',
                          is_extra_edition=bool(re.search(r'extra|suplement|vol', desc, re.I)),
                          file_urls=[f"{self.BASE}/diario_oficial_get_anexo.php?codigo={it['Codigo_ANEXO']}"], power='executive')


class RjBomJardimApiSpider(_Base2):
    """Bom Jardim: diariooficial.bomjardim.rj.gov.br lê /api/public/documentos?year=&month= (JSON) e o PDF fica em
    /uploads/<storage_path>. Conferido em 10/11/2026 (edição 635, 09/11/2026)."""
    name = 'rj_bom_jardim'
    TERRITORY_ID = '3300506'
    allowed_domains = ['diariooficial.bomjardim.rj.gov.br']
    start_date = date(2021, 1, 1)
    BASE = 'https://diariooficial.bomjardim.rj.gov.br'

    async def start(self):
        for a, m in self.meses():
            yield scrapy.Request(f'{self.BASE}/api/public/documentos?year={a}&month={m}&limit=100&page=1',
                                 callback=self.parse_api, cb_kwargs=dict(a=a, m=m, pagina=1))

    def parse_api(self, response, a, m, pagina):
        d_ = json.loads(response.text)
        for it in d_.get('documentos') or []:
            if not it.get('storage_path') or it.get('is_public') is False:
                continue
            t = it.get('titulo') or ''
            mm = re.match(r'(\d{4})-(\d{2})-(\d{2})', t)
            try:
                d = date(int(mm.group(1)), int(mm.group(2)), int(mm.group(3))) if mm else date.fromisoformat(it['uploaded_at'][:10])
            except (ValueError, KeyError, TypeError):
                continue
            if not self.dentro(d):
                continue
            n = re.search(r'(\d{1,5})', it.get('numero_edital') or '') or re.search(r'Edicao_(\d+)', t)
            yield Gazette(date=d, edition_number=n.group(1) if n else '',
                          is_extra_edition=bool(re.search(r'extra|suplement', t, re.I)) or bool(it.get('is_errata')),
                          file_urls=[f"{self.BASE}/uploads/{it['storage_path']}"], power='executive')
        if (d_.get('totalPages') or 1) > pagina:
            yield scrapy.Request(f'{self.BASE}/api/public/documentos?year={a}&month={m}&limit=100&page={pagina + 1}',
                                 callback=self.parse_api, cb_kwargs=dict(a=a, m=m, pagina=pagina + 1))


class RjParacambiAnoSpider(_Base2):
    """Paracambi: uma página por ano (diario-oficial-eletronico-AAAA/) com os PDFs
    'DOE.Paracambi.Ed<N> DD.MM.AAAA[-Extra|-II Caderno].pdf'. O robô de lista genérico não achava a data."""
    name = 'rj_paracambi_v2'
    TERRITORY_ID = '3303609'
    allowed_domains = ['paracambi.rj.gov.br']
    start_date = date(2017, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False}
    RX = re.compile(r'[^"\'\s>]*DOE\.Paracambi\.Ed\s*(\d+)(?:\s|%20)+(\d{2})\.(\d{2})\.(\d{4})([^"\'<>]*?)\.pdf', re.I)

    async def start(self):
        for ano in range(max(self.start_date.year, 2017), self.end_date.year + 1):
            yield scrapy.Request(f'https://paracambi.rj.gov.br/diario-oficial-eletronico-{ano}/', callback=self.parse_ano)

    def parse_ano(self, response):
        vistos = set()
        for m in self.RX.finditer(response.text):
            url = response.urljoin(m.group(0))
            try:
                d = date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
            except ValueError:
                continue
            if url in vistos or not self.dentro(d):
                continue
            vistos.add(url)
            yield Gazette(date=d, edition_number=m.group(1), is_extra_edition=bool(re.search(r'extra|caderno|suplement', m.group(5), re.I)),
                          file_urls=[url], power='executive')


class _WpMediaSpider(_Base2):
    """Sites WordPress que publicam o diário como arquivo de mídia: /wp-json/wp/v2/media (API pública do próprio
    WordPress) filtrada por PDF, data e um padrão no nome do arquivo."""
    BASE = ''
    BUSCA = ''
    RX_ARQ = re.compile(r'.')
    custom_settings = {'ROBOTSTXT_OBEY': False}

    def _url(self, pagina):
        q = f'mime_type=application/pdf&per_page=100&page={pagina}&orderby=date&order=desc&_fields=date,source_url,title'
        q += f'&after={self.start_date.isoformat()}T00:00:00&before={self.end_date.isoformat()}T23:59:59'
        if self.BUSCA:
            q += f'&search={self.BUSCA}'
        return f'{self.BASE}/wp-json/wp/v2/media?{q}'

    async def start(self):
        yield scrapy.Request(self._url(1), callback=self.parse_wp, cb_kwargs=dict(pagina=1))

    def data_do_arquivo(self, nome, publicado):
        m = re.search(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})', nome)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
        return publicado

    def parse_wp(self, response, pagina):
        try:
            itens = json.loads(response.text)
        except ValueError:
            self.logger.error(f'resposta não é JSON: {response.text[:200]!r}')
            return
        for it in itens:
            url = (it.get('source_url') or '').replace('\\/', '/')
            nome = url.rsplit('/', 1)[-1]
            m = self.RX_ARQ.search(nome)
            if not m:
                continue
            d = self.data_do_arquivo(nome, date.fromisoformat(it['date'][:10]))
            if not self.dentro(d):
                continue
            n = re.search(r'(\d{3,6})', nome)
            yield Gazette(date=d, edition_number=n.group(1) if n else '', is_extra_edition=bool(re.search(r'extra|suplement', nome, re.I)),
                          file_urls=[url], power='executive')
        tot = int(response.headers.get('X-WP-TotalPages', b'1').decode() or 1)
        if pagina < tot and pagina < 60:
            yield scrapy.Request(self._url(pagina + 1), callback=self.parse_wp, cb_kwargs=dict(pagina=pagina + 1))


class RjMiracemaWpSpider(_WpMediaSpider):
    """Miracema: Boletim Oficial em miracema.boletimoficialbr.com.br (WordPress), arquivos 'B.O-<N>-DD.MM.AAAA-Assinado.pdf'."""
    name = 'rj_miracema'
    TERRITORY_ID = '3303005'
    allowed_domains = ['miracema.boletimoficialbr.com.br']
    start_date = date(2023, 7, 1)
    BASE = 'https://miracema.boletimoficialbr.com.br'
    RX_ARQ = re.compile(r'^B\.?O[.\-_ ]', re.I)


class RjTribunaMunicipiosWpSpider(_WpMediaSpider):
    """Tribuna dos Municípios: jornal que publica atos oficiais de prefeituras da região serrana e centro-sul
    (achado por busca em 10/11/2026: Três Rios, Cachoeiras de Macacu). Edição digital 'edicao-digital-<N>.pdf'.
    É jornal, não diário oficial próprio: o município de cada ato sai do texto (cabeçalho do ato)."""
    name = 'rj_tribuna_dos_municipios'
    TERRITORY_ID = '3300000'
    allowed_domains = ['tribunadosmunicipios.com.br']
    start_date = date(2024, 1, 1)
    BASE = 'https://tribunadosmunicipios.com.br'
    RX_ARQ = re.compile(r'^(edicao-digit|tribuna-\d)', re.I)
