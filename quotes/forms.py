from django import forms
from .models import Quote, TrainingTrade, RealTrade

class ReportForm(forms.Form):
    TRADE_TYPE_CHOICES = [
        ('training', 'Тренировочные сделки'),
        ('real', 'Реальные сделки'),
        ('both', 'Оба типа'),
    ]
    trade_type = forms.ChoiceField(choices=TRADE_TYPE_CHOICES, label='Тип сделок', initial='both')
    date_from = forms.DateField(label='Дата от', widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Дата до', widget=forms.DateInput(attrs={'type': 'date'}))

class QuoteSelectForm(forms.Form):
    quote = forms.ModelChoiceField(queryset=Quote.objects.all(), label='Котировка', empty_label=None)

class TradeParamsForm(forms.Form):
    date = forms.DateField(label='Дата', widget=forms.DateInput(attrs={'type': 'date'}))
    volume = forms.DecimalField(label='Объём', max_digits=12, decimal_places=2)
    asset = forms.CharField(label='Актив', max_length=50)
    price = forms.DecimalField(label='Цена', max_digits=12, decimal_places=4)

class TimeSettingsForm(forms.Form):
    timeframe = forms.ChoiceField(
        choices=[('1d', '1 день'), ('1w', '1 неделя'), ('1m', '1 месяц')],
        label='Временной период для графика'
    )
    algorithm = forms.ChoiceField(
        choices=[
            ('random', 'Случайное блуждание'),
            ('bert_transformer', 'Анализ тренда через латентное пространство')
        ],
        label='Алгоритм прогнозирования',
        initial='random',
        required=True,
        widget=forms.RadioSelect,
        help_text='''<div class="algorithm-description">
                        <p><strong>Случайное блуждание:</strong> Цена меняется случайным образом в пределах ±5% на каждом шаге. Просто, быстро, без учёта истории.</p>
                        <p><strong>BERT → Transformer:</strong> Сначала исторические цены кодируются в латентное пространство (BERT-подобный энкодер), затем трансформер предсказывает следующие значения на основе этого латентного представления. Учитывает прошлые тренды.</p>
                     </div>'''
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Разрешаем HTML в help_text
        self.fields['algorithm'].help_text = mark_safe(self.fields['algorithm'].help_text)

# Не забудьте импортировать mark_safe
from django.utils.safestring import mark_safe

class TrainingTradeForm(forms.ModelForm):
    class Meta:
        model = TrainingTrade
        fields = ['trade_type', 'volume', 'price']
        widgets = {
            'trade_type': forms.RadioSelect,
            'volume': forms.NumberInput(attrs={'step': '0.01'}),
            'price': forms.NumberInput(attrs={'step': '0.0001'}),
        }

class RealTradeForm(forms.ModelForm):
    class Meta:
        model = RealTrade
        fields = ['trade_type', 'volume', 'price']
        widgets = {
            'trade_type': forms.RadioSelect,
            'volume': forms.NumberInput(attrs={'step': '0.01'}),
            'price': forms.NumberInput(attrs={'step': '0.0001'}),
        }