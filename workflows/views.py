from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from files.services import validate_uploaded
from operations.validators import FileValidationError
from operations.services import OPERATION_ICONS, OPERATION_LABELS

from .forms import WorkflowForm, WorkflowRunForm
from .models import Execution, Workflow
from .services import create_workflow_from_session, run_workflow


@login_required
def index(request):
    workflows = (
        Workflow.objects.filter(user=request.user)
        .prefetch_related("operations")
        .annotate_runs()
    )
    return render(
        request,
        "workflows/index.html",
        {
            "section": "workflows",
            "workflows": workflows,
            "icons": OPERATION_ICONS,
        },
    )


@login_required
def detail(request, pk):
    workflow = get_object_or_404(Workflow, pk=pk, user=request.user)
    operations = list(workflow.operations.all())
    executions = (
        Execution.objects.filter(workflow=workflow)
        .select_related("input_file", "output_file")
        .order_by("-created_at")[:20]
    )
    from operations.services import describe_operation

    op_steps = [
        {
            "op": op,
            "label": describe_operation(op.operation_type, op.configuration),
        }
        for op in operations
    ]
    return render(
        request,
        "workflows/detail.html",
        {
            "section": "workflows",
            "workflow": workflow,
            "operations": operations,
            "op_steps": op_steps,
            "executions": executions,
            "labels": OPERATION_LABELS,
            "icons": OPERATION_ICONS,
        },
    )


@login_required
def create_from_session(request):
    state = request.session.get("processing")
    if not state or not state["history"]:
        messages.info(request, "Сначала загрузите файл и выполните операции.")
        return redirect("files:upload")

    from files import processing as proc

    steps = [h for h in proc.applied_history(state) if h.get("op") != "export"]
    if not steps:
        messages.info(request, "В текущей обработке нет операций для сохранения.")
        return redirect("files:processor")

    if request.method == "POST":
        form = WorkflowForm(request.POST)
        if form.is_valid():
            workflow = create_workflow_from_session(
                request,
                form.cleaned_data["name"],
                form.cleaned_data["description"],
            )
            if workflow is None:
                messages.error(request, "Не удалось сохранить workflow.")
                return redirect("files:processor")
            messages.success(request, f"Workflow «{workflow.name}» сохранён.")
            return redirect("workflows:detail", pk=workflow.pk)
    else:
        form = WorkflowForm()

    return render(
        request,
        "workflows/create.html",
        {
            "section": "workflows",
            "form": form,
            "steps": steps,
            "labels": OPERATION_LABELS,
        },
    )


@login_required
def run(request, pk):
    workflow = get_object_or_404(Workflow, pk=pk, user=request.user)
    if request.method == "POST":
        form = WorkflowRunForm(request.POST, request.FILES)
        if form.is_valid():
            request_file = request.FILES["file"]
            try:
                validate_uploaded(request_file, _max_size())
            except FileValidationError as exc:
                messages.error(request, str(exc))
                return redirect("workflows:run", pk=workflow.pk)
            execution = run_workflow(request.user, workflow, request_file)
            if execution.status == Execution.Status.SUCCESS:
                messages.success(
                    request,
                    "Workflow выполнен. Файл готов к скачиванию.",
                )
            else:
                messages.error(request, execution.error or "Произошла ошибка при выполнении.")
            return redirect("workflows:detail", pk=workflow.pk)
    else:
        form = WorkflowRunForm()

    return render(
        request,
        "workflows/run.html",
        {
            "section": "workflows",
            "workflow": workflow,
            "form": form,
        },
    )


@login_required
def delete(request, pk):
    workflow = get_object_or_404(Workflow, pk=pk, user=request.user)
    if request.method == "POST":
        name = workflow.name
        workflow.delete()
        messages.success(request, f"Workflow «{name}» удалён.")
        return redirect("workflows:index")
    return render(
        request,
        "workflows/delete.html",
        {"section": "workflows", "workflow": workflow},
    )


def _max_size():
    from django.conf import settings

    return settings.DATA_MAX_FILE_SIZE