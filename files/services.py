"""Чтение, проверка и экспорт таблиц (XLSX/CSV)."""

import csv
import os
import re
from pathlib import Path

import pandas as pd

from operations.validators import (
    ExportError,
    FileValidationError,
    TableReadError,
)

# Разрешённые расширения и MIME-типы
ALLOWED_EXTENSIONS = {".xlsx": "xlsx", ".csv": "csv"}
ALLOWED_MIME = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "text/plain",
    "application/csv",
    "application/x-csv",
}
# Браузеры часто шлют application/octet-stream; пропускаем только для
# разрешённых расширений — само по себе расширение уже проверено.
OCTET_STREAM = "application/octet-stream"

CSV_ENCODINGS = ["utf-8-sig", "cp1251", "utf-8", "latin-1"]

_SAFE_NAME_RE = re.compile(r"[^A-Za-zА-Яа-яЁё0-9_.\- ]+")


def detect_file_type(filename):
    """Возвращает тип файла ('xlsx'/'csv') по расширению или None."""
    suffix = Path(filename).suffix.lower()
    return ALLOWED_EXTENSIONS.get(suffix)


def get_safe_original_name(filename):
    """Оставляет только безопасные символы в имени файла."""
    name = Path(filename).name
    name = _SAFE_NAME_RE.sub("_", name)
    return name.strip() or "file"


def validate_uploaded(request_file, max_size):
    """Проверяет расширение, MIME и размер. Возвращает (file_type, safe_name)."""
    original_name = request_file.name or ""
    file_type = detect_file_type(original_name)
    if file_type is None:
        raise FileValidationError("Формат файла не поддерживается. Разрешены XLSX и CSV.")

    mime = getattr(request_file, "content_type", "") or ""
    if mime and mime != OCTET_STREAM and mime not in ALLOWED_MIME:
        raise FileValidationError("Тип файла не распознан как таблица (XLSX или CSV).")

    if request_file.size > max_size:
        mb = max_size // (1024 * 1024)
        raise FileValidationError(f"Файл слишком большой. Максимальный размер — {mb} МБ.")

    if request_file.size == 0:
        raise FileValidationError("Файл пустой.")

    return file_type, get_safe_original_name(original_name)


def normalize_headers(df):
    """Приводит заголовки к единому виду: без пробелов по краям,
    без пустых имён и без дубликатов."""
    new_columns = []
    seen = {}
    for col in df.columns:
        name = str(col).strip()
        if not name or name.lower().startswith("unnamed:"):
            name = "unnamed"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        new_columns.append(name)
    df.columns = new_columns
    return df


def detect_encoding(path):
    sample = Path(path).read_bytes()[: 64 * 1024]
    for encoding in CSV_ENCODINGS:
        try:
            sample.decode(encoding)
            return encoding
        except (UnicodeDecodeError, Exception):
            continue
    return "utf-8"


def read_csv(path, nrows=None):
    encoding = detect_encoding(path)
    try:
        df = pd.read_csv(path, encoding=encoding, nrows=nrows)
    except Exception:
        raise TableReadError("Не удалось прочитать CSV-файл. Возможно, он повреждён.")
    return df


def read_excel(path, nrows=None):
    try:
        df = pd.read_excel(path, engine="openpyxl", nrows=nrows)
    except Exception:
        raise TableReadError("Не удалось прочитать файл. Возможно, он повреждён или не является Excel.")
    return df


def read_table(path, file_type, nrows=None):
    """Читает таблицу в DataFrame с нормализованными заголовками."""
    if file_type == "csv":
        df = read_csv(path, nrows=nrows)
    elif file_type == "xlsx":
        df = read_excel(path, nrows=nrows)
    else:
        raise TableReadError("Неизвестный тип файла.")

    if df is None or df.empty:
        raise TableReadError("Файл пустой: в нём нет данных.")

    df = normalize_headers(df)
    df.columns = [str(c) for c in df.columns]
    return df


def count_csv_rows(path):
    try:
        encoding = detect_encoding(path)
        with open(path, "r", encoding=encoding, newline="") as handle:
            return max(sum(1 for _ in csv.reader(handle)) - 1, 0)
    except Exception:
        return None


def count_xlsx_rows(path):
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            return max((ws.max_row or 1) - 1, 0)
        finally:
            wb.close()
    except Exception:
        return None


def table_info(path, file_type):
    """Возвращает (rows_count, columns, columns_count) без полного чтения."""
    if file_type == "csv":
        rows = count_csv_rows(path)
        try:
            sample = read_csv(path, nrows=0)
        except TableReadError:
            raise
        columns = [str(c).strip() for c in sample.columns]
    else:
        rows = count_xlsx_rows(path)
        sample = read_excel(path, nrows=0)
        columns = [str(c).strip() for c in sample.columns]
    if not columns or all(c in ("", "unnamed") for c in columns):
        raise TableReadError("Не удалось прочитать таблицу: отсутствуют заголовки столбцов.")
    return rows, columns, len(columns)


def export_dataframe(df, file_type):
    """Экспортирует DataFrame в байты (xlsx или csv). Возвращает (bytes, mime)."""
    try:
        if file_type == "xlsx":
            from io import BytesIO

            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Data")
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            return buffer.getvalue(), mime
        if file_type == "csv":
            from io import StringIO

            buffer = StringIO()
            df.to_csv(buffer, index=False, encoding="utf-8")
            # BOM для корректного открытия в Excel
            data = buffer.getvalue().encode("utf-8-sig")
            return data, "text/csv; charset=utf-8"
    except Exception:
        raise ExportError("Произошла ошибка при формировании файла результата.")
    raise ExportError("Неизвестный формат экспорта.")


def suggest_result_name(source_name, file_type):
    stem = Path(source_name).stem
    suffix = ".xlsx" if file_type == "xlsx" else ".csv"
    return f"{stem}_cleaned{suffix}"


def cleanup_stale_processing(user_id, session_token):
    """Бест-эфорт очистка временных файлов старой сессии обработки."""
    root = Path("media") / "processing" / str(user_id) / session_token
    try:
        import shutil

        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
    except Exception:
        pass


def processing_root(user_id, session_token):
    return Path("media") / "processing" / str(user_id) / session_token