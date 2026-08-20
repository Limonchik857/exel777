from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Удаляет processing-сессии (временные версии таблиц) старше заданного времени."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="Порог возраста в часах (по умолчанию PROCESSING_RETENTION_HOURS).",
        )

    def handle(self, *args, **options):
        import shutil

        hours = options["hours"] or settings.PROCESSING_RETENTION_HOURS
        cutoff = timezone.now() - timedelta(hours=hours)

        root = settings.MEDIA_ROOT / "processing"
        if not root.exists():
            self.stdout.write("Processing-папок нет.")
            return

        removed = 0
        for user_dir in sorted(root.iterdir()):
            if not user_dir.is_dir():
                continue
            for session_dir in sorted(user_dir.iterdir()):
                if not session_dir.is_dir():
                    continue
                try:
                    mtime = timezone.datetime.fromtimestamp(
                        session_dir.stat().st_mtime, tz=timezone.get_current_timezone()
                    )
                except OSError:
                    continue
                if mtime < cutoff:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    removed += 1

        self.stdout.write(self.style.SUCCESS(f"Удалено processing-сессий: {removed}"))