"""Запускает pipelines, чьё расписание наступило.

Вызывайте по cron/планировщику, например:
    0 * * * *  venv/bin/python manage.py run_scheduled
"""

from django.core.management.base import BaseCommand

from workflows.services import run_due_pipelines


class Command(BaseCommand):
    help = "Запускает активные pipelines по расписанию (next_run <= now)."

    def handle(self, *args, **options):
        results = run_due_pipelines()
        ran = sum(1 for _, execution in results if execution is not None)
        self.stdout.write(
            self.style.SUCCESS(f"Запущено pipelines: {ran} из {len(results)}")
        )