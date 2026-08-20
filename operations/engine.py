"""Исполнение операций над DataFrame.

Каждая функция принимает (df, config) и возвращает (df, meta),
где meta — dict со сведениями для истории и сообщений пользователю.
"""

import numpy as np
import pandas as pd

from .services import (
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