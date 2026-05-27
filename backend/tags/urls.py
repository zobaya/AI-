"""标签管理 API"""
from django.urls import path
from . import views

urlpatterns = [
    path("internal/registry/", views.TagRegistryInternalView.as_view(), name="tag-registry-internal"),
    path("", views.TagTreeView.as_view(), name="tag-tree"),
    path("create/", views.TagCreateView.as_view(), name="tag-create"),
    path("<int:pk>/documents/", views.TagDocumentsView.as_view(), name="tag-documents"),
    path("<int:pk>/", views.TagDetailView.as_view(), name="tag-detail"),
]
