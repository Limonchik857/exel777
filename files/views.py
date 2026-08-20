from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from operations.engine import apply_operation, column_kind, prepare_df_for_display
from operations.services import (
    OPERATION_ICONS,
    OPERATION_LABELS,
    OPERATION_TYPES,
    QUICK_OPERATIONS,
    FILTER_OPERATORS,
)
from operations.validators import (
    FileValidationError,
    MergeStructureError,
    OperationError,
    TableReadError,
)

from . import processing as proc
from .models import ProcessedFile, UploadedFile
from .services import (
    export_dataframe,
    get_safe_original_name,
    read_table,
    suggest_result_name,
    validate_uploaded,
)

PREVIEW_ROWS = getattr(settings, "PREVIEW_ROWS", 50)


def _format_size(size):
    value = float(size)
    units = ["Б", "КБ", "МБ", "ГБ"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "Б":
                return f"{int(value)} Б"
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{value:.1f} МБ".replace(".", ",")


def _success_message(op_type, meta):
    if op_type == "remove_duplicates":
        return f"Удалено строк: {meta.get('removed', 0)}. Осталось строк: {meta.get('remaining', 0)}."
    if op_type == "remove_empty_rows":
        return f"Удалено пустых строк: {meta.get('removed', 0)}. Осталось строк: {meta.get('remaining', 0)}."
    if op_type == "drop_columns":
        return f"Удалено столбцов: {len(meta.get('columns', []))}."
    if op_type == "filter":
        return f"Удалено строк: {meta.get('removed', 0)}. Осталось строк: {meta.get('remaining', 0)}."
    if op_type == "sort":
        return "Сортировка применена."
    if op_type == "find_replace":
        return f"Выполнено замен: {meta.get('replacements', 0)}."
    if op_type == "normalize_phone":
        return f"Телефоны в столбце «{meta.get('column', '')}» приведены к единому виду."
    return "Операция выполнена."


@login_required
def files_index(request):
    uploaded = UploadedFile.objects.filter(user=request.user)
    processed = ProcessedFile.objects.filter(user=request.user)
    return render(
        request,
        "files/index.html",
        {
            "section": "files",
            "uploaded": uploaded,
            "processed": processed,
            "format_size": _format_size,
        },
    )


@login_required
def upload(request):
    if request.method == "POST":
        request_file = request.FILES.get("file")
        if request_file is None:
            messages.error(request, "Выберите файл для загрузки.")
            return redirect("files:upload")

        try:
            file_type, safe_name = validate_uploaded(
                request_file, settings.DATA_MAX_FILE_SIZE
            )
        except FileValidationError as exc:
            messages.error(request, str(exc))
            return redirect("files:upload")

        uploaded = UploadedFile.objects.create(
            user=request.user,
            original_name=safe_name,
            file=request_file,
            file_type=file_type,
            size=request_file.size,
        )
        try:
            df = read_table(uploaded.file.path, file_type)
        except TableReadError as exc:
            uploaded.delete()
            messages.error(request, str(exc))
            return redirect("files:upload")

        columns = [str(c) for c in df.columns]
        uploaded.rows_count = len(df)
        uploaded.columns_count = len(columns)
        uploaded.columns = columns
        uploaded.save()

        proc.clear_session(request)
        proc.start_session(
            request,
            uploaded.id,
            safe_name,
            df,
            columns,
            len(df),
        )
        messages.success(
            request,
            f"Файл «{safe_name}» загружен: {len(df)} строк, {len(columns)} столбцов.",
        )
        return redirect("files:processor")

    return render(
        request,
        "files/upload.html",
        {
            "section": "files",
            "op_types": [
                {"key": key, "label": label, "icon": OPERATION_ICONS[key]}
                for key, label in OPERATION_TYPES
            ],
        },
    )


@login_required
def processor(request):
    if not proc.has_session(request):
        messages.info(request, "Сначала загрузите файл.")
        return redirect("files:upload")

    state = proc.get_state(request)
    df = proc.current_df(request)
    uploaded = UploadedFile.objects.filter(
        pk=state["uploaded_file_id"], user=request.user
    ).first()
    if uploaded is None:
        proc.clear_session(request)
        messages.error(request, "Исходный файл не найден. Загрузите файл заново.")
        return redirect("files:upload")

    columns = [str(c) for c in df.columns]
    column_types = {c: column_kind(df[c]) for c in columns}
    preview_df = prepare_df_for_display(df.head(PREVIEW_ROWS))
    preview_rows_data = preview_df.to_dict("records")
    preview_rows = len(preview_rows_data)
    total_rows = len(df)

    active_op = request.GET.get("op", "")
    if active_op and active_op not in [k for k, _ in OPERATION_TYPES]:
        active_op = ""

    op_list = [
        {
            "key": key,
            "label": label,
            "icon": OPERATION_ICONS[key],
        }
        for key, label in OPERATION_TYPES
    ]

    return render(
        request,
        "files/processor.html",
        {
            "section": "files",
            "state": state,
            "uploaded": uploaded,
            "source_name": state["source_name"],
            "file_size_display": _format_size(uploaded.size),
            "columns": columns,
            "column_types": column_types,
            "preview_df": preview_rows_data,
            "preview_rows": preview_rows,
            "total_rows": total_rows,
            "history": proc.applied_history(state),
            "history_count": len(proc.applied_history(state)),
            "op_list": op_list,
            "active_op": active_op,
            "filter_operators": FILTER_OPERATORS,
            "quick_ops": QUICK_OPERATIONS,
            "icons": OPERATION_ICONS,
            "labels": OPERATION_LABELS,
            "can_undo": state["current"] > 0,
            "can_redo": state["current"] < len(state["versions"]) - 1,
        },
    )


@login_required
def apply_operation_view(request):
    if request.method != "POST":
        return redirect("files:processor")
    if not proc.has_session(request):
        messages.error(request, "Сначала загрузите файл.")
        return redirect("files:upload")

    op_type = request.POST.get("op", "")
    config = _build_config(op_type, request.POST)

    if config is None:
        messages.error(request, "Не заполнены параметры операции.")
        return redirect("files:processor")

    try:
        df = proc.current_df(request)
        result, meta = apply_operation(df, op_type, config)
    except OperationError as exc:
        messages.error(request, str(exc))
        return redirect("files:processor")
    except Exception:
        messages.error(request, "Произошла ошибка при обработке. Проверьте данные.")
        return redirect("files:processor")

    proc.apply_operation(request, result, op_type, config, meta)
    messages.success(request, _success_message(op_type, meta))
    return redirect(reverse("files:processor") + f"?op={op_type}")


def _build_config(op_type, post):
    try:
        if op_type == "remove_duplicates":
            scope = post.get("scope", "all")
            columns = [c for c in post.getlist("columns") if c] if scope == "selected" else []
            if scope == "selected" and not columns:
                return None
            return {"columns": columns}

        if op_type == "drop_columns":
            columns = [c for c in post.getlist("columns") if c]
            if not columns:
                return None
            return {"columns": columns}

        if op_type == "filter":
            column = post.get("column", "")
            operator = post.get("operator", "")
            value = post.get("value", "")
            if not column or not operator or value == "":
                return None
            return {"column": column, "operator": operator, "value": value}

        if op_type == "sort":
            column = post.get("column", "")
            order = post.get("order", "asc")
            if not column:
                return None
            return {"column": column, "ascending": order == "asc"}

        if op_type == "find_replace":
            find = post.get("find", "")
            replace = post.get("replace", "")
            scope = post.get("scope", "all")
            column = post.get("column", "") if scope == "column" else ""
            if not find:
                return None
            return {"find": find, "replace": replace, "all_columns": scope == "all", "column": column}

        if op_type == "remove_empty_rows":
            return {}

        if op_type == "normalize_phone":
            column = post.get("column", "")
            if not column:
                return None
            return {"column": column}
    except Exception:
        return None
    return None


@login_required
def undo(request):
    if request.method == "POST" and proc.undo(request):
        messages.success(request, "Операция отменена.")
    return redirect("files:processor")


@login_required
def redo(request):
    if request.method == "POST" and proc.redo(request):
        messages.success(request, "Операция повторена.")
    return redirect("files:processor")


@login_required
def reset(request):
    if request.method == "POST":
        proc.clear_session(request)
        messages.info(request, "Обработка сброшена.")
    return redirect("files:upload")


@login_required
def download(request):
    if not proc.has_session(request):
        messages.error(request, "Нет данных для скачивания.")
        return redirect("files:upload")

    fmt = request.GET.get("fmt", "xlsx")
    if fmt not in ("xlsx", "csv"):
        fmt = "xlsx"

    df = proc.current_df(request)
    state = proc.get_state(request)

    try:
        data, mime = export_dataframe(df, fmt)
    except Exception:
        messages.error(request, "Произошла ошибка при обработке.")
        return redirect("files:processor")

    result_name = suggest_result_name(state["source_name"], fmt)
    result_path = f"user_results/{request.user.id}/{timezone.now().strftime('%Y%m%d%H%M%S')}/{result_name}"

    from django.core.files.base import ContentFile

    processed = ProcessedFile.objects.create(
        user=request.user,
        uploaded_file_id=state["uploaded_file_id"],
        file_type=fmt,
        original_name=result_name,
        source_name=state["source_name"],
        rows_before=state.get("rows_original", df.shape[0]),
        rows_after=df.shape[0],
        operations=proc.applied_history(state),
    )
    processed.file.save(result_name, ContentFile(data), save=True)

    # Фиксируем экспорт в истории сессии (в workflow не сохраняется)
    state["history"].append(
        {
            "op": "export",
            "config": {"fmt": fmt},
            "label": f"Экспортирован результат: {result_name}",
            "meta": {},
        }
    )
    request.session.modified = True

    response = FileResponse(processed.file.open("rb"), content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="{result_name}"'
    return response


@login_required
def merge(request):
    if request.method == "POST":
        request_files = request.FILES.getlist("files")
        if not request_files:
            messages.error(request, "Выберите файлы для объединения.")
            return redirect("files:merge")

        tables = []
        uploaded_list = []
        try:
            for rf in request_files:
                file_type, safe_name = validate_uploaded(
                    rf, settings.DATA_MAX_FILE_SIZE
                )
                uploaded = UploadedFile.objects.create(
                    user=request.user,
                    original_name=safe_name,
                    file=rf,
                    file_type=file_type,
                    size=rf.size,
                )
                uploaded_list.append(uploaded)
                try:
                    df = read_table(uploaded.file.path, file_type)
                except TableReadError:
                    for u in uploaded_list:
                        u.delete()
                    raise
                tables.append((df, safe_name))

            # Проверка единой структуры
            reference = [str(c) for c in tables[0][0].columns]
            for df, name in tables[1:]:
                current = [str(c) for c in df.columns]
                if current != reference:
                    for u in uploaded_list:
                        u.delete()
                    raise MergeStructureError("Файлы имеют разную структуру: столбцы не совпадают.")

            merged_df = tables[0][0].copy()
            for df, _ in tables[1:]:
                merged_df = _concat_preserving(merged_df, df)

            first_uploaded = uploaded_list[0]
            total_rows = len(merged_df)
            columns = [str(c) for c in merged_df.columns]
            first_uploaded.rows_count = total_rows
            first_uploaded.columns_count = len(columns)
            first_uploaded.columns = columns
            first_uploaded.save()
            for extra in uploaded_list[1:]:
                extra.delete()

            proc.clear_session(request)
            proc.start_session(
                request,
                first_uploaded.id,
                f"merged_{len(tables)}_files.xlsx",
                merged_df,
                columns,
                total_rows,
            )
            messages.success(
                request,
                f"Объединено файлов: {len(tables)}. Итого строк: {total_rows}.",
            )
            return redirect("files:processor")
        except FileValidationError as exc:
            messages.error(request, str(exc))
            return redirect("files:merge")
        except TableReadError as exc:
            messages.error(request, str(exc))
            return redirect("files:merge")
        except MergeStructureError as exc:
            messages.error(request, str(exc))
            return redirect("files:merge")
        except Exception:
            messages.error(request, "Произошла ошибка при объединении файлов.")
            return redirect("files:merge")

    return render(request, "files/merge.html", {"section": "files"})


def _concat_preserving(left, right):
    import pandas as pd

    return pd.concat([left, right], ignore_index=True, sort=False)


@login_required
def history(request):
    processed = ProcessedFile.objects.filter(user=request.user).select_related("uploaded_file")
    return render(
        request,
        "files/history.html",
        {
            "section": "history",
            "processed": processed,
            "format_size": _format_size,
        },
    )