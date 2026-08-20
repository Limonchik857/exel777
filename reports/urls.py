from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report, name="index"),
    path("export/", views.report_export, name="export"),
]