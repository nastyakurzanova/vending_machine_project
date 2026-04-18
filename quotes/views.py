"""
Представления для работы с котировками, тренировочными и реальными сделками.
"""
import json
import os
import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import QuerySet
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now

import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from .forms import (
    ReportForm, TradeParamsForm, TimeSettingsForm,
    TrainingTradeForm, RealTradeForm
)
from .models import Quote, TrainingTrade, RealTrade
from .services import AlphaVantageService

# =============================================================================
# Конфигурация шрифтов для PDF (один раз при загрузке модуля)
# =============================================================================
FONT_PATH = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))
    DEFAULT_FONT = 'DejaVuSans'
else:
    DEFAULT_FONT = 'Helvetica'


# =============================================================================
# Вспомогательные функции
# =============================================================================

def get_historical_prices_and_volumes(user, quote) -> tuple[List[float], List[float], List[Dict[str, Any]]]:
    """
    Извлекает исторические данные о ценах и объёмах из тренировочных сделок пользователя.
    Возвращает списки цен, объёмов и список словарей с датами и ценами.
    """
    trades = TrainingTrade.objects.filter(
        user=user, quote=quote
    ).order_by('date')
    
    historical_prices = []
    historical_volumes = []
    historical_data = []
    
    for trade in trades:
        price = float(trade.price)
        historical_prices.append(price)
        historical_volumes.append(float(trade.volume))
        historical_data.append({
            'date': trade.date.strftime('%Y-%m-%d'),
            'price': price
        })
    
    return historical_prices, historical_volumes, historical_data


def generate_sample_historical_data(base_price: float, days: int = 5) -> List[Dict[str, Any]]:
    """
    Генерирует демонстрационные исторические данные, если реальные отсутствуют.
    """
    import datetime
    data = []
    for i in range(days, 0, -1):
        hist_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        hist_price = base_price * (1 + (i - 3) * 0.01)
        data.append({
            'date': hist_date,
            'price': round(hist_price, 4)
        })
    return data


def forecast_prices_to_graph_data(
    forecast_prices: List[float],
    historical_data: List[Dict[str, Any]],
    timeframe: str,                         # новый параметр
    start_date_override: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Преобразует список прогнозируемых цен в список словарей с датами.
    Шаг дат зависит от timeframe.
    """
    import datetime

    # Шаг в днях для каждого периода
    step_days_map = {
        '1d': 1,
        '1w': 7,
        '1m': 30
    }
    step_days = step_days_map.get(timeframe, 1)

    if historical_data:
        last_hist_date = datetime.datetime.strptime(historical_data[-1]['date'], '%Y-%m-%d')
        start_date = last_hist_date
    elif start_date_override:
        start_date = start_date_override
    else:
        start_date = datetime.datetime.now()

    graph_data = []
    for i, price in enumerate(forecast_prices, start=1):
        # Приведение к float
        if isinstance(price, (int, float)):
            price_value = float(price)
        elif isinstance(price, dict):
            price_value = float(price.get('price', 0))
        else:
            try:
                price_value = float(price)
            except (ValueError, TypeError):
                price_value = 0.0

        next_date = start_date + datetime.timedelta(days=i * step_days)
        graph_data.append({
            'date': next_date.strftime('%Y-%m-%d'),
            'price': round(price_value, 4)
        })

    return graph_data

def generate_forecast(
    current_price: float,
    timeframe: str,
    algorithm: str,
    historical_data: Optional[List[float]] = None,
    historical_volumes: Optional[List[float]] = None
) -> List[float]:
    """
    Генерирует список прогнозируемых цен на основе выбранного алгоритма.
    """
    points_count_map = {
        'day': 10,
        'week': 30,
        'month': 90,
        'year': 365
    }
    points_count = points_count_map.get(timeframe, 10)
    
    forecast = []
    current = float(current_price)
    
    if algorithm == 'random':
        for _ in range(points_count):
            change = (random.random() - 0.5) * 0.05  # ±2.5%
            current *= (1 + change)
            forecast.append(round(current, 4))
    
    elif algorithm == 'moving_average' and historical_data and len(historical_data) >= 3:
        window_size = min(5, len(historical_data))
        last_prices = historical_data[-window_size:]
        if len(last_prices) > 1:
            avg_change = sum(last_prices[i] - last_prices[i-1] for i in range(1, len(last_prices))) / (len(last_prices) - 1)
        else:
            avg_change = 0
        
        for _ in range(points_count):
            current = current + avg_change
            current *= (1 + (random.random() - 0.5) * 0.01)
            forecast.append(round(current, 4))
    
    elif algorithm == 'linear' and historical_data and len(historical_data) >= 2:
        x = list(range(len(historical_data)))
        y = historical_data
        n = len(x)
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator != 0:
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean
            for i in range(1, points_count + 1):
                predicted = intercept + slope * (n + i)
                forecast.append(round(predicted, 4))
        else:
            # Fallback to random
            for _ in range(points_count):
                change = (random.random() - 0.5) * 0.05
                current *= (1 + change)
                forecast.append(round(current, 4))
    
    else:
        # Default: случайное блуждание
        for _ in range(points_count):
            change = (random.random() - 0.5) * 0.03
            current *= (1 + change)
            forecast.append(round(current, 4))
    
    return forecast


def calculate_profit_loss(
    trade_type: str,
    volume: float,
    entry_price: float,
    forecast_prices: List[float]
) -> float:
    """Вычисляет прибыль/убыток сделки на основе последней прогнозной цены."""
    if not forecast_prices:
        return 0.0
    exit_price = forecast_prices[-1]
    if trade_type == 'buy':
        profit = (exit_price - entry_price) * volume
    else:
        profit = (entry_price - exit_price) * volume
    return round(profit, 2)


def clear_session_keys(request, keys: List[str]) -> None:
    """Удаляет указанные ключи из сессии."""
    for key in keys:
        request.session.pop(key, None)


def build_pdf_report(
    response: HttpResponse,
    username: str,
    date_from: str,
    date_to: str,
    trade_type_display: str,
    trades_data: List[Dict[str, Any]],
    total_profit: float
) -> None:
    """Генерирует PDF-отчёт и записывает его в HttpResponse."""
    doc = SimpleDocTemplate(response, pagesize=A4)
    styles = getSampleStyleSheet()
    
    # Применяем шрифт с поддержкой кириллицы
    for style_name in styles.byName:
        styles[style_name].fontName = DEFAULT_FONT
    
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
    story.append(Paragraph(f"Отчёт по прибыли за период с {date_from} по {date_to}", title_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Пользователь: {username}", normal_style))
    story.append(Paragraph(f"Тип сделок: {trade_type_display}", normal_style))
    story.append(Spacer(1, 0.3 * inch))
    
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
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(f"Общая прибыль: {total_profit:.2f}", total_style))
    else:
        story.append(Paragraph("Нет сделок за выбранный период.", normal_style))
    
    doc.build(story)


# =============================================================================
# Представления
# =============================================================================

@login_required
def update_forecast_ajax(request):
    """AJAX-эндпоинт для обновления прогноза в реальном времени."""
    if request.method != 'GET' or request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
    try:
        quote_id = request.session.get('selected_quote_id')
        if not quote_id:
            return JsonResponse({'error': 'No quote selected'}, status=400)
        
        quote = Quote.objects.get(id=quote_id)
        price = float(request.session.get('trade_price', quote.current_price))
        timeframe = request.session.get('timeframe', '1d')
        algorithm = request.session.get('algorithm', 'arima')
        
        historical_prices, historical_volumes, _ = get_historical_prices_and_volumes(request.user, quote)
        
        graph_data = generate_forecast(
            price, timeframe, algorithm,
            historical_data=historical_prices or None,
            historical_volumes=historical_volumes or None
        )
        return JsonResponse({'graph_data': graph_data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def realtime_chart(request, quote_id):
    """Отображение графика реального времени для выбранной котировки."""
    quote = get_object_or_404(Quote, id=quote_id)
    cache_key = f'realtime_{quote.id}'
    historical_data = cache.get(cache_key)
    
    if not historical_data:
        historical_data = AlphaVantageService.fetch_historical_prices(quote.name, days=30)
        cache.set(cache_key, historical_data, 60 * 10)  # 10 минут
    
    labels = [item['date'] for item in historical_data]
    prices = [float(item['price']) for item in historical_data]
    
    return render(request, 'quotes/realtime.html', {
        'quote': quote,
        'labels': labels,
        'prices': prices,
    })


@login_required
def profit_report(request):
    """Генерация PDF-отчёта по прибыли."""
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            trade_type = form.cleaned_data['trade_type']
            date_from = form.cleaned_data['date_from']
            date_to = form.cleaned_data['date_to']
            
            trades_data = []
            total_profit = 0.0
            
            # Тренировочные сделки
            if trade_type in ('training', 'both'):
                training_trades = TrainingTrade.objects.filter(
                    user=request.user,
                    date__gte=date_from,
                    date__lte=date_to
                ).order_by('date').select_related('quote')
                
                for t in training_trades:
                    profit = float(t.profit_loss or 0)
                    trades_data.append({
                        'type': 'Тренировочная',
                        'date': t.date,
                        'quote': t.quote.name,
                        'trade_type': t.get_trade_type_display(),
                        'volume': float(t.volume),
                        'price': float(t.price),
                        'profit_loss': profit,
                    })
                    total_profit += profit
            
            # Реальные сделки
            if trade_type in ('real', 'both'):
                real_trades = RealTrade.objects.filter(
                    user=request.user,
                    date__gte=date_from,
                    date__lte=date_to,
                    is_confirmed=True
                ).order_by('date').select_related('quote')
                
                for t in real_trades:
                    profit = 0.0  # Для реальных сделок прибыль пока не считается
                    trades_data.append({
                        'type': 'Реальная',
                        'date': t.date,
                        'quote': t.quote.name,
                        'trade_type': t.get_trade_type_display(),
                        'volume': float(t.volume),
                        'price': float(t.price),
                        'profit_loss': profit,
                    })
                    total_profit += profit
            
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="profit_report_{date_from}_{date_to}.pdf"'
            
            build_pdf_report(
                response,
                request.user.username,
                date_from,
                date_to,
                dict(ReportForm.TRADE_TYPE_CHOICES).get(trade_type, ''),
                trades_data,
                total_profit
            )
            return response
    else:
        form = ReportForm(initial={'date_from': now().date(), 'date_to': now().date()})
    
    return render(request, 'quotes/report_form.html', {'form': form})


@login_required
def quote_list(request):
    """Список всех доступных котировок."""
    quotes = Quote.objects.all()
    return render(request, 'quotes/quote_list.html', {'quotes': quotes})


@login_required
def training_history(request):
    """История тренировочных сделок пользователя."""
    trades = TrainingTrade.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'quotes/training_history.html', {'trades': trades})


@login_required
def time_settings(request):
    """Настройка временных параметров и алгоритма прогнозирования."""
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
    """Установка параметров сделки: дата, объём, цена."""
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
    """Основная страница тренировочного режима с графиком и формой сделки."""
    required_keys = [
        'selected_quote_id', 'trade_date', 'trade_volume',
        'trade_price', 'timeframe', 'algorithm'
    ]
    if not all(key in request.session for key in required_keys):
        messages.error(request, 'Сначала заполните все параметры сделки и настройки')
        return redirect('quotes:quote_list')
    
    quote = get_object_or_404(Quote, id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    price = float(request.session['trade_price'])
    timeframe = request.session['timeframe']
    algorithm = request.session['algorithm']
    asset = quote.name  # для отображения
    
    # Получение исторических данных
    historical_prices, historical_volumes, historical_data = get_historical_prices_and_volumes(
        request.user, quote
    )
    
    if not historical_prices:
        # Демо-данные при отсутствии истории
        sample_data = generate_sample_historical_data(price, days=5)
        historical_data = sample_data
        historical_prices = [item['price'] for item in sample_data]
        historical_volumes = []  # не используется
    
    # Генерация прогноза
    forecast_prices = generate_forecast(
        price, timeframe, algorithm,
        historical_data=historical_prices,
        historical_volumes=historical_volumes
    )
    
    # Подготовка данных для графика (прогноз)
    graph_data = forecast_prices_to_graph_data(forecast_prices, historical_data, timeframe)
    
    # Обработка POST-запроса на совершение сделки
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
                profit_loss=calculate_profit_loss(
                    form.cleaned_data['trade_type'], volume, price, forecast_prices
                )
            )
            request.session['last_training_trade_id'] = trade.id
            return redirect('quotes:training_result')
    else:
        form = TrainingTradeForm()
    
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
    """AJAX-эндпоинт для пересчёта цены и объёма."""
    if request.method != 'POST' or request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'error': 'Неверный запрос'}, status=400)
    
    quote_id = request.POST.get('quote_id')
    volume = request.POST.get('volume')
    price = request.POST.get('price')
    
    try:
        quote = Quote.objects.get(id=quote_id)
        current_price = float(quote.current_price)
        sensitivity = 1000.0
        
        if volume:
            volume_val = float(volume)
            new_price = round(current_price * (1 + volume_val / sensitivity), 4)
            return JsonResponse({'price': new_price, 'volume': volume_val})
        
        elif price:
            price_val = float(price)
            new_volume = round((price_val / current_price - 1) * sensitivity, 2)
            return JsonResponse({'volume': new_volume, 'price': price_val})
        
        else:
            return JsonResponse({'error': 'Не указаны данные'}, status=400)
    except Quote.DoesNotExist:
        return JsonResponse({'error': 'Котировка не найдена'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def training_result(request):
    """Страница с результатом тренировочной сделки."""
    trade_id = request.session.get('last_training_trade_id')
    if not trade_id:
        return redirect('quotes:quote_list')
    
    trade = get_object_or_404(TrainingTrade, id=trade_id)
    
    if request.method == 'POST':
        decision = request.POST.get('decision')
        if decision == 'accept':
            return redirect('quotes:real_trade')
        else:
            clear_session_keys(request, [
                'selected_quote_id', 'trade_date', 'trade_volume',
                'trade_price', 'timeframe'
            ])
            return redirect('quotes:quote_list')
    
    return render(request, 'quotes/training_result.html', {'trade': trade})


@login_required
def real_trade(request):
    """Оформление реальной сделки."""
    required = ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_price']
    if not all(key in request.session for key in required):
        messages.error(request, 'Недостаточно данных для оформления сделки')
        return redirect('quotes:quote_list')
    
    quote = get_object_or_404(Quote, id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    price = float(request.session['trade_price'])
    asset = quote.name
    
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
            clear_session_keys(request, required + ['timeframe'])
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