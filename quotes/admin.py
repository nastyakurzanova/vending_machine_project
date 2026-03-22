from django.contrib import admin
from .models import Quote, TrainingTrade, RealTrade

admin.site.register(Quote)
admin.site.register(TrainingTrade)
admin.site.register(RealTrade)