from django.urls import path
from . import views

app_name = 'quotes'

urlpatterns = [
    path('', views.quote_list, name='quote_list'),
    path('trade_params/<int:quote_id>/', views.trade_params, name='trade_params'),
    path('trade_params/', views.trade_params, name='trade_params_no_quote'),
    path('time_settings/', views.time_settings, name='time_settings'),
    path('training/', views.training, name='training'),
    path('training_result/', views.training_result, name='training_result'),
    path('real_trade/', views.real_trade, name='real_trade'),
    path('training_history/', views.training_history, name='training_history'),
]