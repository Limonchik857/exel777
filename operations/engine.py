"""Исполнение операций над DataFrame.

Каждая функция принимает (df, config) и возвращает (df, meta),
где meta — dict со сведениями для истории и сообщений пользователю.
"""

import re

import numpy as np
import pandas as pd

from .services import (
    CONVERT_TARGETS,
    DATE_FORMATS,
    EXTRACT_MODES,
    FILTER_OPERATORS,
    NUMERIC_OPERATORS,
    STRING_OPERATORS,
    normalize_phone_value,
    validate_operation_config,
)
from .validators import OperationError


def _ensure_columns(df, columns):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        names = ", ".join(f"«{c}»" for c in missing[:5])
        more = f" и ещё {len(missing) - 5}" if len(missing) > 5 else ""
        raise OperationError(f"В файле отсутствуют столбцы: {names}{more}.")


def _is_whitespace_or_empty(value):
    if value is None or pd.isna(value):
        return True
    try:
        return str(value).strip() == ""
    except Exception:
        return False


def column_kind(series) -> str:
    """Определяет тип столбца: numeric / text."""
    sample = series.dropna()
    if len(sample) == 0:
        return "text"
    numeric = pd.to_numeric(sample, errors="coerce")
    share = numeric.notna().mean()
    return "numeric" if share >= 0.6 else "text"


def remove_duplicates(df, config=None):
    config = validate_operation_config("remove_duplicates", config or {})
    subset = config.get("columns") or None
    if subset:
        _ensure_columns(df, subset)
    before = len(df)
    result = df.drop_duplicates(subset=subset, keep="first")
    removed = before - len(result)
    return result, {"removed": removed, "remaining": len(result)}


def drop_columns(df, config):
    config = validate_operation_config("drop_columns", config)
    columns = config["columns"]
    _ensure_columns(df, columns)
    remaining = [c for c in df.columns if c not in set(columns)]
    if not remaining:
        raise OperationError("Нельзя удалить все столбцы таблицы.")
    return df[remaining], {"columns": columns, "remaining": len(remaining)}


def _coerce_numeric(series, value):
    numeric = pd.to_numeric(series, errors="coerce")
    try:
        target = float(value)
    except (TypeError, ValueError):
        raise OperationError("Для выбранного условия укажите число.")
    return numeric, target


def filter_rows(df, config):
    config = validate_operation_config("filter", config)
    column = config["column"]
    operator = config["operator"]
    value = config["value"]
    _ensure_columns(df, [column])

    series = df[column]
    kind = column_kind(series)

    if operator in STRING_OPERATORS:
        text = series.astype(str)
        needle = str(value)
        if operator == "contains":
            mask = text.str.contains(needle, na=False, regex=False)
        else:
            mask = ~text.str.contains(needle, na=False, regex=False)
        result = df[mask]
    elif operator in NUMERIC_OPERATORS and kind == "numeric":
        numeric, target = _coerce_numeric(series, value)
        if operator == "eq":
            mask = numeric == target
        elif operator == "ne":
            mask = numeric != target
        elif operator == "gt":
            mask = numeric > target
        elif operator == "lt":
            mask = numeric < target
        elif operator == "gte":
            mask = numeric >= target
        else:
            mask = numeric <= target
        result = df[mask.fillna(False)]
    else:
        # Текстовое сравнение (для ne NaN считается «не равным», поэтому не отбрасываем)
        text = series.astype(str).str.strip().str.lower()
        target = str(value).strip().lower()
        if operator == "eq":
            mask = text == target
            result = df[mask]
        elif operator == "ne":
            mask = text != target
            result = df[mask]
        elif operator == "gt":
            mask = text > target
            result = df[mask.fillna(False)]
        elif operator == "lt":
            mask = text < target
            result = df[mask.fillna(False)]
        elif operator == "gte":
            mask = text >= target
            result = df[mask.fillna(False)]
        else:
            mask = text <= target
            result = df[mask.fillna(False)]

    return result, {"removed": len(df) - len(result), "remaining": len(result)}


def sort_rows(df, config):
    config = validate_operation_config("sort", config)
    column = config["column"]
    ascending = bool(config.get("ascending", True))
    _ensure_columns(df, [column])

    series = df[column]
    kind = column_kind(series)
    if kind == "numeric":
        numeric = pd.to_numeric(series, errors="coerce")
        result = df.assign(_sort_key=numeric, _orig=range(len(df))).sort_values(
            ["_sort_key", "_orig"],
            ascending=[ascending, True],
            na_position="last",
        )
        result = result.drop(columns=["_sort_key", "_orig"])
    else:
        result = df.sort_values(column, ascending=ascending, na_position="last", kind="stable")
    return result, {"ascending": ascending}


def find_replace(df, config):
    config = validate_operation_config("find_replace", config)
    find = config["find"]
    replace = config.get("replace", "")
    all_columns = config.get("all_columns", True)
    column = config.get("column", "")

    targets = list(df.columns) if all_columns else [column]
    if not all_columns:
        _ensure_columns(df, [column])

    total_replacements = 0
    for col in targets:
        series = df[col]
        was_null = series.isna()
        text = series.astype(str).str.replace(find, replace, regex=False)
        text = text.mask(was_null, None)
        if str(find) != str(replace):
            # считаем фактические замены в непустых значениях
            diff = (~was_null) & (series.astype(str) != text)
            total_replacements += int(diff.sum())
        df = df.copy()
        df[col] = text

    return df, {"replacements": total_replacements}


def remove_empty_rows(df, config=None):
    validate_operation_config("remove_empty_rows", config or {})
    before = len(df)
    empty_mask = df.map(lambda v: _is_whitespace_or_empty(v))
    result = df[~empty_mask.all(axis=1)]
    removed = before - len(result)
    return result, {"removed": removed, "remaining": len(result)}


def normalize_phone(df, config):
    config = validate_operation_config("normalize_phone", config)
    column = config["column"]
    _ensure_columns(df, [column])
    df = df.copy()
    df[column] = df[column].map(lambda v: normalize_phone_value(v) if not _is_whitespace_or_empty(v) else v)
    return df, {"column": column}


def _to_text(value):
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, np.integer):
        return str(int(value))
    if isinstance(value, np.floating):
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    return str(value)


def _parse_dates(series):
    """Парсит даты с поддержкой DD.MM.YYYY и YYYY-MM-DD одновременно."""
    text = series.astype(str)
    iso_mask = text.str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if iso_mask.any():
        parsed.loc[iso_mask] = pd.to_datetime(text[iso_mask], errors="coerce")
    rest_mask = (~iso_mask) & series.notna()
    if rest_mask.any():
        parsed.loc[rest_mask] = pd.to_datetime(
            text[rest_mask], errors="coerce", dayfirst=True
        )
    return parsed


def normalize_text(df, config):
    """Нормализует текст в столбце: trim, схлопывание пробелов, регистр."""
    config = validate_operation_config("normalize_text", config)
    column = config["column"]
    modes = config["modes"]
    _ensure_columns(df, [column])
    df = df.copy()

    def apply_modes(value):
        if _is_whitespace_or_empty(value):
            return value
        text = str(value)
        if "trim" in modes:
            text = text.strip()
        if "collapse_spaces" in modes:
            text = re.sub(r"\s+", " ", text).strip()
        if "lower" in modes:
            text = text.lower()
        elif "upper" in modes:
            text = text.upper()
        elif "title" in modes:
            text = text.title()
        return text

    df[column] = df[column].map(apply_modes)
    return df, {"column": column, "modes": modes}


def normalize_dates(df, config):
    """Приводит даты в столбце к выбранному формату."""
    config = validate_operation_config("normalize_dates", config)
    column = config["column"]
    fmt = config["format"]
    _ensure_columns(df, [column])
    df = df.copy()
    series = df[column]
    parsed = _parse_dates(series)
    converted = int(parsed.notna().sum())
    df[column] = parsed.map(
        lambda v: v.strftime(DATE_FORMATS[fmt]) if pd.notna(v) else v
    )
    return df, {"column": column, "format": fmt, "converted": converted}


def convert_type(df, config):
    """Преобразует тип столбца: number / text / date."""
    config = validate_operation_config("convert_type", config)
    column = config["column"]
    target = config["target"]
    _ensure_columns(df, [column])
    df = df.copy()
    series = df[column]
    converted = int(series.notna().sum())
    if target == "number":
        df[column] = pd.to_numeric(series, errors="coerce")
    elif target == "text":
        df[column] = series.map(_to_text)
    elif target == "date":
        df[column] = _parse_dates(series)
    return df, {"column": column, "target": target, "converted": converted}


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s]+")
NUMBER_RE = re.compile(r"[-+]?\d[\d\s]*[.,]?\d*")
PHONE_RE = re.compile(r"(?:\+?7|8)?[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}")


def _extract_value(value, mode, separator):
    if value is None or pd.isna(value):
        return value
    text = str(value)
    if mode == "email":
        match = EMAIL_RE.search(text)
        return match.group(0) if match else ""
    if mode == "phone":
        match = PHONE_RE.search(text)
        if match:
            return re.sub(r"\D", "", match.group(0))
        return ""
    if mode == "number":
        match = NUMBER_RE.search(text)
        return match.group(0).replace(" ", "") if match else ""
    if mode == "url":
        match = URL_RE.search(text)
        return match.group(0) if match else ""
    if mode == "before":
        return text.split(separator)[0] if separator else ""
    if mode == "after":
        if not separator:
            return ""
        parts = text.split(separator)
        return separator.join(parts[1:]) if len(parts) > 1 else ""
    return text


def extract(df, config):
    """Извлекает из текста email/телефон/число/URL или текст до/после разделителя."""
    config = validate_operation_config("extract", config)
    column = config["column"]
    mode = config["mode"]
    separator = config.get("separator", "")
    _ensure_columns(df, [column])
    df = df.copy()
    df[column] = df[column].map(lambda v: _extract_value(v, mode, separator))
    return df, {"column": column, "mode": mode}


def split_table(df, config):
    """Разделяет таблицу на части по значению столбца.

    Возвращает (dict{value: df}, meta) — в отличие от обычных операций.
    """
    config = validate_operation_config("split", config)
    column = config["column"]
    _ensure_columns(df, [column])
    parts = {}
    for value, group in df.groupby(df[column], dropna=False):
        key = "пустое" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)
        parts[key] = group.copy()
    counts = {k: len(v) for k, v in parts.items()}
    return parts, {"column": column, "parts": counts, "total": len(df)}


def append_tables(df, other_df, config=None):
    """Добавляет строки другого файла в текущую таблицу.

    Не является линейной операцией: требует второй источник данных.
    Возвращает (merged_df, meta).
    """
    if config is None:
        config = {}
    columns = list(df.columns)
    missing = [c for c in other_df.columns if c not in df.columns]
    if missing:
        raise OperationError(
            f"Файл для добавления содержит столбцы, которых нет в таблице: "
            f"{', '.join(missing[:5])}."
        )
    other = other_df[columns]
    merged = pd.concat([df, other], ignore_index=True, sort=False)
    return merged, {"added": len(other), "total": len(merged)}


def apply_operation(df, op_type, config):
    """Точка входа: применяет операцию к DataFrame, возвращает (df, meta)."""
    if op_type == "remove_duplicates":
        return remove_duplicates(df, config)
    if op_type == "drop_columns":
        return drop_columns(df, config)
    if op_type == "filter":
        return filter_rows(df, config)
    if op_type == "sort":
        return sort_rows(df, config)
    if op_type == "find_replace":
        return find_replace(df, config)
    if op_type == "remove_empty_rows":
        return remove_empty_rows(df, config)
    if op_type == "normalize_phone":
        return normalize_phone(df, config)
    if op_type == "normalize_text":
        return normalize_text(df, config)
    if op_type == "normalize_dates":
        return normalize_dates(df, config)
    if op_type == "convert_type":
        return convert_type(df, config)
    if op_type == "extract":
        return extract(df, config)
    if op_type == "split":
        return split_table(df, config)
    if op_type == "append":
        raise OperationError(
            "Операция «Добавить данные» требует второй файл и выполняется отдельно."
        )
    raise OperationError("Неизвестная операция.")


def validate_columns_exist(df, columns):
    _ensure_columns(df, columns)


def prepare_df_for_display(df, max_cells_chars=120):
    """Готовит DataFrame для показа в HTML: заменяет NaN на пустые строки
    и укорачивает длинные значения."""
    def fmt(value):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return ""
        if isinstance(value, (np.generic,)):
            value = value.item()
        text = str(value)
        if len(text) > max_cells_chars:
            text = text[: max_cells_chars - 1] + "…"
        return text

    return df.map(fmt)