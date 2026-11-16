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
    """Duque de Caxias: a página diario_oficial_busca.php lê uma lista JSON por mês (POST mesano=M/AAAA, mês SEM zero à esquerda: "05/2026" volta vazio) e
    o PDF sai em diario_oficial_get_anexo.php?codigo=<Codigo_ANEXO>. Conferido em 10/11/2026."""
    name = 'rj_duque_de_caxias_v3'
    TERRITORY_ID = '3301702'
    allowed_domains = ['transparencia.duquedecaxias.rj.gov.br']
    start_date = date(2021, 1, 1)
    BASE = 'https://transparencia.duquedecaxias.rj.gov.br'

    async def start(self):
        for a, m in self.meses():
            yield scrapy.FormRequest(f'{self.BASE}/diario_oficial_get.php', formdata={'mesano': f'{m}/{a}', 'pagina': '1'},
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


class RjItatiaiaWpSpider(_WpMediaSpider):
    """Itatiaia: o site (WordPress) publica o 'Diario-Regular-Ed.-<N>-Ano-<A>.pdf' como mídia (achado em 10/11/2026)."""
    name = 'rj_itatiaia_v2'
    TERRITORY_ID = '3302254'
    allowed_domains = ['itatiaia.rj.gov.br']
    start_date = date(2019, 1, 1)
    BASE = 'https://itatiaia.rj.gov.br'
    BUSCA = 'diario'
    RX_ARQ = re.compile(r'^Diario[-_ ](Regular|Extra|Oficial)', re.I)

# Guapimirim: coberto pelo rj_guapimirim_seq (rj_proprios.py); a API de mídia do WordPress respondeu 401 em 10/11/2026.


class RjMaricaWpSpider(_WpMediaSpider):
    """Maricá: o site (WordPress) publica o Jornal Oficial (JOM_<N>_DD-MM-AAAA.pdf, até 03/2026) e o Diário Oficial
    (DOM_<N>_DD-MM-AAAA_.pdf, numeração nova desde 09/03/2026) como mídia. Achado pela sondagem do PC em 11/11/2026 e
    conferido da nuvem (a API abre). O robô antigo do Querido Diário parou em 10/03/2026. Reenvios do mesmo arquivo
    (sufixo -1, -2...) entram uma vez só: fica o mais recente."""
    name = 'rj_marica_wp'
    TERRITORY_ID = '3302700'
    allowed_domains = ['www.marica.rj.gov.br', 'marica.rj.gov.br']
    start_date = date(2025, 1, 1)
    BASE = 'https://www.marica.rj.gov.br'
    RX_ARQ = re.compile(r'^(DOM|JOM)[_\-]?(\d{1,5})[_\-]', re.I)
    BUSCAS = ('DOM', 'JOM')

    async def start(self):
        self._vistos = set()
        for b in self.BUSCAS:
            self.BUSCA = b
            yield scrapy.Request(self._url(1), callback=self.parse_marica, cb_kwargs=dict(pagina=1, busca=b))

    def _url_b(self, pagina, busca):
        self.BUSCA = busca
        return self._url(pagina)

    def parse_marica(self, response, pagina, busca):
        try:
            itens = json.loads(response.text)
        except ValueError:
            self.logger.error(f'resposta não é JSON: {response.text[:200]!r}')
            return
        for it in itens:   # vem do mais novo para o mais antigo
            url = (it.get('source_url') or '').replace('\\/', '/')
            nome = url.rsplit('/', 1)[-1]
            m = self.RX_ARQ.search(nome)
            if not m:
                continue
            d = self.data_do_arquivo(nome, date.fromisoformat(it['date'][:10]))
            if not self.dentro(d):
                continue
            extra = bool(re.search(r'extra|suplement', nome, re.I))
            chave = (m.group(1).upper(), int(m.group(2)), d, extra)
            if chave in self._vistos:
                continue
            self._vistos.add(chave)
            yield Gazette(date=d, edition_number=str(int(m.group(2))), is_extra_edition=extra, file_urls=[url], power='executive')
        tot = int(response.headers.get('X-WP-TotalPages', b'1').decode() or 1)
        if pagina < tot and pagina < 60:
            yield scrapy.Request(self._url_b(pagina + 1, busca), callback=self.parse_marica, cb_kwargs=dict(pagina=pagina + 1, busca=busca))


class _TranspExibirSpider(_Base2):
    """Portais de transparência com a seção 'Diário Oficial Eletrônico' em /transparencia/exibir/<seção>/<pasta>/<página>/.
    Cada linha da tabela traz 'Edição N', a data de publicação e /transparencia/download/<id>. Pastas (ano, mês) são
    seguidas pelos próprios links da página. Só leitura de página pública."""
    BASE = ''
    SECAO = ''
    custom_settings = {'ROBOTSTXT_OBEY': False, 'DOWNLOAD_DELAY': 1}
    RX_LINHA = re.compile(r'<tr>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>.*?(\d{2})/(\d{2})/(\d{4}).*?</td>\s*<td[^>]*>.*?href="([^"]*/transparencia/download/\d+)"', re.S | re.I)

    async def start(self):
        self._vistos = set()
        yield scrapy.Request(f'{self.BASE}/transparencia/exibir/{self.SECAO}/0/1/', callback=self.parse_pasta)

    def parse_pasta(self, response):
        for tit, dd, mm, aa, url in self.RX_LINHA.findall(response.text):
            tit = re.sub(r'<[^>]+>|\s+', ' ', tit).strip()
            try:
                d = date(int(aa), int(mm), int(dd))
            except ValueError:
                continue
            if url in self._vistos or not self.dentro(d):
                continue
            self._vistos.add(url)
            n = re.search(r'(\d{1,5})', tit)
            yield Gazette(date=d, edition_number=n.group(1) if n else '', is_extra_edition=bool(re.search(r'extra|suplement', tit, re.I)),
                          file_urls=[url], power='executive')
        for p in sorted(set(re.findall(rf'/transparencia/exibir/{self.SECAO}/(\d+)/(\d+)/', response.text))):
            u = f'{self.BASE}/transparencia/exibir/{self.SECAO}/{p[0]}/{p[1]}/'
            if u not in self._vistos:
                self._vistos.add(u)
                yield scrapy.Request(u, callback=self.parse_pasta)


class RjCambuciSpider(_TranspExibirSpider):
    """Cambuci: prefeituradecambuci.rj.gov.br/transparencia/exibir/53/... (domínio achado na sondagem de 11/11/2026;
    abre da nuvem). Edições 529 (10/11/2025) a 711 (10/11/2026) vistas na conferência."""
    name = 'rj_cambuci'
    TERRITORY_ID = '3300902'
    allowed_domains = ['prefeituradecambuci.rj.gov.br']
    start_date = date(2021, 1, 1)
    BASE = 'https://prefeituradecambuci.rj.gov.br'
    SECAO = '53'


class RjMageBioSpider(_Base2):
    """Magé: Boletim Informativo Oficial (BIO), quinzenal, nas páginas públicas /bio/ (BIO<N>.pdf) e /bioextra/
    (BIO-EXTRA-DD-MM-AAAA.pdf). Achado em 16/11/2026. A edição regular não traz data no nome nem na página
    (só a última, como período "16 à 31 de Outubro de 2026"); a data usada é o Last-Modified do PDF no servidor
    (data em que a prefeitura subiu o arquivo), anotada como método. Extra: data do nome do arquivo."""
    name = 'rj_mage_bio'
    TERRITORY_ID = '3302502'
    allowed_domains = ['mage.rj.gov.br']
    start_date = date(2025, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False, 'DOWNLOAD_DELAY': 1}
    BASE = 'https://mage.rj.gov.br'

    async def start(self):
        yield scrapy.Request(f'{self.BASE}/bio/', callback=self.parse_lista)
        yield scrapy.Request(f'{self.BASE}/bioextra/', callback=self.parse_lista)

    def parse_lista(self, response):
        vistos = set()
        for url in re.findall(r'href="([^"]*/BIO/\d{4}/[^"]*\.pdf)"', response.text):
            if url in vistos:
                continue
            vistos.add(url)
            nome = url.rsplit('/', 1)[-1]
            m = re.match(r'BIO-EXTRA-(\d{2})-(\d{2})-(\d{4})', nome, re.I)
            if m:
                try:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                except ValueError:
                    continue
                if self.dentro(d):
                    yield Gazette(date=d, edition_number='', is_extra_edition=True, file_urls=[url], power='executive')
                continue
            m = re.match(r'BIO(\d{1,5})', nome, re.I)
            ano = re.search(r'/BIO/(\d{4})/', url)
            if not m or not ano or int(ano.group(1)) < self.start_date.year:
                continue
            yield scrapy.Request(url, method='HEAD', callback=self.parse_head, cb_kwargs=dict(url=url, ed=str(int(m.group(1)))),
                                 dont_filter=True)

    def parse_head(self, response, url, ed):
        lm = response.headers.get('Last-Modified', b'').decode()
        try:
            d = datetime.strptime(lm, '%a, %d %b %Y %H:%M:%S GMT').date()
        except ValueError:
            self.logger.error(f'BIO {ed}: sem Last-Modified ({lm!r}); edição não entra')
            return
        if self.dentro(d):
            yield Gazette(date=d, edition_number=ed, is_extra_edition=False, file_urls=[url], power='executive')


_MESES_PT = dict(janeiro=1, fevereiro=2, marco=3, abril=4, maio=5, junho=6, julho=7, agosto=8, setembro=9, outubro=10,
                 novembro=11, dezembro=12)
_MESES_PT['março'] = 3


def _data_extenso(s):   # "13 de novembro de 2026"
    m = re.search(r'(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})', s or '')
    if not m or m.group(2).lower() not in _MESES_PT:
        return None
    try:
        return date(int(m.group(3)), _MESES_PT[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


class RjNovaFriburgoSiteSpider(_Base2):
    """Nova Friburgo: diário próprio em diario.novafriburgo.rj.gov.br (link do site da prefeitura, serviço 11).
    Lista paginada /diario-oficial/index?page=N (mais novo primeiro), com 'Edição nº N/AAAA', data por extenso e
    o PDF assinado em /diario-oficial/versao-pdf/<id>. Achado em 16/11/2026; o robô Dioenet não achava edição."""
    name = 'rj_nova_friburgo_site'
    TERRITORY_ID = '3303401'
    allowed_domains = ['diario.novafriburgo.rj.gov.br']
    start_date = date(2025, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False, 'DOWNLOAD_DELAY': 1}
    BASE = 'https://diario.novafriburgo.rj.gov.br'
    RX = re.compile(r'Edi[çc][ãa]o n[ºo°]\s*([\d.]+)(?:/\d{4})?\s*([^<]*)</h4>\s*([^<]+)<.*?href="(/diario-oficial/versao-pdf/\d+)"', re.S | re.I)

    async def start(self):
        yield scrapy.Request(f'{self.BASE}/diario-oficial/index?page=1', callback=self.parse_pagina, cb_kwargs=dict(pagina=1))

    def parse_pagina(self, response, pagina):
        mais_velha = None
        for ed, resto, dtx, link in self.RX.findall(response.text):
            d = _data_extenso(dtx)
            if d is None:
                continue
            mais_velha = d if mais_velha is None else min(mais_velha, d)
            if self.dentro(d):
                extra = bool(re.search(r'extra|suplement', resto + dtx, re.I))
                yield Gazette(date=d, edition_number=ed.replace('.', ''), is_extra_edition=extra,
                              file_urls=[self.BASE + link], power='executive')
        if mais_velha is None:
            self.logger.error(f'página {pagina} sem edição reconhecida')
            return
        if mais_velha >= self.start_date and pagina < 300:
            yield scrapy.Request(f'{self.BASE}/diario-oficial/index?page={pagina + 1}', callback=self.parse_pagina,
                                 cb_kwargs=dict(pagina=pagina + 1))


class RjValencaApiSpider(RjDuqueDeCaxiasApiSpider):
    """Valença: mesmo sistema do portal de transparência de Duque de Caxias ("Boletins Oficiais do Município",
    diario_oficial_get.php com mesano=M/AAAA e PDF em diario_oficial_get_anexo.php). Achado e conferido em 16/11/2026."""
    name = 'rj_valenca_api'
    TERRITORY_ID = '3306107'
    allowed_domains = ['portaltransparencia.valenca.rj.gov.br']
    start_date = date(2025, 1, 1)
    BASE = 'https://portaltransparencia.valenca.rj.gov.br'


class RjVoltaRedondaVrdSpider(_Base2):
    """Volta Redonda: o diário oficial é o "VR Destaque". A página pública /vrdestaque/index.php traz todas as edições
    desde 2019 num campo de seleção, com o PDF em /images/Documentos/VRDestaques/<pasta>/AAAA-MM-DD_<N>[EXTRA].pdf
    (a pasta nem sempre é o ano: 2025 e 2026 ficam em /2024/). Achado pelo navegador do robô em 16/11/2026."""
    name = 'rj_volta_redonda_vrd'
    TERRITORY_ID = '3306305'
    allowed_domains = ['www.voltaredonda.rj.gov.br', 'voltaredonda.rj.gov.br']
    start_date = date(2019, 1, 1)
    custom_settings = {'ROBOTSTXT_OBEY': False, 'DOWNLOAD_DELAY': 1}
    BASE = 'https://www.voltaredonda.rj.gov.br'
    RX = re.compile(r'/(\d{4})-(\d{2})-(\d{2})[_\- ]+(\d{3,5})([^/]*)\.pdf$', re.I)

    async def start(self):
        yield scrapy.Request(f'{self.BASE}/vrdestaque/index.php', callback=self.parse_lista)

    def parse_lista(self, response):
        vistos = set()
        for url in re.findall(r'<option[^>]*value="([^"]+\.pdf)"', response.text, re.I):
            m = self.RX.search(url)
            if not m:
                continue
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if not self.dentro(d) or url in vistos:
                continue
            vistos.add(url)
            yield Gazette(date=d, edition_number=m.group(4), is_extra_edition=bool(re.search(r'extra|part|par\d', m.group(5), re.I)),
                          file_urls=[response.urljoin(url)], power='executive')
