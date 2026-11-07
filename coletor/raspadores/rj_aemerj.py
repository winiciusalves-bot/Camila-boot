# Diário Oficial dos Municípios do RJ (AEMERJ, plataforma SIGPub), um PDF com vários municípios.
# Reserva para municípios cujo site está fora ou mudou. Usa o raspador-base SIGPub do Querido Diário (MIT).
import datetime

from gazette.spiders.base.sigpub import BaseSigpubSpider


class RjAemerjSpider(BaseSigpubSpider):
    name = "rj_aemerj"
    TERRITORY_ID = "3300000"
    CALENDAR_URL = "https://www.diariomunicipal.com.br/aemerj/"
    start_date = datetime.date(2014, 1, 1)
    custom_settings = {"DOWNLOAD_DELAY": 0.5, "CONCURRENT_REQUESTS_PER_DOMAIN": 4}
