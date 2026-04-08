from django.http import HttpResponse
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
from .forms import ReportForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Quote, TrainingTrade, RealTrade
from .forms import QuoteSelectForm, TradeParamsForm, TimeSettingsForm, TrainingTradeForm, RealTradeForm
from .prediction import get_forecaster
import random
from datetime import datetime, timedelta

import os
from django.conf import settings
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# Регистрируем шрифт (делаем это один раз вне функции, чтобы не регистрировать при каждом запросе)
font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
    DEFAULT_FONT = 'DejaVuSans'
else:
    # fallback на стандартный шрифт, но кириллица не будет работать
    DEFAULT_FONT = 'Helvetica'

@login_required
def profit_report(request):
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            trade_type = form.cleaned_data['trade_type']
            date_from = form.cleaned_data['date_from']
            date_to = form.cleaned_data['date_to']
            
            # Собираем данные (как раньше)
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
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading1'],
                fontName=DEFAULT_FONT,
                fontSize=12,
                textColor=colors.HexColor('#2dd4bf')
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
                # Стиль таблицы с использованием нашего шрифта
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
                    # Для реальных сделок profit_loss нет, считаем? Пока ставим 0
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
            title_style = styles['Title']
            heading_style = ParagraphStyle(
                'Heading1',
                parent=styles['Heading1'],
                fontSize=14,
                textColor=colors.HexColor('#2dd4bf')
            )
            normal_style = styles['Normal']
            
            # Содержимое PDF
            story = []
            
            # Заголовок
            story.append(Paragraph(f"Отчёт по прибыли за период с {date_from} по {date_to}", title_style))
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(f"Пользователь: {request.user.username}", normal_style))
            story.append(Paragraph(f"Тип сделок: {dict(ReportForm.TRADE_TYPE_CHOICES).get(trade_type)}", normal_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Таблица с данными
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
                # Добавляем строку итога
                table_data.append(['', '', '', '', '', 'Итого:', f"{total_profit:.2f}"])
                
                table = Table(table_data, colWidths=[70, 70, 70, 70, 60, 60, 70])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2dd4bf')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#0f172f')),
                    ('TEXTCOLOR', (0, 1), (-1, -2), colors.HexColor('#eef2ff')),
                    ('GRID', (0, 0), (-1, -2), 1, colors.HexColor('#2d3a5e')),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1e2b4f')),
                    ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#2dd4bf')),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ]))
                story.append(table)
                story.append(Spacer(1, 0.3*inch))
                story.append(Paragraph(f"Общая прибыль: {total_profit:.2f}", ParagraphStyle('Total', parent=styles['Heading2'], textColor=colors.HexColor('#2dd4bf'))))
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
            request.session['algorithm'] = form.cleaned_data['algorithm']   # сохраняем выбранный алгоритм
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
def training(request):
    required = ['selected_quote_id', 'trade_date', 'trade_volume', 'trade_asset', 'trade_price', 'timeframe', 'algorithm']
    for key in required:
        if key not in request.session:
            messages.error(request, 'Сначала заполните все параметры сделки и настройки')
            return redirect('quotes:quote_list')
    
    quote = Quote.objects.get(id=request.session['selected_quote_id'])
    date = request.session['trade_date']
    volume = float(request.session['trade_volume'])
    asset = request.session['trade_asset']
    price = float(request.session['trade_price'])
    timeframe = request.session['timeframe']
    algorithm = request.session['algorithm']
    
    # Получаем исторические данные (для умного алгоритма) – например, предыдущие сделки по этой котировке
    historical_prices = list(TrainingTrade.objects.filter(
        user=request.user, quote=quote
    ).order_by('-date').values_list('price', flat=True)[:10])  # последние 10 цен
    historical_prices = [float(p) for p in historical_prices]
    
    print(f"Algorithm: {algorithm}, historical_prices: {historical_prices}")
    graph_data = generate_forecast(price, timeframe, algorithm, historical_prices)
    print(f"Generated graph_data length: {len(graph_data)}")
    

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
def recalc_price_volume(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        quote_id = request.POST.get('quote_id')
        volume = request.POST.get('volume')
        price = request.POST.get('price')
        
        try:
            quote = Quote.objects.get(id=quote_id)
            current_price = float(quote.current_price)
            # Параметр чувствительности: чем больше, тем слабее влияние объёма на цену
            sensitivity = 1000.0  
            
            if volume is not None and volume != '':
                # Если введён объём, пересчитываем цену
                volume = float(volume)
                # price = current_price * (1 + volume / sensitivity)
                new_price = round(current_price * (1 + volume / sensitivity), 4)
                return JsonResponse({'price': new_price, 'volume': volume})
            
            elif price is not None and price != '':
                # Если введена цена, пересчитываем объём
                price = float(price)
                # volume = (price / current_price - 1) * sensitivity
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
def generate_forecast(current_price, timeframe, algorithm='random', historical_data=None):
    """Генерация прогноза с выбранным алгоритмом"""
    if timeframe == '1d':
        steps = 10
        step_days = 1
    elif timeframe == '1w':
        steps = 10
        step_days = 7
    else:  # '1m'
        steps = 10
        step_days = 30
    
    forecaster = get_forecaster(algorithm)
    predicted_prices = forecaster.predict(current_price, steps, step_days, historical_data)
    
    start_date = datetime.now().date()
    points = []
    for i, price_val in enumerate(predicted_prices):
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