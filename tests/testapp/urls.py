from django.urls import path

from testapp import views

app_name = "forms"

urlpatterns = [
    path("<slug:slug>/", views.form_view, name="form"),
]
