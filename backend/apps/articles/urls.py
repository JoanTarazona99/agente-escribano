"""URLs de la app articles."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ArticleViewSet, SearchJobViewSet, NotebookViewSet

router = DefaultRouter()
router.register("articles", ArticleViewSet, basename="article")
router.register("jobs", SearchJobViewSet, basename="searchjob")
router.register("notebooks", NotebookViewSet, basename="notebook")

urlpatterns = [
    path("", include(router.urls)),
]
