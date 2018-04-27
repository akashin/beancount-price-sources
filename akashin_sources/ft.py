"""Fetch prices from Morningstar's JSON 'api'
"""

import datetime
import pytz
import logging
import re
import json
from bs4 import BeautifulSoup
from urllib import parse
from urllib import error

from beancount.core.number import D
from beancount.prices import source
from beancount.utils import net_utils

"""
bean-price -e 'GBP:akashin_sources.ft/19753923'
"""


class Source(source.Source):
    "FT API price extractor."

    def get_latest_price(self, ticker):
        return self.get_historical_price(ticker, datetime.date.today())

    def get_ft_symbol(self, security_type, exchange, ticker):
        template = 'http://beta.morningstar.com/{}/{}/{}/quote.html'
        url = template.format(security_type, exchange, ticker)
        try:
            response = net_utils.retrying_urlopen(url)
            if response is None:
                return None
            response = response.read().decode('utf-8').strip()
        except error.HTTPError:
            return None

        soup = BeautifulSoup(response, 'html.parser')
        
        def make_finder(name):
            def meta_finder(a):
                return a.name == 'meta' and 'name' in a.attrs and a['name'] == name
            return meta_finder

        def get_meta(name):
            attr = soup.find_all(make_finder(name))[0]
            return attr['content']

        fetched_exchange_id = get_meta('exchangeId')
        fetched_ticker = get_meta('ticker')
        sec_id = get_meta('secId')

        return sec_id

    def get_historical_price(self, compound_ticker, date):
        """See contract in beancount.prices.source.Source."""

        # security_type, exchange, ticker = compound_ticker.lower().split(':')
        # symbol = self.get_ft_symbol(security_type, exchange, ticker)
        symbol = compound_ticker

        if not symbol:
            logging.info("Could not find secId for %s" % compound_ticker)
            return None

        # Look back some number of days in the past in order to make sure we hop
        # over national holidays.
        begin_date = date - datetime.timedelta(days=5)
        end_date = date

        # template = 'http://mschart.morningstar.com/chartweb/defaultChart?type=getcc&secids={}&dataid={}&startdate={}&enddate={}&currency=&format=1'
        template = 'https://markets.ft.com/data/equities/ajax/get-historical-prices?startDate={}&endDate={}&symbol={}'

        def fmt(d):
            return d.strftime('%Y/%m/%d')

        # symbol = 19753923
        url = template.format(fmt(begin_date), fmt(end_date), symbol)
        logging.info("Fetching %s", url)

        try:
            response = net_utils.retrying_urlopen(url)
            if response is None:
                return None
            response = response.read().decode('utf-8').strip()
            response = json.loads(response)
            if 'status' in response:
                status = response['status']
                if status['code'] != 200:
                    logging.info("HTTP Status: [%s] %s" % (status['code'], status['message']))
                    return None
            soup = BeautifulSoup(response['html'], 'html.parser')
        except error.HTTPError:
            return None

        try:
            entries = soup.find_all('td')
            trade_date = entries[0].find_all('span')[0].contents[0]
            trade_date = datetime.datetime.strptime(trade_date, '%A, %B %d, %Y')
            trade_date = trade_date.replace(tzinfo=pytz.UTC)
            price = D(entries[4].contents[0])

            return source.SourcePrice(price, trade_date, None)
        except:
            import sys
            logging.error("Error parsing data.", sys.exc_info()[0])
            return None

