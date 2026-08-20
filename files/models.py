import uuid

from django.conf import settings
from django.db import models


def user_upload_path(instance, filename):
    return f"user_uploads/{instance.user_id}/{uuid.uuid4().hex}/{filename}"


def user_result_path(instance, filename):
    return f"user_results/{instance.user_id}/{uuid.uuid4().hex}/{filename}"


class UploadedFile(models.Model):
    """Исходный файл пользователя (XLSX/CSV)."""

    class Type(models.TextChoices):
        XLSX = "xlsx", "Excel (XLSX)"
        CSV = "csv", "CSV"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to=user_upload_path)
    file_type = models.CharField(max_length=8, choices=Type.choices)
    size = models.PositiveBigIntegerField(default=0)
    rows_count = models.PositiveIntegerField(null=True, blank=True)
    columns_count = models.PositiveIntegerField(null=True, blank=True)
    columns = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    def delete(self, *args, **kwargs):
        if self.file:
            storage, name = self.file.storage, self.file.name
            super().delete(*args, **kwargs)
            if name and storage.exists(name):
                storage.delete(name)
        else:
            super().delete(*args, **kwargs)


class ProcessedFile(models.Model):
    """Результат обработки: файл, готовый к скачиванию."""

    class Type(models.TextChoices):
        XLSX = "xlsx", "Excel (XLSX)"
        CSV = "csv", "CSV"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="processed_files",
    )
    uploaded_file = models.ForeignKey(
        UploadedFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
    )
    file = models.FileField(upload_to=user_result_path)
    file_type = models.CharField(max_length=8, choices=Type.choices)
    original_name = models.CharField(max_length=255)
    source_name = models.CharField(max_length=255, default="")
    rows_before = models.PositiveIntegerField(null=True, blank=True)
    rows_after = models.PositiveIntegerField(null=True, blank=True)
    operations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    def delete(self, *args, **kwargs):
        if self.file:
            storage, name = self.file.storage, self.file.name
            super().delete(*args, **kwargs)
            if name and storage.exists(name):
                storage.delete(name)
        else:
            super().delete(*args, **kwargs)