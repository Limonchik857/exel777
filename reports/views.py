from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from files import processing as proc

from .services import (
    chart_bar,
    chart_line,
    chart_pie,
    column_choices,
    detect_kind,
    kpi_cards,
    report_table,
)


@login_required
def report(request):
    if not proc.has_session(request):
        messages.info(request, "Сначала загрузите файл.")
        return redirect("files:upload")

    state = proc.get_state(request)
    df = proc.current_df(request)

    columns = column_choices(df)
    bar_col = request.GET.get("bar") or (columns[0] if columns else None)
    line_col = request.GET.get("line") or (
        next((c for c in columns if detect_kind(df, c) == "numeric"), None)
        or (columns[1] if len(columns) > 1 else (columns[0] if columns else None))
    )
    pie_col = request.GET.get("pie") or (
        next((c for c in columns if detect_kind(df, c) == "text"), None)
        or (columns[0] if columns else None)
    )

    context = {
        "section": "reports",
        "source_name": state["source_name"],
        "cards": kpi_cards(df),
        "table": report_table(df),
        "columns": columns,
        "kinds": {c: detect_kind(df, c) for c in columns},
        "bar_col": bar_col,
        "line_col": line_col,
        "pie_col": pie_col,
        "bar_svg": chart_bar(df, bar_col) if bar_col else None,
        "line_svg": chart_line(df, line_col) if line_col else None,
        "pie_svg": chart_pie(df, pie_col) if pie_col else None,
        "total_rows": len(df),
    }
    return render(request, "reports/report.html", context)


@login_required
def report_export(request):
    if not proc.has_session(request):
        messages.info(request, "Сначала загрузите файл.")
        return redirect("files:upload")

    state = proc.get_state(request)
    df = proc.current_df(request)

    columns = column_choices(df)
    html = render_to_string(
        "reports/report_export.html",
        {
            "source_name": state["source_name"],
            "cards": kpi_cards(df),
            "table": report_table(df, limit=100),
            "columns": columns,
            "kinds": {c: detect_kind(df, c) for c in columns},
            "bar_col": columns[0] if columns else None,
            "line_col": next((c for c in columns if detect_kind(df, c) == "numeric"), None),
            "pie_col": next((c for c in columns if detect_kind(df, c) == "text"), None),
            "bar_svg": chart_bar(df, columns[0]) if columns else None,
            "line_svg": chart_line(df, next((c for c in columns if detect_kind(df, c) == "numeric"), None))
            if any(detect_kind(df, c) == "numeric" for c in columns)
            else None,
            "pie_svg": chart_pie(df, next((c for c in columns if detect_kind(df, c) == "text"), None))
            if any(detect_kind(df, c) == "text" for c in columns)
            else None,
            "total_rows": len(df),
        },
    )
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="report.html"'
    return response