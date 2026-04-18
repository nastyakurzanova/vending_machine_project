import requests
from decimal import Decimal
from django.conf import settings
from .models import Quote
import logging
import time

logger = logging.getLogger(__name__)

class AlphaVantageService:
    BASE_URL = 'https://www.alphavantage.co/query'

    @classmethod
    def _get_symbol_type(cls, symbol):
        """
        Определяет тип символа:
        - 'forex' для валютных пар (6 букв, заканчивается на USD)
        - 'crypto' для криптовалют (начинается с BTC, ETH и т.п.)
        - 'stock' для акций
        """
        symbol_upper = symbol.upper()
        # Валютная пара: длина 6 и заканчивается на USD (EURUSD, GBPUSD, etc.)
        if len(symbol_upper) == 6 and symbol_upper.endswith('USD'):
            return 'forex'
        # Криптовалюта
        if symbol_upper.startswith('BTC') or symbol_upper.startswith('ETH') or symbol_upper.startswith('XRP'):
            return 'crypto'
        return 'stock'

    @classmethod
    def fetch_current_price(cls, symbol):
        """Получает текущую цену для символа."""
        symbol_type = cls._get_symbol_type(symbol)
        clean_symbol = symbol.replace('/', '')

        if symbol_type == 'forex':
            from_currency = clean_symbol[:3]
            to_currency = clean_symbol[3:]
            params = {
                'function': 'CURRENCY_EXCHANGE_RATE',
                'from_currency': from_currency,
                'to_currency': to_currency,
                'apikey': settings.ALPHA_VANTAGE_API_KEY
            }
            price_path = ['Realtime Currency Exchange Rate', '5. Exchange Rate']
        elif symbol_type == 'crypto':
            # Для криптовалют используем CURRENCY_EXCHANGE_RATE
            from_currency = clean_symbol[:3]
            params = {
                'function': 'CURRENCY_EXCHANGE_RATE',
                'from_currency': from_currency,
                'to_currency': 'USD',
                'apikey': settings.ALPHA_VANTAGE_API_KEY
            }
            price_path = ['Realtime Currency Exchange Rate', '5. Exchange Rate']
        else:
            # Акции
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': clean_symbol,
                'apikey': settings.ALPHA_VANTAGE_API_KEY
            }
            price_path = ['Global Quote', '05. price']

        try:
            response = requests.get(cls.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            obj = data
            for key in price_path:
                obj = obj.get(key, {})
                if obj is None:
                    break
            if obj and isinstance(obj, (str, Decimal)):
                price_str = str(obj)
                if price_str:
                    return Decimal(price_str)
                else:
                    logger.warning(f"Пустая цена для {symbol}.")
            else:
                logger.warning(f"Неожиданный формат ответа для {symbol}: {data}")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при запросе к Alpha Vantage для {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при получении цены для {symbol}: {e}")
            return None

    @classmethod
    def fetch_historical_prices(cls, symbol, days=30):
        """
        Получает исторические дневные цены (close) для символа.
        Возвращает список словарей [{'date': 'YYYY-MM-DD', 'price': Decimal}, ...]
        """
        symbol_type = cls._get_symbol_type(symbol)
        clean_symbol = symbol.replace('/', '')

        if symbol_type == 'forex':
            function = 'FX_DAILY'
            price_key = '4. close'
            from_currency = clean_symbol[:3]
            to_currency = clean_symbol[3:]
            params = {
                'function': function,
                'from_symbol': from_currency,
                'to_symbol': to_currency,
                'apikey': settings.ALPHA_VANTAGE_API_KEY
            }
            time_series_key = 'Time Series FX (Daily)'
        elif symbol_type == 'crypto':
            function = 'DIGITAL_CURRENCY_DAILY'
            price_key = '4a. close (USD)'
            params = {
                'function': function,
                'symbol': clean_symbol,
                'market': 'USD',
                'apikey': settings.ALPHA_VANTAGE_API_KEY
            }
            time_series_key = 'Time Series (Digital Currency Daily)'
        else:
            function = 'TIME_SERIES_DAILY'
            price_key = '4. close'
            params = {
                'function': function,
                'symbol': clean_symbol,
                'apikey': settings.ALPHA_VANTAGE_API_KEY
            }
            time_series_key = 'Time Series (Daily)'

        try:
            response = requests.get(cls.BASE_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            series = data.get(time_series_key, {})
            if not series:
                logger.warning(f"Нет исторических данных для {symbol}: {data}")
                return []

            # Сортируем по дате (от новых к старым) и берём последние 'days' дней
            sorted_items = sorted(series.items(), key=lambda x: x[0], reverse=True)[:days]
            result = []
            for date_str, values in sorted_items:
                price = Decimal(values.get(price_key, 0))
                result.append({'date': date_str, 'price': round(price, 4)})

            # Возвращаем в хронологическом порядке (от старых к новым)
            return list(reversed(result))
        except Exception as e:
            logger.error(f"Ошибка получения исторических данных для {symbol}: {e}")
            return []


def update_all_quotes():
    """Обновляет текущие цены для всех котировок в базе данных."""
    quotes = Quote.objects.all()
    updated_count = 0
    for quote in quotes:
        logger.info(f"Обновление цены для {quote.name}...")
        
        # Сохраняем текущую цену как предыдущую
        quote.previous_price = quote.current_price
        
        new_price = AlphaVantageService.fetch_current_price(quote.name)
        
        if new_price is not None:
            quote.current_price = new_price
            quote.save()
            updated_count += 1
            logger.info(f"Цена для {quote.name} обновлена с {quote.previous_price} до {new_price}")
        else:
            # Если не удалось получить новую цену, не меняем previous_price
            quote.save()  # сохраняем только updated_at
            logger.warning(f"Не удалось обновить цену для {quote.name}. Старая цена сохранена.")
        
        time.sleep(12)
    
    logger.info(f"Обновление завершено. Обновлено {updated_count} из {quotes.count()} котировок.")
    return updated_count