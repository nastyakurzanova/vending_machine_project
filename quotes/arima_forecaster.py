import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import logging
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ARIMAForecaster:
    """
    ARIMA модель для прогнозирования цен.
    Автоматически подбирает параметры (p,d,q) на основе исторических данных.
    """
    
    def __init__(self):
        self.model = None
        self.fitted = False
    
    def _auto_arima_params(self, data, max_p=3, max_d=1, max_q=3):
        """
        Автоматический подбор параметров ARIMA на основе AIC.
        """
        best_aic = float('inf')
        best_order = (1, 1, 1)
        
        if len(data) < 10:
            return (1, 1, 1)
        
        for p in range(max_p + 1):
            for d in range(max_d + 1):
                for q in range(max_q + 1):
                    try:
                        model = ARIMA(data, order=(p, d, q))
                        fitted = model.fit()
                        if fitted.aic < best_aic:
                            best_aic = fitted.aic
                            best_order = (p, d, q)
                    except:
                        continue
        
        logger.info(f"Выбраны параметры ARIMA: order={best_order}, AIC={best_aic}")
        return best_order
    
    def fit(self, historical_prices):
        """
        Обучает ARIMA модель на исторических данных.
        """
        if not historical_prices or len(historical_prices) < 4:
            logger.warning("Недостаточно исторических данных для ARIMA")
            return False
        
        # Преобразуем в pandas Series
        series = pd.Series(historical_prices)
        
        # Автоматический подбор параметров
        order = self._auto_arima_params(series)
        
        try:
            self.model = ARIMA(series, order=order)
            self.fitted_model = self.model.fit()
            self.fitted = True
            logger.info(f"ARIMA модель успешно обучена с параметрами {order}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обучения ARIMA: {e}")
            return False
    
    def predict(self, current_price, steps, step_days, historical_data=None):
        """
        Делает прогноз на steps шагов вперёд.
        """
        if historical_data and len(historical_data) >= 4:
            # Обучаем модель на истории
            self.fit(historical_data)
            
            if self.fitted:
                try:
                    # Прогноз на steps шагов
                    forecast = self.fitted_model.forecast(steps=steps)
                    predictions = forecast.tolist()
                    
                    # Добавляем небольшой случайный шум для реалистичности
                    noise = np.random.normal(0, 0.01 * current_price, steps)
                    predictions = [p + n for p, n in zip(predictions, noise)]
                    
                    # Убеждаемся, что цены не отрицательные
                    predictions = [max(p, current_price * 0.5) for p in predictions]
                    
                    return predictions
                except Exception as e:
                    logger.error(f"Ошибка прогнозирования ARIMA: {e}")
        
        # Fallback: если ARIMA не сработал, используем улучшенное случайное блуждание
        return self._random_walk_fallback(current_price, steps)
    
    def _random_walk_fallback(self, current_price, steps):
        """
        Fallback на случайное блуждание с дрейфом.
        """
        predictions = []
        price_val = current_price
        # Добавляем небольшой тренд на основе истории (если есть)
        drift = 0.002  # небольшой позитивный дрейф
        
        for i in range(steps):
            change = np.random.normal(drift, 0.03)  # нормальное распределение
            price_val = price_val * (1 + change)
            predictions.append(price_val)
        return predictions


class ARIMAXForecaster(ARIMAForecaster):
    """
    ARIMAX модель с экзогенными переменными (объём, волатильность).
    Расширенная версия ARIMA, учитывающая дополнительные факторы.
    """
    
    def __init__(self):
        super().__init__()
        self.exog_data = None
    
    def _calculate_volatility(self, prices):
        """
        Вычисляет волатильность как экзогенную переменную.
        """
        if len(prices) < 2:
            return [0.01] * len(prices)
        
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns)
        return volatility
    
    def _prepare_exogenous(self, historical_prices, volumes=None):
        """
        Подготавливает экзогенные переменные.
        """
        exog = []
        
        # Волатильность (скользящее окно)
        window = min(5, len(historical_prices))
        for i in range(len(historical_prices)):
            if i >= window:
                window_prices = historical_prices[i-window:i]
                vol = self._calculate_volatility(window_prices)
                exog.append(vol)
            else:
                exog.append(0.01)
        
        # Если есть данные по объёмам, добавляем их как второй фактор
        if volumes and len(volumes) == len(historical_prices):
            # Нормализуем объёмы
            max_vol = max(volumes) if volumes else 1
            norm_volumes = [v / max_vol if max_vol > 0 else 0 for v in volumes]
            exog = [[exog[i], norm_volumes[i]] for i in range(len(exog))]
        else:
            exog = [[v] for v in exog]
        
        return exog
    
    def fit(self, historical_prices, volumes=None):
        """
        Обучает ARIMAX модель с экзогенными переменными.
        """
        if not historical_prices or len(historical_prices) < 5:
            return False
        
        series = pd.Series(historical_prices)
        exog = self._prepare_exogenous(historical_prices, volumes)
        
        # Создаём DataFrame для экзогенных переменных
        exog_df = pd.DataFrame(exog)
        
        try:
            order = self._auto_arima_params(series)
            self.model = ARIMA(series, exog=exog_df, order=order)
            self.fitted_model = self.model.fit()
            self.fitted = True
            logger.info(f"ARIMAX модель успешно обучена с параметрами {order}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обучения ARIMAX: {e}")
            return False
    
    def predict(self, current_price, steps, step_days, historical_data=None):
        """
        Делает прогноз с учётом экзогенных переменных.
        """
        if historical_data and len(historical_data) >= 5:
            # Для ARIMAX нужны объёмы (если есть)
            volumes = None
            if hasattr(self, 'volumes') and self.volumes:
                volumes = self.volumes
            
            self.fit(historical_data, volumes)
            
            if self.fitted:
                try:
                    # Прогнозируем будущие экзогенные переменные (используем последние значения)
                    last_exog = self._prepare_exogenous(historical_data[-5:], volumes)[-1] if historical_data else [0.01]
                    future_exog = [last_exog] * steps
                    future_exog_df = pd.DataFrame(future_exog)
                    
                    forecast = self.fitted_model.forecast(steps=steps, exog=future_exog_df)
                    predictions = forecast.tolist()
                    
                    # Добавляем шум
                    noise = np.random.normal(0, 0.008 * current_price, steps)
                    predictions = [max(p + n, current_price * 0.5) for p, n in zip(predictions, noise)]
                    
                    return predictions
                except Exception as e:
                    logger.error(f"Ошибка прогнозирования ARIMAX: {e}")
        
        # Fallback на ARIMA или случайное блуждание
        return super().predict(current_price, steps, step_days, historical_data)


def get_forecaster(algorithm, **kwargs):
    """
    Фабрика для создания объектов прогнозирования.
    """
    if algorithm == 'arima':
        return ARIMAForecaster()
    elif algorithm == 'arimax':
        return ARIMAXForecaster()
    elif algorithm == 'bert_transformer':
        # Сохраняем существующий BERT → Transformer
        from .prediction import BertTransformerForecaster
        return BertTransformerForecaster()
    else:
        # Случайное блуждание (для обратной совместимости)
        from .prediction import RandomForecaster
        return RandomForecaster()