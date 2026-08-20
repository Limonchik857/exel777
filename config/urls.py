from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("files/", include("files.urls")),
    path("workflows/", include("workflows.urls")),
    path("quality/", include("quality.urls")),
]

# Медиафайлы (исходные и обработанные таблицы) — личные данные пользователей.
# Их отдаёт только core.views.ProtectedFileView, который проверяет владельца.