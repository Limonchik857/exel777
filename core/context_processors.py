def nav_section(request):
    """Активный раздел навигации по текущему URL-маршруту."""
    section = "dashboard"
    if not request.user.is_authenticated:
        return {"section": section}

    resolver = getattr(request, "resolver_match", None)
    app = getattr(resolver, "app_name", None)
    name = getattr(resolver, "url_name", "")

    if app == "files":
        section = "history" if name in ("history",) else "files"
    elif app == "workflows":
        section = "workflows"
    elif app == "core":
        section = "settings" if name in ("settings",) else "dashboard"
    return {"section": section}