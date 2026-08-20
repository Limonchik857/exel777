from django.urls import path

from . import views

app_name = "quality"

urlpatterns = [
    path("", views.quality, name="index"),
]