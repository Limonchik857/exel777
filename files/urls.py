from django.urls import path

from . import views

app_name = "files"

urlpatterns = [
    path("", views.files_index, name="index"),
    path("upload/", views.upload, name="upload"),
    path("processor/", views.processor, name="processor"),
    path("apply/", views.apply_operation_view, name="apply"),
    path("undo/", views.undo, name="undo"),
    path("redo/", views.redo, name="redo"),
    path("reset/", views.reset, name="reset"),
    path("merge/", views.merge, name="merge"),
    path("download/", views.download, name="download"),
    path("history/", views.history, name="history"),
]