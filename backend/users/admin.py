"""Admin 注册"""
from django.contrib import admin
from .models import User, Department, KnowledgeBase, UserKBPermission, UserAgentPermission


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "description", "created_at"]
    search_fields = ["name"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["id", "username", "phone", "role", "department", "is_active"]
    list_filter = ["role", "department", "is_active"]
    search_fields = ["username", "phone"]


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ["id", "kb_id", "name", "department", "created_by", "is_active"]


@admin.register(UserKBPermission)
class UserKBPermissionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "knowledge_base", "granted_by", "created_at"]


@admin.register(UserAgentPermission)
class UserAgentPermissionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "agent_name"]
