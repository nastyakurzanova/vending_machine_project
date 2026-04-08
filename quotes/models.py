from django.db import models
from django.contrib.auth.models import User

class Quote(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Название котировки')
    description = models.TextField(blank=True, verbose_name='Описание')
    # в models.py Quote
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Время последнего обновления')
    current_price = models.DecimalField(
        max_digits=12, decimal_places=4, default=100.00,
        verbose_name='Текущая цена'
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Котировка'
        verbose_name_plural = 'Котировки'


class TrainingTrade(models.Model):
    TRADE_TYPE_CHOICES = [
        ('buy', 'Покупка'),
        ('sell', 'Продажа'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, verbose_name='Котировка')
    date = models.DateField(verbose_name='Дата')
    volume = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Объём')
    asset = models.CharField(max_length=50, verbose_name='Актив')
    price = models.DecimalField(max_digits=12, decimal_places=4, verbose_name='Цена')
    trade_type = models.CharField(max_length=4, choices=TRADE_TYPE_CHOICES, verbose_name='Тип сделки')
    profit_loss = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Результат')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.quote.name} - {self.date}"

    class Meta:
        verbose_name = 'Тренировочная сделка'
        verbose_name_plural = 'Тренировочные сделки'

class RealTrade(models.Model):
    TRADE_TYPE_CHOICES = [
        ('buy', 'Покупка'),
        ('sell', 'Продажа'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, verbose_name='Котировка')
    date = models.DateField(verbose_name='Дата')
    volume = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Объём')
    asset = models.CharField(max_length=50, verbose_name='Актив')
    price = models.DecimalField(max_digits=12, decimal_places=4, verbose_name='Цена')
    trade_type = models.CharField(max_length=4, choices=TRADE_TYPE_CHOICES, verbose_name='Тип сделки')
    is_confirmed = models.BooleanField(default=False, verbose_name='Подтверждена')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.quote.name} - {self.date}"

    class Meta:
        verbose_name = 'Реальная сделка'
        verbose_name_plural = 'Реальные сделки'