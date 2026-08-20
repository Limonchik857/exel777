from django.urls import path

from . import views

app_name = "workflows"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create_from_session, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/run/", views.run, name="run"),
    path("<int:pk>/schedule/", views.schedule, name="schedule"),
    path("<int:pk>/delete/", views.delete, name="delete"),
]