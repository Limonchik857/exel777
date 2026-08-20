from django import forms

from .models import Workflow

WEEKDAY_CHOICES = [
    (0, "Понедельник"),
    (1, "Вторник"),
    (2, "Среда"),
    (3, "Четверг"),
    (4, "Пятница"),
    (5, "Суббота"),
    (6, "Воскресенье"),
]

MONTH_DAY_CHOICES = [(i, str(i)) for i in range(1, 32)]

TIMEZONE_CHOICES = [
    ("Europe/Moscow", "Москва (UTC+3)"),
    ("Europe/Kaliningrad", "Калининград (UTC+2)"),
    ("Europe/Samara", "Самара (UTC+4)"),
    ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
    ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
    ("Asia/Vladivostok", "Владивосток (UTC+10)"),
    ("UTC", "UTC"),
]


class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ("name", "description")
        labels = {"name": "Название", "description": "Описание"}
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Например: Очистка клиентской базы"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Что делает этот workflow (необязательно)",
                }
            ),
        }


class WorkflowRunForm(forms.Form):
    file = forms.FileField(label="Файл для обработки")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)


class ScheduleDaysField(forms.MultipleChoiceField):
    """Допускает пустое значение (для daily/monthly списки дней не нужны)."""

    def clean(self, value):
        if value in (None, "", [], [""]):
            return []
        return super().clean(value)


class ScheduleForm(forms.ModelForm):
    schedule_days = ScheduleDaysField(
        required=False,
        choices=WEEKDAY_CHOICES,
        label="Дни",
        widget=forms.SelectMultiple(attrs={"size": 7}),
    )

    class Meta:
        model = Workflow
        fields = ("schedule_type", "schedule_time", "schedule_days", "timezone", "schedule_active")
        labels = {
            "schedule_type": "Периодичность",
            "schedule_time": "Время запуска",
            "timezone": "Часовой пояс",
            "schedule_active": "Расписание активно",
        }
        widgets = {
            "schedule_type": forms.Select(),
            "schedule_time": forms.TimeInput(attrs={"type": "time"}),
            "timezone": forms.Select(choices=TIMEZONE_CHOICES),
            "schedule_active": forms.CheckboxInput(),
        }

    def clean(self):
        cleaned = super().clean()
        sched_type = cleaned.get("schedule_type")
        active = cleaned.get("schedule_active")
        if active and sched_type != Workflow.ScheduleType.MANUAL:
            if not cleaned.get("schedule_time"):
                self.add_error("schedule_time", "Укажите время запуска.")
            if sched_type == Workflow.ScheduleType.CUSTOM and not cleaned.get("schedule_days"):
                self.add_error("schedule_days", "Выберите хотя бы один день недели.")
        if not active:
            cleaned["schedule_type"] = Workflow.ScheduleType.MANUAL
            cleaned["schedule_days"] = []
        return cleaned