"""统计看板 API"""
from django.urls import path
from . import views

urlpatterns = [
    path("overview/", views.OverviewView.as_view()),
    path("trend/", views.TrendView.as_view()),
    path("departments-compare/", views.DepartmentCompareView.as_view()),
    path("export/", views.ExportView.as_view()),
    path("feedback/", views.FeedbackListView.as_view()),
    path("feedback/export/", views.FeedbackExportView.as_view()),
    path("user-stats/", views.UserStatsView.as_view()),
]
