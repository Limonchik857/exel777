from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from files import processing as proc
from files.views import PREVIEW_ROWS, _format_size
from operations.engine import prepare_df_for_display

from .services import analyze_quality


@login_required
def quality(request):
    if not proc.has_session(request):
        return render(
            request,
            "quality/quality.html",
            {"section": "quality", "no_file": True},
        )

    from files.models import UploadedFile

    state = proc.get_state(request)
    uploaded = UploadedFile.objects.filter(
        pk=state["uploaded_file_id"], user=request.user
    ).first()
    df = proc.current_df(request)
    report = analyze_quality(df)

    # Для карточек «Show rows» показываем сами проблемные строки.
    issue_rows = {}
    for issue in report["issues"]:
        if not issue["rows"]:
            continue
        rows_df = df.loc[[i for i in issue["rows"] if i in df.index]].head(50)
        issue_rows[issue["category"]] = {
            "columns": [str(c) for c in rows_df.columns],
            "rows": prepare_df_for_display(rows_df).to_dict("records"),
        }

    columns = [str(c) for c in df.columns]
    return render(
        request,
        "quality/quality.html",
        {
            "section": "quality",
            "report": report,
            "source_name": state["source_name"],
            "total_rows": len(df),
            "columns": columns,
            "column_types": report["column_types"],
            "issue_rows": issue_rows,
            "file_size_display": _format_size(uploaded.size) if uploaded else "",
        },
    )