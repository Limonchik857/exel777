"""Rate limiting: учёт действий пользователя/IP в БД.

Ограничения хранятся в settings (RATE_LIMIT_*_PER_MINUTE). Лимит считается
за скользящее окно в 60 секунд. Для MVP достаточно простого подсчёта в БД —
без Redis и фоновых задач.
"""

from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from .models import RateLimitLog

WINDOW_SECONDS = 60


def get_client_ip(request):
    """Возвращает IP пользователя из стандартных заголовков."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def is_limited(request, action, limit):
    """Проверяет лимит и фиксирует попытку. Возвращает True, если лимит превышен."""
    user = request.user if request.user.is_authenticated else None
    ip = get_client_ip(request)
    cutoff = timezone.now() - timedelta(seconds=WINDOW_SECONDS)

    qs = RateLimitLog.objects.filter(action=action, created_at__gte=cutoff)
    if user is not None:
        qs = qs.filter(user=user)
    else:
        qs = qs.filter(ip=ip)

    exceeded = qs.count() >= limit
    RateLimitLog.objects.create(user=user, ip=ip, action=action)
    return exceeded


def rate_limit(action, redirect_to=None, message=None, limit=None, methods=("POST",)):
    """Декоратор: ограничивает частоту действия для пользователя/IP.

    Лимит по умолчанию берётся из settings.RATE_LIMIT_<ACTION>_PER_MINUTE
    в момент запроса (не при импорте) — это позволяет менять лимиты
    через override_settings в тестах. По умолчанию учитываются только POST.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return view_func(request, *args, **kwargs)
            current_limit = limit if limit is not None else action_limit(action)
            if is_limited(request, action, current_limit):
                if redirect_to is not None:
                    target = (
                        redirect_to(request, *args, **kwargs)
                        if callable(redirect_to)
                        else redirect_to
                    )
                    messages.error(
                        request,
                        message or "Слишком много запросов. Попробуйте через минуту.",
                    )
                    return redirect(target)
                return HttpResponse("Слишком много запросов", status=429)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def action_limit(name):
    """Достаёт лимит из settings по имени (например 'upload')."""
    return getattr(settings, f"RATE_LIMIT_{name.upper()}_PER_MINUTE", 10)