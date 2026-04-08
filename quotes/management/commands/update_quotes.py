from django.core.management.base import BaseCommand
from quotes.services import update_all_quotes

class Command(BaseCommand):
    help = 'Обновляет текущие цены для всех котировок через Alpha Vantage API'

    def handle(self, *args, **options):
        self.stdout.write('Начинаем обновление цен...')
        updated_count = update_all_quotes()
        self.stdout.write(self.style.SUCCESS(f'Успешно обновлено {updated_count} котировок.'))