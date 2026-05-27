"""自定义权限"""
from rest_framework.permissions import BasePermission


class IsSysAdmin(BasePermission):
    """仅系统管理员"""

    def has_permission(self, request, view):
        return request.user and request.user.role == "sys_admin"


class IsDeptAdmin(BasePermission):
    """部门管理员及以上"""

    def has_permission(self, request, view):
        return request.user and request.user.role in ("dept_admin", "sys_admin")


class IsSameDepartmentOrSysAdmin(BasePermission):
    """同部门或系统管理员"""

    def has_object_permission(self, request, view, obj):
        if request.user.role == "sys_admin":
            return True
        return getattr(obj, "department_id", None) == request.user.department_id
