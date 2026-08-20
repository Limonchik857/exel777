"""Логика сохранения и запуска workflow."""

from django.core.files.base import ContentFile
from django.utils import timezone

from files.models import ProcessedFile, UploadedFile
from files.services import export_dataframe, read_table, suggest_result_name, validate_uploaded
from operations.engine import apply_operation
from operations.services import describe_operation
from operations.validators import OperationError

from .models import Execution, Workflow, WorkflowOperation


def create_workflow_from_session(request, name, description=""):
    """Сохраняет последовательность операций текущей сессии как workflow.

    Экспорты (записи 'export') в workflow не попадают.
    """
    state = request.session.get("processing")
    if not state or not state["history"]:
        return None

    from files import processing as proc

    steps = [h for h in proc.applied_history(state) if h.get("op") != "export"]
    if not steps:
        return None

    workflow = Workflow.objects.create(
        user=request.user,
        name=name.strip()[:150],
        description=description.strip(),
    )
    for index, step in enumerate(steps):
        WorkflowOperation.objects.create(
            workflow=workflow,
            operation_type=step["op"],
            order=index,
            configuration=step.get("config", {}),
        )
    return workflow


def run_workflow(user, workflow, request_file):
    """Запускает workflow на новом файле. Возвращает Execution."""
    execution = Execution.objects.create(
        user=user,
        workflow=workflow,
        status=Execution.Status.PENDING,
    )
    try:
        file_type, safe_name = validate_uploaded(
            request_file, _max_size()
        )
        uploaded = UploadedFile.objects.create(
            user=user,
            original_name=safe_name,
            file=request_file,
            file_type=file_type,
            size=request_file.size,
        )
        df = read_table(uploaded.file.path, file_type)
        uploaded.rows_count = len(df)
        uploaded.columns_count = len(df.columns)
        uploaded.columns = [str(c) for c in df.columns]
        uploaded.save()

        execution.input_file = uploaded
        execution.rows_before = len(df)
        execution.save()

        steps = list(workflow.operations.all())
        applied = []
        for step in steps:
            df, meta = apply_operation(df, step.operation_type, step.configuration)
            applied.append(
                {
                    "op": step.operation_type,
                    "config": step.configuration,
                    "label": describe_operation(step.operation_type, step.configuration),
                    "meta": meta,
                }
            )

        fmt = "xlsx"
        result_name = suggest_result_name(safe_name, fmt)
        data, mime = export_dataframe(df, fmt)

        processed = ProcessedFile.objects.create(
            user=user,
            uploaded_file=uploaded,
            file_type=fmt,
            original_name=result_name,
            source_name=safe_name,
            rows_before=len(df),
            rows_after=len(df),
            operations=applied,
        )
        processed.file.save(result_name, ContentFile(data), save=True)

        execution.output_file = processed
        execution.status = Execution.Status.SUCCESS
        execution.rows_after = len(df)
        execution.completed_at = timezone.now()
        execution.save()
        return execution
    except OperationError as exc:
        execution.status = Execution.Status.FAILED
        execution.error = str(exc)
        execution.completed_at = timezone.now()
        execution.save()
        return execution
    except Exception:
        execution.status = Execution.Status.FAILED
        execution.error = "Не удалось обработать файл. Проверьте его содержимое."
        execution.completed_at = timezone.now()
        execution.save()
        return execution


def _max_size():
    from django.conf import settings

    return settings.DATA_MAX_FILE_SIZE