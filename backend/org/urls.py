"""组织架构 API"""
from django.urls import path
from . import views

urlpatterns = [
    # 部门管理
    path("departments/", views.DepartmentListView.as_view()),
    path("departments/<int:pk>/", views.DepartmentDetailView.as_view()),
    # 用户管理
    path("users/", views.UserListView.as_view()),
    path("users/create/", views.UserCreateView.as_view()),
    path("users/<int:pk>/", views.UserDetailView.as_view()),
    path("users/<int:pk>/reset-password/", views.ResetPasswordView.as_view()),
    path("users/<int:pk>/toggle-active/", views.ToggleActiveView.as_view()),
    path("users/<int:pk>/transfer/", views.TransferUserView.as_view()),
    path("users/batch-import/", views.BatchImportView.as_view()),
    # 权限管理
    path("users/<int:pk>/kb-permissions/", views.KBPermissionView.as_view()),
    path("users/<int:pk>/agent-permissions/", views.AgentPermissionView.as_view()),
    # 用户头像
    path("users/<int:pk>/avatar/", views.UserAvatarView.as_view()),
]
