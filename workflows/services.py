"""Р›РѕРіРёРєР° СЃРѕС…СЂР°РЅРµРЅРёСЏ Рё Р·Р°РїСѓСЃРєР° workflow."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.utils import timezone

from files.models import ProcessedFile, UploadedFile
from files.services import export_dataframe, read_table, suggest_result_name, validate_uploaded
from operations.engine import apply_operation
from operations.services import WORKFLOW_SAFE_OPERATIONS, describe_operation
from operations.validators import OperationError

from .models import Execution, Workflow, WorkflowOperation


def create_workflow_from_session(request, name, description=""):
    """РЎРѕС…СЂР°РЅСЏРµС‚ РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅРѕСЃС‚СЊ РѕРїРµСЂР°С†РёР№ С‚РµРєСѓС‰РµР№ СЃРµСЃСЃРёРё РєР°Рє workflow.

    Р­РєСЃРїРѕСЂС‚С‹ (Р·Р°РїРёСЃРё 'export') РІ workflow РЅРµ РїРѕРїР°РґР°СЋС‚.
    """
    state = request.session.get("processing")
    if not state or not state["history"]:
        return None

    from files import processing as proc

    steps = [
        h
        for h in proc.applied_history(state)
        if h.get("op") in WORKFLOW_SAFE_OPERATIONS
    ]
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
    """Р—Р°РїСѓСЃРєР°РµС‚ workflow РЅР° РЅРѕРІРѕРј С„Р°Р№Р»Рµ. Р’РѕР·РІСЂР°С‰Р°РµС‚ Execution."""
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

        rows_before = len(df)
        execution.input_file = uploaded
        execution.rows_before = rows_before
        execution.save()

        steps = list(workflow.operations.all())
        applied = []
        for index, step in enumerate(steps):
            try:
                df, meta = apply_operation(df, step.operation_type, step.configuration)
            except OperationError as exc:
                execution.status = Execution.Status.FAILED
                execution.stage_errors = [
                    {
                        "order": index,
                        "op": step.operation_type,
                        "label": describe_operation(step.operation_type, step.configuration),
                        "error": str(exc),
                    }
                ]
                execution.error = f"РЁР°Рі {index + 1}: {str(exc)}"
                execution.completed_at = timezone.now()
                execution.save()
                return execution
            except Exception as exc:
                execution.status = Execution.Status.FAILED
                execution.stage_errors = [
                    {
                        "order": index,
                        "op": step.operation_type,
                        "label": describe_operation(step.operation_type, step.configuration),
                        "error": "РќРµРїСЂРµРґРІРёРґРµРЅРЅР°СЏ РѕС€РёР±РєР° РЅР° С€Р°РіРµ.",
                    }
                ]
                execution.error = f"РЁР°Рі {index + 1}: РЅРµРїСЂРµРґРІРёРґРµРЅРЅР°СЏ РѕС€РёР±РєР°."
                execution.completed_at = timezone.now()
                execution.save()
                return execution
            applied.append(
                {
                    "op": step.operation_type,
                    "config": step.configuration,
                    "label": describe_operation(step.operation_type, step.configuration),
                    "meta": meta,
                }
            )

        rows_after = len(df)
        fmt = "xlsx"
        result_name = suggest_result_name(safe_name, fmt)
        data, mime = export_dataframe(df, fmt)

        processed = ProcessedFile.objects.create(
            user=user,
            uploaded_file=uploaded,
            file_type=fmt,
            original_name=result_name,
            source_name=safe_name,
            rows_before=rows_before,
            rows_after=rows_after,
            operations=applied,
        )
        processed.file.save(result_name, ContentFile(data), save=True)

        execution.output_file = processed
        execution.status = Execution.Status.SUCCESS
        execution.rows_after = rows_after
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
        execution.error = "РќРµ СѓРґР°Р»РѕСЃСЊ РѕР±СЂР°Р±РѕС‚Р°С‚СЊ С„Р°Р№Р». РџСЂРѕРІРµСЂСЊС‚Рµ РµРіРѕ СЃРѕРґРµСЂР¶РёРјРѕРµ."
        execution.completed_at = timezone.now()
        execution.save()
        return execution


def _max_size():
    from django.conf import settings

    return settings.DATA_MAX_FILE_SIZE


def compute_next_run(workflow, now=None):
    """Р’С‹С‡РёСЃР»СЏРµС‚ СЃР»РµРґСѓСЋС‰РёР№ Р·Р°РїСѓСЃРє workflow РїРѕ СЂР°СЃРїРёСЃР°РЅРёСЋ.

    Р’РѕР·РІСЂР°С‰Р°РµС‚ aware datetime РІ timezone workflow (РёР»Рё None, РµСЃР»Рё СЂР°СЃРїРёСЃР°РЅРёРµ
    РЅРµ Р·Р°РґР°РЅРѕ). Р”РЅРё РЅРµРґРµР»Рё: 0=РџРЅ вЂ¦ 6=Р’СЃ; РґР»СЏ monthly schedule_days вЂ” РґРЅРё РјРµСЃСЏС†Р°.
    """
    if not workflow.schedule_active or not workflow.schedule_time:
        return None
    if workflow.schedule_type == Workflow.ScheduleType.MANUAL:
        return None

    if now is None:
        now = timezone.now()

    tz = _zone(workflow.timezone)
    local_now = now.astimezone(tz)
    run_time = workflow.schedule_time
    days = list(workflow.schedule_days or [])

    sched_type = workflow.schedule_type
    candidate = local_now
    for _ in range(366 * 2):
        candidate = candidate + timedelta(days=1)
        candidate = candidate.replace(hour=run_time.hour, minute=run_time.minute, second=0, microsecond=0)
        if sched_type == Workflow.ScheduleType.DAILY:
            return candidate.astimezone(UTC)
        if sched_type == Workflow.ScheduleType.WEEKLY:
            if candidate.weekday() == _weekday_choice(days, local_now.weekday()):
                return candidate.astimezone(UTC)
        elif sched_type == Workflow.ScheduleType.MONTHLY:
            if candidate.day in days:
                return candidate.astimezone(UTC)
        elif sched_type == Workflow.ScheduleType.CUSTOM:
            if candidate.weekday() in days:
                return candidate.astimezone(UTC)
    return None


def _weekday_choice(days, fallback):
    if days:
        return int(days[0])
    return fallback


def save_next_run(workflow, now=None):
    workflow.next_run = compute_next_run(workflow, now)
    workflow.save(update_fields=["next_run"])
    return workflow.next_run


def apply_schedule(workflow, form_data):
    """РџСЂРёРјРµРЅСЏРµС‚ РЅР°СЃС‚СЂРѕР№РєРё СЂР°СЃРїРёСЃР°РЅРёСЏ Рє workflow Рё РїРµСЂРµСЃС‡РёС‚С‹РІР°РµС‚ next_run."""
    workflow.schedule_type = form_data["schedule_type"]
    workflow.schedule_time = form_data["schedule_time"]
    workflow.schedule_days = [
        int(d) for d in form_data.get("schedule_days", []) if str(d).strip().isdigit()
    ]
    workflow.timezone = form_data.get("timezone") or workflow.timezone
    workflow.schedule_active = bool(form_data.get("schedule_active", False))
    workflow.save(update_fields=[
        "schedule_type", "schedule_time", "schedule_days",
        "timezone", "schedule_active", "next_run",
    ])
    save_next_run(workflow)


def run_due_pipelines(now=None):
    """Р—Р°РїСѓСЃРєР°РµС‚ РІСЃРµ Р°РєС‚РёРІРЅС‹Рµ СЂР°СЃРїРёСЃР°РЅРёСЏ, РІСЂРµРјСЏ РєРѕС‚РѕСЂС‹С… РЅР°СЃС‚СѓРїРёР»Рѕ (РґР»СЏ scheduler).

    Р Р°Р±РѕС‚Р°РµС‚ РЅР° РїРѕСЃР»РµРґРЅРµРј Р·Р°РіСЂСѓР¶РµРЅРЅРѕРј С„Р°Р№Р»Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ. Р’РѕР·РІСЂР°С‰Р°РµС‚
    СЃРїРёСЃРѕРє РєРѕСЂС‚РµР¶РµР№ (workflow, execution).
    """
    if now is None:
        now = timezone.now()
    due = Workflow.objects.filter(
        schedule_active=True,
        next_run__isnull=False,
        next_run__lte=now,
    ).select_related("user")
    results = []
    for workflow in due:
        input_file = (
            UploadedFile.objects.filter(user=workflow.user)
            .order_by("-uploaded_at")
            .first()
        )
        execution = None
        if input_file:
            with input_file.file.open("rb") as fh:
                execution = run_workflow(workflow.user, workflow, fh)
        workflow.last_run_at = now
        save_next_run(workflow, now)
        results.append((workflow, execution))
    return results


def _zone(name):
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")