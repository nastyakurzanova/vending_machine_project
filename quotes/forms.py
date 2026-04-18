from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from .models import Quote, TrainingTrade, RealTrade

# Константы для выбора
TRADE_TYPE_CHOICES = [
    ('buy', 'Покупка'),
    ('sell', 'Продажа'),
]

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']
        labels = {
            'username': 'Имя пользователя',
            'password1': 'Пароль',
            'password2': 'Подтверждение пароля',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].error_messages = {
            'unique': 'Пользователь с таким именем уже существует.',
            'invalid': 'Введите правильное имя пользователя.',
            'required': 'Обязательное поле.',
        }
        self.fields['password1'].error_messages = {
            'required': 'Обязательное поле.',
        }
        self.fields['password2'].error_messages = {
            'required': 'Обязательное поле.',
            'password_mismatch': 'Введенные пароли не совпадают.',
        }

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        try:
            from django.contrib.auth import password_validation
            password_validation.validate_password(password1, self.instance)
        except forms.ValidationError as e:
            messages = {
                'The password is too similar to the username.': 'Пароль слишком похож на имя пользователя.',
                'This password is too short. It must contain at least 8 characters.': 'Пароль слишком короткий. Минимальная длина — 8 символов.',
                'This password is too common.': 'Пароль слишком простой и часто используется.',
                'This password is entirely numeric.': 'Пароль не может состоять только из цифр.',
            }
            new_messages = [messages.get(msg, msg) for msg in e.messages]
            raise forms.ValidationError(new_messages)
        return password1


class CustomAuthenticationForm(AuthenticationForm):
    class Meta:
        model = User
        fields = ['username', 'password']
        labels = {
            'username': 'Имя пользователя',
            'password': 'Пароль',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].error_messages = {
            'invalid': 'Введите правильное имя пользователя.',
            'required': 'Обязательное поле.',
        }
        self.fields['password'].error_messages = {
            'required': 'Обязательное поле.',
        }


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
    price = forms.DecimalField(label='Цена', max_digits=12, decimal_places=4)


class TimeSettingsForm(forms.Form):
    timeframe = forms.ChoiceField(
        choices=[('1d', '1 день'), ('1w', '1 неделя'), ('1m', '1 месяц')],
        label='Временной период для графика'
    )
    algorithm = forms.ChoiceField(
        choices=[
            ('random', 'Arima'),
            ('bert_transformer', 'Bert')
        ],
        label='Алгоритм прогнозирования',
        initial='random',
        required=True,
        widget=forms.RadioSelect,
        help_text='''<div class="algorithm-description">
                        <p><strong>Arima:</strong> Цена меняется случайным образом в пределах ±5% на каждом шаге. Просто, быстро, без учёта истории.</p>
                        <p><strong>BERT:</strong> Статистический метод для анализа и прогнозирования временных рядов. Он использует исторические данные для выявления закономерностей и построения прогнозов будущих значений.</p>
                     </div>'''
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['algorithm'].help_text = mark_safe(self.fields['algorithm'].help_text)


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
    trade_type = forms.ChoiceField(
        choices=TRADE_TYPE_CHOICES,
        widget=forms.RadioSelect,
        label='Тип сделки'
    )

    class Meta:
        model = RealTrade
        fields = ['trade_type', 'volume', 'price']
        widgets = {
            'volume': forms.NumberInput(attrs={
                'step': '0.01',
                'placeholder': 'Введите объём',
                'class': 'form-control'
            }),
            'price': forms.NumberInput(attrs={
                'step': '0.0001',
                'placeholder': 'Введите цену',
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Дополнительные CSS-классы (не обязательно, но оставим)
        self.fields['volume'].widget.attrs.update({'class': 'form-control'})
        self.fields['price'].widget.attrs.update({'class': 'form-control'})
    class Meta:
        model = RealTrade
        fields = ['trade_type', 'volume', 'price']
        widgets = {
            'trade_type': forms.RadioSelect(),
            'volume': forms.NumberInput(attrs={
                'step': '0.01',
                'placeholder': 'Введите объём',
                'class': 'form-control'
            }),
            'price': forms.NumberInput(attrs={
                'step': '0.0001',
                'placeholder': 'Введите цену',
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Убираем пустой пункт выбора в радиокнопках
        self.fields['trade_type'].empty_label = None
        # Дополнительно обновляем классы (можно оставить, не помешает)
        self.fields['volume'].widget.attrs.update({'class': 'form-control'})
        self.fields['price'].widget.attrs.update({'class': 'form-control'})