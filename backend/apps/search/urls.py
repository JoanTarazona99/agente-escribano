"""URLs de la app search."""
from django.urls import path

from .views import SearchView

urlpatterns = [
    path("search/", SearchView.as_view(), name="search"),
]
