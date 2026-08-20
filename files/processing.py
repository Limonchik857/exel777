"""Управление состоянием текущей обработки в сессии.

Каждая версия таблицы сохраняется в pickle-файл на диск — это позволяет
делать отмену/повтор и не хранить DataFrame в сессии (память браузера).

Модель данных:

    versions[0]           — исходная таблица
    versions[i]           — результат после i операций
    history_snapshots[i]  — полный список операций, применённых к versions[i]
    current               — индекс активной версии

Такая модель гарантирует синхронность versions / history / current:
даже после Undo → новая операция старая ветка полностью отбрасывается,
а при trimming старых версий снимки истории остаются консистентными.
"""

import secrets
import shutil
from pathlib import Path

import pandas as pd

from django.conf import settings

from operations.services import describe_operation


def _root(request):
    return Path(settings.MEDIA_ROOT) / "processing" / str(request.user.id)


def _session_dir(request):
    token = request.session["processing"]["token"]
    return _root(request) / token


def _version_path(request, index):
    return _session_dir(request) / f"v{index}.pkl"


def _save_df(request, df, index):
    path = _version_path(request, index)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(path)
    return str(path)


def start_session(request, uploaded_file_id, source_name, df, columns, rows):
    """Создаёт новую сессию обработки с исходной таблицей."""
    token = secrets.token_hex(16)
    # Бест-эфорт чистка старых сессий этого пользователя
    old_root = _root(request)
    try:
        shutil.rmtree(old_root, ignore_errors=True)
    except Exception:
        pass
    session_dir = old_root / token
    session_dir.mkdir(parents=True, exist_ok=True)

    # Сессия создаётся до сохранения файла: _save_df зависит от token.
    request.session["processing"] = {
        "uploaded_file_id": uploaded_file_id,
        "token": token,
        "source_name": source_name,
        "versions": [],
        "current": 0,
        "history": [],
        "history_snapshots": [],
        "columns": columns,
        "rows": rows,
        "rows_original": rows,
    }
    first_path = _save_df(request, df, 0)
    request.session["processing"]["versions"] = [first_path]
    request.session["processing"]["history_snapshots"] = [[]]
    request.session.modified = True


def get_state(request):
    return request.session.get("processing")


def has_session(request):
    return bool(request.session.get("processing"))


def current_df(request):
    state = get_state(request)
    if not state:
        return None
    path = state["versions"][state["current"]]
    return pd.read_pickle(path)


def applied_history(state):
    """Операции, фактически применённые к текущей версии (не меняет состояние)."""
    snapshots = state.get("history_snapshots")
    if snapshots:
        return list(snapshots[state["current"]])
    # Совместимость со старыми сессиями без снимков.
    return list(state.get("history", [])[: state["current"]])


def apply_operation(request, df, op_type, config, meta):
    """Сохраняет результат операции как новую версию и пишет в историю.

    Отбрасывает «хвост» после current (Undo → новая операция), сохраняя
    versions / history / current синхронизированными.
    """
    state = get_state(request)
    new_index = state["current"] + 1
    path = _save_df(request, df, new_index)

    prev_history = applied_history(state)
    new_snapshot = prev_history + [
        {
            "op": op_type,
            "config": config,
            "label": describe_operation(op_type, config),
            "meta": meta,
        }
    ]
    max_steps = settings.MAX_UNDO_STEPS
    if len(new_snapshot) > max_steps:
        new_snapshot = new_snapshot[-max_steps:]

    # Отбрасываем «повторы» вперёд при новой операции
    state["versions"] = state["versions"][:new_index] + [path]
    state["history_snapshots"] = state["history_snapshots"][:new_index] + [new_snapshot]
    state["current"] = new_index
    state["rows"] = len(df)
    state["history"] = list(new_snapshot)

    # Ограничиваем число хранимых версий.
    if len(state["versions"]) > max_steps:
        keep_from = len(state["versions"]) - max_steps
        excess = state["versions"][:keep_from]
        for p in excess:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        state["versions"] = state["versions"][keep_from:]
        state["history_snapshots"] = state["history_snapshots"][keep_from:]
        state["current"] = len(state["versions"]) - 1
        state["history"] = list(state["history_snapshots"][state["current"]])

    request.session.modified = True


def undo(request):
    state = get_state(request)
    if not state or state["current"] <= 0:
        return False
    state["current"] -= 1
    df = pd.read_pickle(state["versions"][state["current"]])
    state["rows"] = len(df)
    request.session.modified = True
    return True


def redo(request):
    state = get_state(request)
    if not state or state["current"] >= len(state["versions"]) - 1:
        return False
    state["current"] += 1
    df = pd.read_pickle(state["versions"][state["current"]])
    state["rows"] = len(df)
    request.session.modified = True
    return True


def clear_session(request):
    state = get_state(request)
    if state:
        try:
            shutil.rmtree(_session_dir(request), ignore_errors=True)
        except Exception:
            pass
    request.session.pop("processing", None)
    request.session.modified = True