from django.conf import settings
from django.db import models

from operations.services import OPERATION_CHOICES


class WorkflowQuerySet(models.QuerySet):
    def annotate_runs(self):
        return self.annotate(
            runs_count=models.Count("executions", distinct=True)
        )


class Workflow(models.Model):
    """Сохранённая последовательность операций обработки (pipeline)."""

    class ScheduleType(models.TextChoices):
        MANUAL = "manual", "Вручную"
        DAILY = "daily", "Ежедневно"
        WEEKLY = "weekly", "Еженедельно"
        MONTHLY = "monthly", "Ежемесячно"
        CUSTOM = "custom", "По дням недели"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workflows",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    schedule_type = models.CharField(
        max_length=10,
        choices=ScheduleType.choices,
        default=ScheduleType.MANUAL,
    )
    schedule_time = models.TimeField(null=True, blank=True)
    schedule_days = models.JSONField(default=list, blank=True)
    timezone = models.CharField(max_length=64, default=settings.TIME_ZONE)
    schedule_active = models.BooleanField(default=False)
    next_run = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    objects = WorkflowQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def schedule_label(self):
        label = self.get_schedule_type_display()
        if self.schedule_active and self.schedule_time:
            label += f" · {self.schedule_time.strftime('%H:%M')} {self.timezone}"
        return label


class WorkflowOperation(models.Model):
    """Одна операция внутри workflow."""

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="operations",
    )
    operation_type = models.CharField(max_length=40, choices=OPERATION_CHOICES)
    order = models.PositiveIntegerField(default=0)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "order"],
                name="uniq_workflow_order",
            )
        ]

    def __str__(self):
        return f"{self.operation_type} #{self.order}"


class Execution(models.Model):
    """Запуск workflow на конкретном файле."""

    class Status(models.TextChoices):
        PENDING = "pending", "В обработке"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="executions",
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="executions",
    )
    input_file = models.ForeignKey(
        "files.UploadedFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_executions",
    )
    output_file = models.ForeignKey(
        "files.ProcessedFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_executions",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rows_before = models.PositiveIntegerField(null=True, blank=True)
    rows_after = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    stage_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def duration(self):
        if not self.completed_at:
            return None
        delta = self.completed_at - self.created_at
        return delta.total_seconds()

    def __str__(self):
        return f"{self.workflow} · {self.pk}"