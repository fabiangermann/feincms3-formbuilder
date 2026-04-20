from django.urls import include, path

urlpatterns = [
    path("forms/", include("testapp.urls", namespace="forms")),
]
