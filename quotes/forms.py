from django import forms
from .models import Quote, TrainingTrade, RealTrade

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
            ('random', 'Случайный (базовый)'),
            ('bert_transformer', 'BERT → Transformer (улучшенный метод)')
        ],
        label='Алгоритм прогнозирования',
        initial='random',
        required=True,
        widget=forms.RadioSelect
    )

class TrainingTradeForm(forms.ModelForm):
    class Meta:
        model = TrainingTrade
        fields = ['trade_type', 'volume', 'price']  # частично, остальное из сессии
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