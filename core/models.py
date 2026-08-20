from django.conf import settings
from django.db import models


class RateLimitLog(models.Model):
    """Учёт попыток действий для rate limiting (пользователь или IP)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rate_limit_logs",
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "action", "created_at"]),
            models.Index(fields=["ip", "action", "created_at"]),
        ]