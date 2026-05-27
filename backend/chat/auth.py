"""
服务间认证 — AI Service 通过 Service Token 调用 Django API

用法：ai-service 在请求头中携带 Authorization: Service <token>，
并在请求参数中传递 user_id，Django 会查找对应 User 并设为 request.user。
"""
import os
import logging

from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)

User = get_user_model()

# 服务间通信 Token（与 ai-service 的 core/config.py SERVICE_AUTH_TOKEN 保持一致）
SERVICE_TOKEN = os.getenv("SERVICE_AUTH_TOKEN", "")


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    """
    服务间 Token 认证。

    请求格式：
        Authorization: Service <token>
        Query/Body 参数: user_id=<int>

    认证流程：
        1. 检查 Authorization header 是否以 "Service " 开头
        2. 验证 token 是否匹配环境变量 SERVICE_AUTH_TOKEN
        3. 根据 user_id 参数查找 User 对象
    """

    keyword = "Service"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        logger.info(f"[ServiceAuth] Authorization header: {auth_header[:50] if auth_header else '(empty)'}")

        if not auth_header.startswith(f"{self.keyword} "):
            logger.debug(f"[ServiceAuth] Not a Service token, skipping")
            return None  # 不匹配，交给其他认证类处理

        token = auth_header[len(self.keyword) + 1:].strip()

        if not SERVICE_TOKEN:
            logger.error("[ServiceAuth] SERVICE_TOKEN not configured in Django")
            raise exceptions.AuthenticationFailed("服务间认证未配置")
        if token != SERVICE_TOKEN:
            logger.warning(f"[ServiceAuth] Token mismatch: got={token[:10]}... expected={SERVICE_TOKEN[:10]}...")
            raise exceptions.AuthenticationFailed("无效的服务 Token")

        # 从请求中获取 user_id（兼容 DRF Request 和 Django WSGIRequest）
        if hasattr(request, 'query_params'):
            user_id = request.query_params.get("user_id")
        else:
            user_id = request.GET.get("user_id")
        if not user_id:
            user_id = request.data.get("user_id") if hasattr(request, 'data') else None
        if not user_id:
            raise exceptions.AuthenticationFailed("缺少 user_id 参数")

        try:
            user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            raise exceptions.AuthenticationFailed(f"用户不存在: {user_id}")

        return (user, "service")

    def authenticate_header(self, request):
        return self.keyword
