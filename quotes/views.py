from .services import AlphaVantageService
from django.core.cache import cache
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
from .forms import ReportForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Quote, TrainingTrade, RealTrade
from .forms import QuoteSelectForm, TradeParamsForm, TimeSettingsForm, TrainingTradeForm, RealTradeForm
from .prediction import get_forecaster
from datetime import datetime, timedelta
import os
from .forms import TrainingTradeForm
from django.conf import settings
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from django.http import JsonResponse
import json

@login_required
def update_forecast_ajax(request):
    """AJAX-эндпоинт для обновления прогноза в реальном времени"""
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            quote_id = request.session.get('selected_quote_id')
            if not quote_id:
                return JsonResponse({'error': 'No quote selected'}, status=400)
            
            quote = Quote.objects.get(id=quote_id)
            price = float(request.session.get('trade_price', quote.current_price))
            timeframe = request.session.get('timeframe', '1d')
            algorithm = request.session.get('algorithm', 'arima')
            
            # Получаем исторические данные
            historical_trades = TrainingTrade.objects.filter(
                user=request.user, quote=quote
            ).order_by('date')
            
            historical_prices = [float(t.price) for t in historical_trades]
            historical_volumes = [float(t.volume) for t in historical_trades]
            
            # Генерируем новый прогноз
            graph_data = generate_forecast(
                price, timeframe, algorithm,
                historical_data=historical_prices if historical_prices else None,
                historical_volumes=historical_volumes if historical_volumes else None
            )
            
            return JsonResponse({'graph_data': graph_data})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Регистрируем шрифт (делаем это один раз вне функции, чтобы не регистрировать при каждом запросе)
font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
    DEFAULT_FONT = 'DejaVuSans'
else:
    # fallback на стандартный шрифт, но кириллица не будет работать
    DEFAULT_FONT = 'Helvetica'


@login_required
def realtime_chart(request, quote_id):
    quote = get_object_or_404(Quote, id=quote_id)
    
    # Пытаемся взять данные из кэша (на 10 минут, чтобы не бить API часто)
    cache_key = f'realtime_{quote.id}'
    historical_data = cache.get(cache_key)
    
    if not historical_data:
        historical_data = AlphaVantageService.fetch_historical_prices(quote.name, days=30)
        cache.set(cache_key, historical_data, 60 * 10)  # 10 минут
    
    # Подготовим данные для графика
    labels = [item['date'] for item in historical_data]
    prices = [float(item['price']) for item in historical_data]
    
    context = {
        'quote': quote,
        'labels': labels,
        'prices': prices,
    }
    return render(request, 'quotes/realtime.html', context)


@login_required
def profit_report(request):
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            trade_type = form.cleaned_data['trade_type']
            date_from = form.cleaned_data['date_from']
            date_to = form.cleaned_data['date_to']
            
            # Собираем данные
            trades_data = []
            total_profit = 0
            
            if trade_type in ('training', 'both'):
                trades = TrainingTrade.objects.filter(
                    user=request.user,
                    date__gte=date_from,
                    date__lte=date_to
                ).order_by('date')
                for t in trades:
                    profit = t.profit_loss if t.profit_loss is not None else 0
                    trades_data.append({
                        'type': 'Тренировочная',
                        'date': t.date,
                        'quote': t.quote.name,
                        'trade_type': t.get_trade_type_display(),
                        'volume': t.volume,
                        'price': t.price,
                        'profit_loss': profit,
                    })
                    total_profit += profit
            
            if trade_type in ('real', 'both'):
                trades = RealTrade.objects.filter(
                    user=request.user,
                    date__gte=date_from,
                    date__lte=date_to,
                    is_confirmed=True
                ).order_by('date')
                for t in trades:
                    profit = 0
                    trades_data.append({
                        'type': 'Реальная',
                        'date': t.date,
                        'quote': t.quote.name,
                        'trade_type': t.get_trade_type_display(),
                        'volume': t.volume,
                        'price': t.price,
                        'profit_loss': profit,
                    })
                    total_profit += profit
            
            # Создаём PDF-ответ
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="profit_report_{date_from}_{date_to}.pdf"'
            
            doc = SimpleDocTemplate(response, pagesize=A4)
            styles = getSampleStyleSheet()
            
            # Переопределяем стандартные стили на наш шрифт
            for style_name in styles.byName:
                styles[style_name].fontName = DEFAULT_FONT
            
            # Создаём собственные стили с поддержкой кириллицы
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontName=DEFAULT_FONT,
                fontSize=16,
                textColor=colors.HexColor('#2dd4bf'),
                alignment=TA_CENTER
            )
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName=DEFAULT_FONT,
                fontSize=9
            )
            total_style = ParagraphStyle(
                'TotalStyle',
                parent=styles['Heading2'],
                fontName=DEFAULT_FONT,
                fontSize=14,
                textColor=colors.HexColor('#2dd4bf')
            )
            
            story = []
            
            # Заголовок
            story.append(Paragraph(f"Отчёт по прибыли за период с {date_from} по {date_to}", title_style))
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(f"Пользователь: {request.user.username}", normal_style))
            story.append(Paragraph(f"Тип сделок: {dict(ReportForm.TRADE_TYPE_CHOICES).get(trade_type)}", normal_style))
            story.append(Spacer(1, 0.3*inch))
            
            if trades_data:
                table_data = [['Тип', 'Дата', 'Котировка', 'Сделка', 'Объём', 'Цена', 'Прибыль']]
                for row in trades_data:
                    table_data.append([
                        row['type'],
                        row['date'].strftime('%Y-%m-%d'),
                        row['quote'],
                        row['trade_type'],
                        str(row['volume']),
                        str(row['price']),
                        f"{row['profit_loss']:.2f}"
                    ])
                table_data.append(['', '', '', '', '', 'Итого:', f"{total_profit:.2f}"])
                
                table = Table(table_data, colWidths=[60, 65, 65, 60, 55, 60, 65])
                tbl_style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2dd4bf')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), DEFAULT_FONT),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#0f172f')),
                    ('TEXTCOLOR', (0, 1), (-1, -2), colors.HexColor('#eef2ff')),
                    ('FONTNAME', (0, 1), (-1, -2), DEFAULT_FONT),
                    ('FONTSIZE', (0, 1), (-1, -2), 8),
                    ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#2d3a5e')),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1e2b4f')),
                    ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#2dd4bf')),
                    ('FONTNAME', (0, -1), (-1, -1), DEFAULT_FONT),
                    ('FONTSIZE', (0, -1), (-1, -1), 9),
                ])
                table.setStyle(tbl_style)
                story.append(table)
                story.append(Spacer(1, 0.3*inch))
                story.append(Paragraph(f"Общая прибыль: {total_profit:.2f}", total_style))
            else:
                story.append(Paragraph("Нет сделок за выбранный период.", normal_style))
            
            doc.build(story)
            return response
    else:
        form = ReportForm(initial={'date_from': datetime.today().date(), 'date_to': datetime.today().date()})
    
    return render(request, 'quotes/report_form.html', {'form': form})


@login_required
def quote_list(request):
    quotes = Quote.objects.all()
    return render(request, 'quotes/quote_list.html', {'quotes': quotes})


@login_required
def training_history(request):
    trades = TrainingTrade.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'quotes/training_history.html', {'trades': trades})


@login_required
def time_settings(request):
    if request.method == 'POST':
        form = TimeSettingsForm(request.POST)
        if form.is_valid():
            request.session['timeframe'] = form.cleaned_data['timeframe']
            request.session['algorithm'] = form.cleaned_data['algorithm']
            return redirect('quotes:training')
    else:
        form = TimeSettingsForm()
    return render(request, 'quotes/time_settings.html', {'form': form})


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
            request.session['trade_price'] = str(form.cleaned_data['price'])
            return redirect('quotes:time_settings')
    else:
        initial = {}
        if quote:
            initial['quote'] = quote
        form = TradeParamsForm(initial=initial)
    return render(request, 'quotes/trade_params.html', {'form': form, 'quote': quote})


@login_required
def training(request):
    required = ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_price', 'timeframe', 'algorithm']
    for key in required:
        if key not in request.session:
            messages.error(request, 'Сначала заполните все параметры сделки и настройки')
            return redirect('quotes:quote_list')
    
    quote = Quote.objects.get(id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    asset = quote.name
    price = float(request.session['trade_price'])
    timeframe = request.session['timeframe']
    algorithm = request.session['algorithm']
    
    # Получаем исторические данные из тренировочных сделок
    historical_trades = TrainingTrade.objects.filter(
        user=request.user, quote=quote
    ).order_by('date')
    
    print(f"=== DEBUG: Found {historical_trades.count()} historical trades ===")
    
    # Формируем список исторических данных для графика
    historical_data = []
    historical_prices = []
    historical_volumes = []
    
    for trade in historical_trades:
        historical_data.append({
            'date': trade.date.strftime('%Y-%m-%d'),
            'price': float(trade.price)
        })
        historical_prices.append(float(trade.price))
        historical_volumes.append(float(trade.volume))
    
    print(f"Historical data count: {len(historical_data)}")
    
    # Если нет исторических данных, создаем тестовые данные для демонстрации
    if not historical_prices:
        print("=== WARNING: No historical data found, creating sample data ===")
        # Создаем несколько исторических точек на основе текущей цены
        import datetime
        base_price = price
        for i in range(5, 0, -1):
            hist_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
            hist_price = base_price * (1 + (i - 3) * 0.01)  # Небольшие вариации
            historical_data.append({
                'date': hist_date,
                'price': round(hist_price, 4)
            })
            historical_prices.append(round(hist_price, 4))
        
        print(f"Created {len(historical_prices)} sample historical points")
    
    # Генерируем прогноз (должен возвращать список чисел)
    forecast_prices = generate_forecast(
        price, timeframe, algorithm, 
        historical_data=historical_prices if historical_prices else None,
        historical_volumes=historical_volumes if historical_volumes else None
    )
    
    print(f"Forecast prices type: {type(forecast_prices)}")
    print(f"Forecast prices first 3: {forecast_prices[:3] if forecast_prices else 'None'}")
    
    # Преобразуем прогноз в формат с датами
    import datetime
    graph_data = []
    
    # Определяем последнюю дату
    if historical_data:
        # Если есть исторические данные, берем последнюю дату из истории
        last_historical_date = datetime.datetime.strptime(historical_data[-1]['date'], '%Y-%m-%d')
        start_date = last_historical_date
    else:
        # Если нет исторических данных, используем текущую дату
        start_date = datetime.datetime.now()
    
    # Создаем прогнозные точки
    for i, forecast_price in enumerate(forecast_prices):
        # Убеждаемся, что forecast_price - это число
        if isinstance(forecast_price, (int, float)):
            price_value = float(forecast_price)
        elif isinstance(forecast_price, dict):
            # Если это словарь, извлекаем price
            price_value = float(forecast_price.get('price', 0))
        else:
            # Пытаемся преобразовать в float
            try:
                price_value = float(forecast_price)
            except (ValueError, TypeError):
                price_value = 0.0
        
        next_date = start_date + datetime.timedelta(days=i+1)
        graph_data.append({
            'date': next_date.strftime('%Y-%m-%d'),
            'price': round(price_value, 4)
        })
    
    print(f"Generated graph_data count: {len(graph_data)}")
    if graph_data:
        print(f"First graph_data point: {graph_data[0]}")
    
    if request.method == 'POST':
        form = TrainingTradeForm(request.POST)
        if form.is_valid():
            trade = TrainingTrade.objects.create(
                user=request.user,
                quote=quote,
                date=date,
                volume=volume,
                price=price,
                trade_type=form.cleaned_data['trade_type'],
                profit_loss=calculate_profit_loss(form.cleaned_data['trade_type'], volume, price, forecast_prices)
            )
            request.session['last_training_trade_id'] = trade.id
            return redirect('quotes:training_result')
    else:
        form = TrainingTradeForm()
    
    # Преобразуем в JSON-совместимые форматы
    import json
    context = {
        'quote': quote,
        'date': date,
        'volume': volume,
        'asset': asset,
        'price': price,
        'timeframe': timeframe,
        'historical_data': json.dumps(historical_data),
        'graph_data': json.dumps(graph_data),
        'form': form,
    }
    return render(request, 'quotes/training.html', context)

@login_required
def recalc_price_volume(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        quote_id = request.POST.get('quote_id')
        volume = request.POST.get('volume')
        price = request.POST.get('price')
        
        try:
            quote = Quote.objects.get(id=quote_id)
            current_price = float(quote.current_price)
            sensitivity = 1000.0  
            
            if volume is not None and volume != '':
                volume = float(volume)
                new_price = round(current_price * (1 + volume / sensitivity), 4)
                return JsonResponse({'price': new_price, 'volume': volume})
            
            elif price is not None and price != '':
                price = float(price)
                new_volume = round((price / current_price - 1) * sensitivity, 2)
                return JsonResponse({'volume': new_volume, 'price': price})
            
            else:
                return JsonResponse({'error': 'Не указаны данные'}, status=400)
        except Quote.DoesNotExist:
            return JsonResponse({'error': 'Котировка не найдена'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Неверный запрос'}, status=400)


@login_required
def training_result(request):
    trade_id = request.session.get('last_training_trade_id')
    if not trade_id:
        return redirect('quotes:quote_list')
    trade = get_object_or_404(TrainingTrade, id=trade_id)
    
    if request.method == 'POST':
        decision = request.POST.get('decision')
        if decision == 'accept':
            return redirect('quotes:real_trade')
        else:
            for key in ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_price', 'timeframe']:
                if key in request.session:
                    del request.session[key]
            return redirect('quotes:quote_list')
    
    return render(request, 'quotes/training_result.html', {'trade': trade})


@login_required
def real_trade(request):
    required = ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_price']
    for key in required:
        if key not in request.session:
            messages.error(request, 'Недостаточно данных для оформления сделки')
            return redirect('quotes:quote_list')
    
    quote = Quote.objects.get(id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    asset = quote.name
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
            return redirect('main:index')
    else:
        form = RealTradeForm()
    
    return render(request, 'quotes/real_trade.html', {
        'form': form, 
        'quote': quote, 
        'date': date, 
        'volume': volume, 
        'asset': asset, 
        'price': price
    })


# Вспомогательные функции
def generate_forecast(current_price, timeframe, algorithm, historical_data=None, historical_volumes=None):
    """
    Генерирует прогноз цен
    
    Args:
        current_price: Текущая цена
        timeframe: Временной период (day, week, month)
        algorithm: Алгоритм прогнозирования (random, moving_average, etc.)
        historical_data: Исторические цены (список чисел)
        historical_volumes: Исторические объемы (список чисел)
    
    Returns:
        list: Список прогнозируемых цен (числа)
    """
    import random
    import numpy as np
    
    # Определяем количество точек прогноза в зависимости от timeframe
    points_count = {
        'day': 10,
        'week': 30,
        'month': 90,
        'year': 365
    }.get(timeframe, 10)
    
    forecast = []
    
    if algorithm == 'random':
        # Случайный прогноз
        current = float(current_price)
        for _ in range(points_count):
            change = (random.random() - 0.5) * 0.05  # Изменение от -2.5% до +2.5%
            current = current * (1 + change)
            forecast.append(round(current, 4))
    
    elif algorithm == 'moving_average' and historical_data and len(historical_data) >= 3:
        # Прогноз на основе скользящей средней
        window_size = min(5, len(historical_data))
        last_prices = historical_data[-window_size:]
        avg_change = sum(last_prices[i] - last_prices[i-1] for i in range(1, len(last_prices))) / (len(last_prices) - 1) if len(last_prices) > 1 else 0
        
        current = float(current_price)
        for _ in range(points_count):
            current = current + avg_change
            # Добавляем небольшую случайность
            current = current * (1 + (random.random() - 0.5) * 0.01)
            forecast.append(round(current, 4))
    
    elif algorithm == 'linear' and historical_data and len(historical_data) >= 2:
        # Линейная регрессия
        x = list(range(len(historical_data)))
        y = historical_data
        
        # Простая линейная регрессия
        n = len(x)
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator != 0:
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean
            
            current = float(current_price)
            for i in range(1, points_count + 1):
                predicted = intercept + slope * (n + i)
                forecast.append(round(predicted, 4))
        else:
            # Fallback to random
            current = float(current_price)
            for _ in range(points_count):
                change = (random.random() - 0.5) * 0.05
                current = current * (1 + change)
                forecast.append(round(current, 4))
    
    else:
        # Прогноз по умолчанию (случайное блуждание)
        current = float(current_price)
        for _ in range(points_count):
            change = (random.random() - 0.5) * 0.03
            current = current * (1 + change)
            forecast.append(round(current, 4))
    
    return forecast

def calculate_profit_loss(trade_type, volume, entry_price, forecast_prices):
    if not forecast_prices:
        return 0
    exit_price = forecast_prices[-1]  # последнее число в списке
    if trade_type == 'buy':
        profit = (exit_price - entry_price) * volume
    else:
        profit = (entry_price - exit_price) * volume
    return round(profit, 2)