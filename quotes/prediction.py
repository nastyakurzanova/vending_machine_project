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
        self.latent_dim = 8   # уменьшим размерность для надёжности
        self.memory = []

    def _bert_encode(self, historical_prices):
        """
        Преобразует историю цен в латентный вектор (список float).
        Всегда возвращает вектор длины self.latent_dim.
        """
        # Если история пустая или слишком короткая – возвращаем случайный вектор
        if not historical_prices or len(historical_prices) < 2:
            return [random.uniform(-1, 1) for _ in range(self.latent_dim)]
        
        # Берём последние до 5 значений
        recent = historical_prices[-5:]
        # Нормализуем (без numpy)
        mean = sum(recent) / len(recent)
        std = math.sqrt(sum((x - mean) ** 2 for x in recent) / len(recent)) if len(recent) > 1 else 1.0
        if std == 0:
            std = 1.0
        norm = [(x - mean) / std for x in recent]
        
        # Интерполяция до latent_dim (линейная)
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
        """
        Генерирует последовательность относительных изменений.
        """
        predictions = []
        current = 0.0
        base_trend = sum(latent_vector) / len(latent_vector) * trend_strength
        for step in range(steps):
            current = current + base_trend + random.gauss(0, 0.01)
            predictions.append(current)
        return predictions

    def predict(self, current_price, steps, step_days, historical_data=None):
        try:
            # Шаг 1: латентный вектор
            latent = self._bert_encode(historical_data)
            # Шаг 2: предсказание относительных изменений
            rel_changes = self._transformer_predict(latent, steps)
            # Шаг 3: превращаем в цены
            points = []
            price_val = current_price
            for change in rel_changes:
                price_val = price_val * (1 + change)
                points.append(price_val)
            return points
        except Exception as e:
            logger.error(f"Ошибка в BertTransformerForecaster: {e}")
            # fallback – случайный прогноз
            fallback = RandomForecaster()
            return fallback.predict(current_price, steps, step_days)

def get_forecaster(algorithm):
    if algorithm == 'bert_transformer':
        return BertTransformerForecaster()
    else:
        return RandomForecaster()