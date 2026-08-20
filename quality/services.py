"""Анализ качества данных: метрики, проблемы и Data Quality Score."""

import math
import re
import warnings

import pandas as pd

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(
    r"^(?:\+7|8)?[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}$"
)


def _is_empty(value):
    return value is None or pd.isna(value) or str(value).strip() == ""


def _to_text(value):
    if _is_empty(value):
        return ""
    return str(value).strip()


def _candidate_email_columns(df):
    cols = []
    for col in df.columns:
        series = df[col]
        non_empty = series.map(lambda v: not _is_empty(v))
        if non_empty.sum() == 0:
            continue
        at_share = series[non_empty].map(lambda v: "@" in str(v)).mean()
        if at_share >= 0.2:
            cols.append(col)
    return cols


def _candidate_phone_columns(df):
    cols = []
    for col in df.columns:
        series = df[col]
        non_empty = series.map(lambda v: not _is_empty(v))
        if non_empty.sum() == 0:
            continue
        digit_share = series[non_empty].map(
            lambda v: sum(c.isdigit() for c in str(v)) >= 10
        ).mean()
        if digit_share >= 0.2:
            cols.append(col)
    return cols


def _candidate_date_columns(df):
    cols = []
    for col in df.columns:
        series = df[col]
        non_empty = series.map(lambda v: not _is_empty(v))
        if non_empty.sum() < 3:
            continue
        parsed = _coerce_dates(series[non_empty].astype(str))
        if parsed.notna().mean() >= 0.7:
            cols.append(col)
    return cols


def _coerce_dates(values):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return pd.to_datetime(values, errors="coerce", dayfirst=True)


def _numeric_outliers(series):
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.dropna()
    if len(values) < 5:
        return 0
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0 or math.isnan(iqr):
        return 0
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((numeric < low) | (numeric > high)).sum())


def analyze_quality(df):
    """Возвращает полный отчёт о качестве данных.

    Структура:
      rows, columns, empty_values, duplicates, fill_rate, unique_rate,
      column_types, issues (карточки проблем), score, status,
      breakdown (метрики для сводки).
    """
    rows = len(df)
    cols = len(df.columns)
    total_cells = rows * cols

    empty_series = df.map(lambda v: _is_empty(v))
    empty_values = int(empty_series.sum().sum())
    fill_rate = round((1 - empty_values / total_cells) * 100, 1) if total_cells else 100.0

    dup_mask = df.duplicated(keep="first")
    duplicates = int(dup_mask.sum())
    duplicate_pct = round(duplicates / rows * 100, 1) if rows else 0.0

    unique_rates = {}
    for col in df.columns:
        non_empty = df[col].map(lambda v: not _is_empty(v))
        if non_empty.sum() == 0:
            unique_rates[col] = 0.0
        else:
            unique_rates[col] = round(
                df.loc[non_empty, col].nunique() / int(non_empty.sum()) * 100, 1
            )
    avg_unique = round(
        sum(unique_rates.values()) / len(unique_rates), 1
    ) if unique_rates else 100.0

    column_types = {}
    for col in df.columns:
        series = df[col]
        numeric = pd.to_numeric(series.dropna(), errors="coerce")
        share = numeric.notna().mean() if len(numeric) else 0
        if share >= 0.6:
            column_types[col] = "numeric"
        elif col in _candidate_date_columns(df):
            column_types[col] = "date"
        else:
            column_types[col] = "text"

    issues = []
    breakdown = {
        "email_valid_pct": 100.0,
        "phone_valid_pct": 100.0,
        "duplicate_pct": duplicate_pct,
        "empty_pct": round(empty_values / total_cells * 100, 1) if total_cells else 0.0,
        "invalid_dates_pct": 0.0,
    }

    # Дубликаты
    if duplicates:
        issues.append(
            {
                "severity": "warning",
                "category": "duplicates",
                "title": f"{duplicates} дублирующихся строк",
                "message": "Строки с полностью совпадающими значениями.",
                "count": duplicates,
                "rows": [int(i) for i in df.index[dup_mask].tolist()],
                "action": "remove_duplicates",
                "action_label": "Удалить дубликаты",
            }
        )

    # Email
    email_issues = []
    for col in _candidate_email_columns(df):
        invalid = []
        for idx, value in df[col].items():
            text = _to_text(value)
            if text and not EMAIL_RE.match(text):
                invalid.append(int(idx))
        if invalid:
            email_issues.append({"column": col, "count": len(invalid), "rows": invalid})
    if email_issues:
        total_invalid_email = sum(iss["count"] for iss in email_issues)
        total_email = 0
        for col in _candidate_email_columns(df):
            total_email += int(df[col].map(lambda v: not _is_empty(v)).sum())
        valid_pct = round(
            (1 - total_invalid_email / total_email) * 100, 1
        ) if total_email else 100.0
        breakdown["email_valid_pct"] = valid_pct
        columns = ", ".join(f"{i['column']} ({i['count']})" for i in email_issues)
        issues.append(
            {
                "severity": "error",
                "category": "email",
                "title": f"{total_invalid_email} некорректных email",
                "message": f"Столбцы: {columns}.",
                "count": total_invalid_email,
                "rows": sorted({r for i in email_issues for r in i["rows"]}),
                "action": None,
                "action_label": None,
            }
        )

    # Телефоны
    phone_issues = []
    for col in _candidate_phone_columns(df):
        invalid = []
        for idx, value in df[col].items():
            text = _to_text(value)
            if text and not PHONE_RE.match(text):
                invalid.append(int(idx))
        if invalid:
            phone_issues.append({"column": col, "count": len(invalid), "rows": invalid})
    if phone_issues:
        total_invalid_phone = sum(iss["count"] for iss in phone_issues)
        total_phone = 0
        for col in _candidate_phone_columns(df):
            total_phone += int(df[col].map(lambda v: not _is_empty(v)).sum())
        valid_pct = round(
            (1 - total_invalid_phone / total_phone) * 100, 1
        ) if total_phone else 100.0
        breakdown["phone_valid_pct"] = valid_pct
        columns = ", ".join(f"{i['column']} ({i['count']})" for i in phone_issues)
        issues.append(
            {
                "severity": "warning",
                "category": "phone",
                "title": f"{total_invalid_phone} некорректных телефонов",
                "message": f"Столбцы: {columns}.",
                "count": total_invalid_phone,
                "rows": sorted({r for i in phone_issues for r in i["rows"]}),
                "action": None,
                "action_label": None,
            }
        )

    # Пустые значения по столбцам
    empty_cols = []
    for col in df.columns:
        count = int(empty_series[col].sum())
        if count:
            empty_cols.append({"column": col, "count": count})
    if empty_cols:
        top = sorted(empty_cols, key=lambda c: -c["count"])[:5]
        columns = ", ".join(f"{c['column']} ({c['count']})" for c in top)
        issues.append(
            {
                "severity": "warning",
                "category": "empty",
                "title": f"{empty_values} пустых значений",
                "message": f"Больше всего в: {columns}.",
                "count": empty_values,
                "rows": sorted(
                    {int(i) for i in df.index[empty_series.any(axis=1)].tolist()}
                ),
                "action": "remove_empty_rows",
                "action_label": "Удалить пустые строки",
            }
        )

    # Даты
    invalid_dates = 0
    for col in _candidate_date_columns(df):
        series = df[col]
        non_empty = series.map(lambda v: not _is_empty(v))
        parsed = _coerce_dates(series[non_empty].astype(str))
        bad = int((non_empty.sum() - parsed.notna().sum()))
        invalid_dates += bad
    if invalid_dates:
        breakdown["invalid_dates_pct"] = round(
            invalid_dates / rows * 100, 1
        ) if rows else 0.0
        issues.append(
            {
                "severity": "warning",
                "category": "dates",
                "title": f"{invalid_dates} некорректных дат",
                "message": "Значения не распознаются как даты.",
                "count": invalid_dates,
                "rows": [],
                "action": "normalize_dates",
                "action_label": "Нормализовать даты",
            }
        )

    # Аномалии чисел
    for col in df.columns:
        if column_types.get(col) != "numeric":
            continue
        outliers = _numeric_outliers(df[col])
        if outliers:
            series = df[col]
            numeric = pd.to_numeric(series, errors="coerce")
            rows_list = [int(i) for i in numeric.index if pd.notna(numeric[i]) and (
                numeric[i] < numeric.quantile(0.25) - 1.5 * (numeric.quantile(0.75) - numeric.quantile(0.25))
                or numeric[i] > numeric.quantile(0.75) + 1.5 * (numeric.quantile(0.75) - numeric.quantile(0.25))
            )]
            issues.append(
                {
                    "severity": "info",
                    "category": "anomalies",
                    "title": f"{outliers} аномальных значений в «{col}»",
                    "message": "Значения сильно выбиваются из диапазона (IQR).",
                    "count": outliers,
                    "rows": rows_list,
                    "action": None,
                    "action_label": None,
                }
            )

    score = _compute_score(df, breakdown, duplicates, empty_values, total_cells)
    status = "GOOD" if score >= 80 else ("WARNING" if score >= 60 else "CRITICAL")

    return {
        "rows": rows,
        "columns": cols,
        "empty_values": empty_values,
        "fill_rate": fill_rate,
        "duplicates": duplicates,
        "unique_rate": avg_unique,
        "column_types": column_types,
        "unique_rates": unique_rates,
        "issues": issues,
        "score": score,
        "status": status,
        "breakdown": breakdown,
    }


def _compute_score(df, breakdown, duplicates, empty_values, total_cells):
    score = 100.0
    rows = len(df)
    if rows:
        score -= min(duplicates / rows * 20, 20)
    if total_cells:
        score -= min(empty_values / total_cells * 20, 20)
    score -= min((100 - breakdown["email_valid_pct"]) * 0.65, 50)
    score -= min((100 - breakdown["phone_valid_pct"]) * 0.65, 35)
    score -= min(breakdown["invalid_dates_pct"] / 2, 10)
    return int(max(0, min(100, round(score))))