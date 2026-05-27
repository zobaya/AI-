"""mybackend URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    # API v1
    path("api/auth/", include("users.urls")),
    path("api/chat/", include("chat.urls")),
    path("api/knowledge/", include("knowledge.urls")),
    path("api/org/", include("org.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/tags/", include("tags.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
