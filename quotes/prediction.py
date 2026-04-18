import random
import math
import logging

logger = logging.getLogger(__name__)

class BaseForecaster:
    def predict(self, current_price, steps, step_days, historical_data=None):
        raise NotImplementedError

class RandomForecaster(BaseForecaster):
    def predict(self, current_price, steps, step_days, historical_data=None):
        points = []
        delta = 0.05
        price_val = current_price
        for i in range(steps):
            change = random.uniform(-delta, delta)
            price_val = price_val * (1 + change)
            points.append(price_val)
        return points

class BertTransformerForecaster(BaseForecaster):
    def __init__(self):
        self.latent_dim = 8
        self.memory = []

    def _bert_encode(self, historical_prices):
        if not historical_prices or len(historical_prices) < 2:
            return [random.uniform(-1, 1) for _ in range(self.latent_dim)]
        
        recent = historical_prices[-5:]
        mean = sum(recent) / len(recent)
        std = math.sqrt(sum((x - mean) ** 2 for x in recent) / len(recent)) if len(recent) > 1 else 1.0
        if std == 0:
            std = 1.0
        norm = [(x - mean) / std for x in recent]
        
        if len(norm) == 1:
            return [norm[0]] * self.latent_dim
        
        indices = [i / (len(norm) - 1) for i in range(len(norm))]
        target_indices = [i / (self.latent_dim - 1) for i in range(self.latent_dim)]
        latent = []
        for ti in target_indices:
            for j in range(len(indices) - 1):
                if indices[j] <= ti <= indices[j+1]:
                    t = (ti - indices[j]) / (indices[j+1] - indices[j])
                    val = norm[j] * (1 - t) + norm[j+1] * t
                    latent.append(val)
                    break
            else:
                latent.append(norm[-1])
        return latent

    def _transformer_predict(self, latent_vector, steps, trend_strength=0.005):
        predictions = []
        current = 0.0
        base_trend = sum(latent_vector) / len(latent_vector) * trend_strength
        for step in range(steps):
            current = current + base_trend + random.gauss(0, 0.01)
            predictions.append(current)
        return predictions

    def predict(self, current_price, steps, step_days, historical_data=None):
        try:
            latent = self._bert_encode(historical_data)
            rel_changes = self._transformer_predict(latent, steps)
            points = []
            price_val = current_price
            for change in rel_changes:
                price_val = price_val * (1 + change)
                points.append(price_val)
            return points
        except Exception as e:
            logger.error(f"Ошибка в BertTransformerForecaster: {e}")
            fallback = RandomForecaster()
            return fallback.predict(current_price, steps, step_days)


def get_forecaster(algorithm):
    """
    Фабрика для создания объектов прогнозирования.
    Поддерживает: arima, arimax, bert_transformer, random
    """
    if algorithm == 'arima':
        try:
            from .arima_forecaster import ARIMAForecaster
            return ARIMAForecaster()
        except ImportError as e:
            logger.warning(f"ARIMA не доступен: {e}. Используем RandomForecaster.")
            return RandomForecaster()
    elif algorithm == 'arimax':
        try:
            from .arima_forecaster import ARIMAXForecaster
            return ARIMAXForecaster()
        except ImportError as e:
            logger.warning(f"ARIMAX не доступен: {e}. Используем RandomForecaster.")
            return RandomForecaster()
    elif algorithm == 'bert_transformer':
        return BertTransformerForecaster()
    else:
        return RandomForecaster()