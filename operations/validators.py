"""Ошибки операций с понятными пользователю сообщениями."""


class OperationError(Exception):
    """Ошибка выполнения операции с человекочитаемым текстом.

    Сообщение показывается пользователю как есть (без traceback).
    """


class FileValidationError(Exception):
    """Ошибка проверки загружаемого файла."""


class TableReadError(Exception):
    """Файл повреждён, пуст или не читается как таблица."""


class MergeStructureError(Exception):
    """Файлы имеют разную структуру (разные столбцы)."""


class ExportError(Exception):
    """Не удалось сохранить/отдать результат."""