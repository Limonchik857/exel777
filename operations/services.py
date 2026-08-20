"""Типы операций над таблицами и их метаданные.

Единый справочник операций используется и в интерактивной обработке,
и в сохранённых workflow. Конфигурация каждой операции — JSON-совместимый
dict (строки, списки строк, числа, bool).
"""

import re

from .validators import OperationError

# Ключи операций
REMOVE_DUPLICATES = "remove_duplicates"
DROP_COLUMNS = "drop_columns"
FILTER = "filter"
SORT = "sort"
FIND_REPLACE = "find_replace"
REMOVE_EMPTY_ROWS = "remove_empty_rows"
NORMALIZE_PHONE = "normalize_phone"
NORMALIZE_TEXT = "normalize_text"
NORMALIZE_DATES = "normalize_dates"
CONVERT_TYPE = "convert_type"
EXTRACT = "extract"
SPLIT = "split"
APPEND = "append"

OPERATION_TYPES = [
    (REMOVE_DUPLICATES, "Удалить дубликаты"),
    (DROP_COLUMNS, "Удалить столбцы"),
    (FILTER, "Фильтровать"),
    (SORT, "Сортировать"),
    (FIND_REPLACE, "Найти и заменить"),
    (REMOVE_EMPTY_ROWS, "Удалить пустые строки"),
    (NORMALIZE_PHONE, "Нормализовать телефон"),
    (NORMALIZE_TEXT, "Нормализовать текст"),
    (NORMALIZE_DATES, "Нормализовать даты"),
    (CONVERT_TYPE, "Изменить тип столбца"),
    (EXTRACT, "Извлечь из текста"),
    (SPLIT, "Разделить таблицу"),
    (APPEND, "Добавить данные"),
]

OPERATION_CHOICES = [(key, label) for key, label in OPERATION_TYPES]

OPERATION_LABELS = dict(OPERATION_TYPES)

# Иконки операций для интерфейса
OPERATION_ICONS = {
    REMOVE_DUPLICATES: "▤",
    DROP_COLUMNS: "⊞",
    FILTER: "◫",
    SORT: "⇅",
    FIND_REPLACE: "⌕",
    REMOVE_EMPTY_ROWS: "⌫",
    NORMALIZE_PHONE: "☎",
    NORMALIZE_TEXT: "Aa",
    NORMALIZE_DATES: "◷",
    CONVERT_TYPE: "⇄",
    EXTRACT: "⌗",
    SPLIT: "⫸",
    APPEND: "⨭",
}

OPERATION_DESCRIPTIONS = {
    REMOVE_DUPLICATES: "Удаляет повторяющиеся строки по выбранным столбцам.",
    DROP_COLUMNS: "Удаляет ненужные столбцы из таблицы.",
    FILTER: "Оставляет строки, которые соответствуют условию.",
    SORT: "Сортирует таблицу по выбранному столбцу.",
    FIND_REPLACE: "Заменяет одни значения на другие.",
    REMOVE_EMPTY_ROWS: "Удаляет строки, полностью лишённые данных.",
    NORMALIZE_PHONE: "Приводит телефоны в столбце к единому виду +7…",
    NORMALIZE_TEXT: "Выравнивает текст: trim, пробелы, регистр.",
    NORMALIZE_DATES: "Приводит даты к выбранному формату.",
    CONVERT_TYPE: "Преобразует тип столбца: текст, число, дата.",
    EXTRACT: "Извлекает из текста email, телефон, числа, ссылки.",
    SPLIT: "Разделяет таблицу на несколько файлов по значению столбца.",
    APPEND: "Добавляет строки из другого файла в текущую таблицу.",
}

# Операторы фильтрации
FILTER_OPERATORS = {
    "eq": "равно",
    "ne": "не равно",
    "contains": "содержит",
    "not_contains": "не содержит",
    "gt": "больше",
    "lt": "меньше",
    "gte": "больше или равно",
    "lte": "меньше или равно",
}

NUMERIC_OPERATORS = {"eq", "ne", "gt", "lt", "gte", "lte"}
STRING_OPERATORS = {"contains", "not_contains"}

# Форматы дат
DATE_FORMATS = {
    "DD.MM.YYYY": "%d.%m.%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD.MM.YYYY HH:MM": "%d.%m.%Y %H:%M",
    "YYYY-MM-DD HH:MM": "%Y-%m-%d %H:%M",
}

# Типы для конвертации
CONVERT_TARGETS = {"number": "Число", "text": "Текст", "date": "Дата"}

# Режимы извлечения
EXTRACT_MODES = {
    "email": "Email",
    "phone": "Телефон",
    "number": "Число",
    "url": "URL",
    "before": "Текст до разделителя",
    "after": "Текст после разделителя",
}

# Операции, которые можно сохранять в workflow/pipeline
WORKFLOW_SAFE_OPERATIONS = {
    REMOVE_DUPLICATES,
    DROP_COLUMNS,
    FILTER,
    SORT,
    FIND_REPLACE,
    REMOVE_EMPTY_ROWS,
    NORMALIZE_PHONE,
    NORMALIZE_TEXT,
    NORMALIZE_DATES,
    CONVERT_TYPE,
    EXTRACT,
}

# Порядок операций в визарде обработки (для кнопок «быстрых операций»)
QUICK_OPERATIONS = [REMOVE_DUPLICATES, DROP_COLUMNS, FILTER, SORT,
                    FIND_REPLACE, REMOVE_EMPTY_ROWS, NORMALIZE_PHONE,
                    NORMALIZE_TEXT, NORMALIZE_DATES, CONVERT_TYPE, EXTRACT,
                    SPLIT, APPEND]

PHONE_RE = re.compile(r"\+?\s*7\s*[-()\s]*\d{3}\s*[-()\s]*\d{3}\s*[-()\s]*\d{2}\s*[-()\s]*\d{2}")
DIGITS_RE = re.compile(r"\D")


def normalize_phone_value(value):
    """Приводит телефон к виду +7XXXXXXXXXX. Неразбираемое — оставляет как есть."""
    if value is None:
        return value
    text = str(value).strip()
    if not text:
        return value
    digits = DIGITS_RE.sub("", text)
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if digits.startswith("7") and len(digits) == 10:
        return "+7" + digits
    return value


def describe_operation(op_type, config):
    """Возвращает короткое человекочитаемое описание операции для истории."""
    label = OPERATION_LABELS.get(op_type, op_type)
    try:
        if op_type == REMOVE_DUPLICATES:
            columns = config.get("columns")
            if columns:
                return f"{label} по {', '.join(columns)}"
            return "Удалить дубликаты по всем столбцам"
        if op_type == DROP_COLUMNS:
            columns = config.get("columns", [])
            shown = ", ".join(columns[:3])
            more = f" и ещё {len(columns) - 3}" if len(columns) > 3 else ""
            return f"Удалён столбец: {shown}{more}" if len(columns) == 1 else f"Удалены столбцы: {shown}{more}"
        if op_type == FILTER:
            column = config.get("column", "?")
            operator = FILTER_OPERATORS.get(config.get("operator", ""), config.get("operator", "?"))
            value = config.get("value", "")
            return f"Фильтр: {column} {operator} {value}"
        if op_type == SORT:
            column = config.get("column", "?")
            order = "возрастание" if config.get("ascending", True) else "убывание"
            return f"Сортировка по {column} ({order})"
        if op_type == FIND_REPLACE:
            scope = "вся таблица" if config.get("all_columns", True) else f"столбец {config.get('column', '?')}"
            return f"Заменить «{config.get('find', '')}» → «{config.get('replace', '')}» ({scope})"
        if op_type == REMOVE_EMPTY_ROWS:
            return "Удалить пустые строки"
        if op_type == NORMALIZE_PHONE:
            return f"Нормализовать телефон: {config.get('column', '?')}"
        if op_type == NORMALIZE_TEXT:
            modes = config.get("modes", [])
            names = {"trim": "trim", "collapse_spaces": "пробелы", "lower": "lower", "upper": "upper", "title": "title"}
            shown = ", ".join(names.get(m, m) for m in modes)
            return f"Нормализовать текст: {config.get('column', '?')} ({shown})"
        if op_type == NORMALIZE_DATES:
            return f"Даты → {config.get('format', '?')}: {config.get('column', '?')}"
        if op_type == CONVERT_TYPE:
            target = CONVERT_TARGETS.get(config.get("target", ""), config.get("target", "?"))
            return f"Тип «{config.get('column', '?')}» → {target}"
        if op_type == EXTRACT:
            mode = EXTRACT_MODES.get(config.get("mode", ""), config.get("mode", "?"))
            suffix = f" после «{config.get('separator', '')}»" if config.get("mode") in ("before", "after") else ""
            return f"Извлечь {mode}: {config.get('column', '?')}{suffix}"
        if op_type == SPLIT:
            return f"Разделить по столбцу: {config.get('column', '?')}"
        if op_type == APPEND:
            return "Добавить данные из файла"
    except Exception:
        pass
    return label


def validate_operation_config(op_type, config):
    """Проверяет структуру конфигурации операции.

    Не проверяет наличие столбцов в конкретной таблице — это делается
    при исполнении операции с реальным DataFrame.
    """
    if op_type not in OPERATION_LABELS:
        raise OperationError("Неизвестный тип операции.")

    if op_type == REMOVE_DUPLICATES:
        columns = config.get("columns")
        if columns is not None and not isinstance(columns, list):
            raise OperationError("Выберите столбцы для поиска дубликатов.")
        if columns and not all(isinstance(c, str) for c in columns):
            raise OperationError("Неверно указаны столбцы.")
        config.setdefault("columns", [])

    elif op_type == DROP_COLUMNS:
        columns = config.get("columns")
        if not isinstance(columns, list) or not columns:
            raise OperationError("Выберите столбцы для удаления.")
        if not all(isinstance(c, str) for c in columns):
            raise OperationError("Неверно указаны столбцы.")

    elif op_type == FILTER:
        column = config.get("column")
        operator = config.get("operator")
        value = config.get("value")
        if not column:
            raise OperationError("Выберите столбец для фильтра.")
        if operator not in FILTER_OPERATORS:
            raise OperationError("Выберите условие фильтра.")
        if value is None or value == "":
            raise OperationError("Укажите значение для фильтра.")

    elif op_type == SORT:
        column = config.get("column")
        if not column:
            raise OperationError("Выберите столбец для сортировки.")

    elif op_type == FIND_REPLACE:
        find = config.get("find")
        if find is None or find == "":
            raise OperationError("Укажите, что нужно найти.")
        config.setdefault("replace", "")
        config.setdefault("all_columns", True)
        config.setdefault("column", "")

    elif op_type == REMOVE_EMPTY_ROWS:
        pass

    elif op_type == NORMALIZE_PHONE:
        column = config.get("column")
        if not column:
            raise OperationError("Выберите столбец с телефонами.")

    elif op_type == NORMALIZE_TEXT:
        column = config.get("column")
        modes = config.get("modes")
        if not column:
            raise OperationError("Выберите столбец для нормализации текста.")
        if not isinstance(modes, list) or not modes:
            raise OperationError("Выберите хотя бы один режим нормализации.")
        allowed = {"trim", "collapse_spaces", "lower", "upper", "title"}
        if not set(modes) <= allowed:
            raise OperationError("Неизвестный режим нормализации.")

    elif op_type == NORMALIZE_DATES:
        column = config.get("column")
        fmt = config.get("format")
        if not column:
            raise OperationError("Выберите столбец с датами.")
        if fmt not in DATE_FORMATS:
            raise OperationError("Выберите формат даты.")

    elif op_type == CONVERT_TYPE:
        column = config.get("column")
        target = config.get("target")
        if not column:
            raise OperationError("Выберите столбец.")
        if target not in CONVERT_TARGETS:
            raise OperationError("Выберите целевой тип.")

    elif op_type == EXTRACT:
        column = config.get("column")
        mode = config.get("mode")
        if not column:
            raise OperationError("Выберите столбец.")
        if mode not in EXTRACT_MODES:
            raise OperationError("Выберите режим извлечения.")
        if mode in ("before", "after"):
            config.setdefault("separator", "")

    elif op_type == SPLIT:
        column = config.get("column")
        if not column:
            raise OperationError("Выберите столбец для разделения.")

    elif op_type == APPEND:
        config.setdefault("columns", [])

    return config