from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Quote, TrainingTrade, RealTrade
from .forms import QuoteSelectForm, TradeParamsForm, TimeSettingsForm, TrainingTradeForm, RealTradeForm
import random
from datetime import datetime, timedelta

@login_required
def quote_list(request):
    quotes = Quote.objects.all()
    return render(request, 'quotes/quote_list.html', {'quotes': quotes})

@login_required
def training_history(request):
    trades = TrainingTrade.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'quotes/training_history.html', {'trades': trades})

@login_required
def trade_params(request, quote_id=None):
    if quote_id:
        quote = get_object_or_404(Quote, id=quote_id)
        request.session['selected_quote_id'] = quote.id
    else:
        quote = None
        if 'selected_quote_id' in request.session:
            quote = get_object_or_404(Quote, id=request.session['selected_quote_id'])
    
    if request.method == 'POST':
        form = TradeParamsForm(request.POST)
        if form.is_valid():
            request.session['trade_date'] = form.cleaned_data['date'].isoformat()
            request.session['trade_volume'] = str(form.cleaned_data['volume'])
            request.session['trade_asset'] = form.cleaned_data['asset']
            request.session['trade_price'] = str(form.cleaned_data['price'])
            return redirect('quotes:time_settings')   # <-- исправлено
    else:
        initial = {}
        if quote:
            initial['quote'] = quote
        form = TradeParamsForm(initial=initial)
    return render(request, 'quotes/trade_params.html', {'form': form, 'quote': quote})

@login_required
def time_settings(request):
    if request.method == 'POST':
        form = TimeSettingsForm(request.POST)
        if form.is_valid():
            request.session['timeframe'] = form.cleaned_data['timeframe']
            return redirect('quotes:training')   # <-- исправлено
    else:
        form = TimeSettingsForm()
    return render(request, 'quotes/time_settings.html', {'form': form})

@login_required
def training(request):
    required = ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_asset', 'trade_price', 'timeframe']
    for key in required:
        if key not in request.session:
            messages.error(request, 'Сначала заполните все параметры сделки и настройки')
            return redirect('quotes:quote_list')   # <-- исправлено
    
    quote = Quote.objects.get(id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    asset = request.session['trade_asset']
    price = float(request.session['trade_price'])
    timeframe = request.session['timeframe']
    
    graph_data = generate_forecast(price, timeframe)
    
    if request.method == 'POST':
        form = TrainingTradeForm(request.POST)
        if form.is_valid():
            trade = TrainingTrade.objects.create(
                user=request.user,
                quote=quote,
                date=date,
                volume=volume,
                asset=asset,
                price=price,
                trade_type=form.cleaned_data['trade_type'],
                profit_loss=calculate_profit_loss(form.cleaned_data['trade_type'], volume, price, graph_data)
            )
            request.session['last_training_trade_id'] = trade.id
            return redirect('quotes:training_result')   # <-- исправлено
    else:
        form = TrainingTradeForm()
    
    context = {
        'quote': quote,
        'date': date,
        'volume': volume,
        'asset': asset,
        'price': price,
        'timeframe': timeframe,
        'graph_data': graph_data,
        'form': form,
    }
    return render(request, 'quotes/training.html', context)

@login_required
def training_result(request):
    trade_id = request.session.get('last_training_trade_id')
    if not trade_id:
        return redirect('quotes:quote_list')   # <-- исправлено
    trade = get_object_or_404(TrainingTrade, id=trade_id)
    
    if request.method == 'POST':
        decision = request.POST.get('decision')
        if decision == 'accept':
            return redirect('quotes:real_trade')   # <-- исправлено
        else:
            for key in ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_asset', 'trade_price', 'timeframe']:
                if key in request.session:
                    del request.session[key]
            return redirect('quotes:quote_list')   # <-- исправлено
    
    return render(request, 'quotes/training_result.html', {'trade': trade})

@login_required
def real_trade(request):
    required = ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_asset', 'trade_price']
    for key in required:
        if key not in request.session:
            messages.error(request, 'Недостаточно данных для оформления сделки')
            return redirect('quotes:quote_list')   # <-- исправлено
    
    quote = Quote.objects.get(id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    asset = request.session['trade_asset']
    price = float(request.session['trade_price'])
    
    if request.method == 'POST':
        form = RealTradeForm(request.POST)
        if form.is_valid():
            trade = RealTrade.objects.create(
                user=request.user,
                quote=quote,
                date=date,
                volume=volume,
                asset=asset,
                price=price,
                trade_type=form.cleaned_data['trade_type'],
                is_confirmed=True
            )
            for key in required + ['timeframe']:
                if key in request.session:
                    del request.session[key]
            messages.success(request, f'Сделка №{trade.id} успешно оформлена!')
            return redirect('main:index')   # <-- исправлено
    else:
        form = RealTradeForm()
    
    return render(request, 'quotes/real_trade.html', {'form': form, 'quote': quote, 'date': date, 'volume': volume, 'asset': asset, 'price': price})

# Вспомогательные функции
def generate_forecast(current_price, timeframe):
    points = []
    delta = 0.05
    start_date = datetime.now().date()
    if timeframe == '1d':
        steps = 10
        step_days = 1
    elif timeframe == '1w':
        steps = 10
        step_days = 7
    else:  # '1m'
        steps = 10
        step_days = 30
    price_val = current_price
    for i in range(steps):
        change = random.uniform(-delta, delta)
        price_val = price_val * (1 + change)
        date = start_date + timedelta(days=step_days * i)
        points.append({'date': date.strftime('%Y-%m-%d'), 'price': round(price_val, 4)})
    return points

def calculate_profit_loss(trade_type, volume, entry_price, graph_data):
    if not graph_data:
        return 0
    exit_price = graph_data[-1]['price']
    if trade_type == 'buy':
        profit = (exit_price - entry_price) * volume
    else:
        profit = (entry_price - exit_price) * volume
    return round(profit, 2)