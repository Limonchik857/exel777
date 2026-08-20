from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("logout/", views.AppLogoutView.as_view(), name="logout"),
    path("settings/", views.settings_view, name="settings"),
    path(
        "media/uploaded/<int:pk>/",
        views.download_source,
        name="download_source",
    ),
    path(
        "media/processed/<int:pk>/",
        views.download_processed,
        name="download_processed",
    ),
]