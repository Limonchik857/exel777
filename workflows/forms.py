from django import forms

from .models import Workflow


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