from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, TemplateView

from files.models import ProcessedFile
from workflows.models import Execution, Workflow

from .auth_backend import EmailAuthBackend
from .forms import ProfileSettingsForm, RegisterForm


def safe_next(request, fallback):
    target = request.POST.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}
    ):
        return target
    return fallback


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = "core/register.html"
    success_url = reverse_lazy("core:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(
            self.request,
            self.object,
            backend="core.auth_backend.EmailAuthBackend",
        )
        return response


class AppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        login(
            self.request,
            form.get_user(),
            backend="core.auth_backend.EmailAuthBackend",
        )
        return super().form_valid(form)


class AppLogoutView(TemplateView):
    template_name = "core/logout_confirm.html"

    def post(self, request):
        logout(request)
        return redirect("core:login")


@login_required
def settings_view(request):
    user = request.user
    if request.method == "POST":
        form = ProfileSettingsForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Настройки сохранены.")
            return redirect("core:settings")
    else:
        form = ProfileSettingsForm(instance=user)

    return render(
        request,
        "core/settings.html",
        {
            "form": form,
            "max_file_size_mb": django_settings.DATA_MAX_FILE_SIZE // (1024 * 1024),
        },
    )


@login_required
def dashboard(request):
    user = request.user
    processed = ProcessedFile.objects.filter(user=user)
    workflows = Workflow.objects.filter(user=user)
    executions = Execution.objects.filter(user=user)

    context = {
        "section": "dashboard",
        "files_count": processed.count(),
        "workflows_count": workflows.count(),
        "runs_count": executions.count(),
        "last_executions": executions.select_related(
            "workflow", "input_file", "output_file"
        ).order_by("-created_at")[:6],
        "last_workflows": workflows.prefetch_related("operations").order_by(
            "-updated_at"
        )[:6],
        "last_files": processed.order_by("-created_at")[:6],
    }
    return render(request, "core/dashboard.html", context)


@login_required
def download_source(request, pk):
    from files.models import UploadedFile

    obj = UploadedFile.objects.filter(pk=pk, user=request.user).first()
    if obj is None:
        raise Http404("Не найдено.")
    from django.http import FileResponse

    try:
        handle = obj.file.open("rb")
    except Exception:
        raise Http404("Файл не найден.")
    response = FileResponse(handle)
    response["Content-Disposition"] = f'attachment; filename="{obj.original_name}"'
    return response


@login_required
def download_processed(request, pk):
    from files.models import ProcessedFile

    obj = ProcessedFile.objects.filter(pk=pk, user=request.user).first()
    if obj is None:
        raise Http404("Не найдено.")
    from django.http import FileResponse

    try:
        handle = obj.file.open("rb")
    except Exception:
        raise Http404("Файл не найден.")
    response = FileResponse(handle)
    response["Content-Disposition"] = f'attachment; filename="{obj.original_name}"'
    return response