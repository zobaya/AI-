"""用户认证 Views"""
import mimetypes
import uuid

from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from knowledge.minio_client import upload_to_bucket, delete_from_bucket, get_minio_client

from .models import User
from .serializers import (
    LoginSerializer,
    ChangePasswordSerializer,
    UserProfileSerializer,
    UserSerializer,
)

AVATAR_BUCKET = "avatar"

REFRESH_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 天


def _set_refresh_cookie(response, value):
    """统一设置 refresh_token HttpOnly Cookie"""
    response.set_cookie(
        key="refresh_token",
        value=value,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/api/auth",
    )


class LoginView(APIView):
    """账号密码登录，返回 Access Token + 用户信息，Refresh Token 通过 HttpOnly Cookie 下发"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        refresh = RefreshToken.for_user(user)
        response = Response({
            "access": str(refresh.access_token),
            "user": UserSerializer(user, context={"request": request}).data,
        })
        _set_refresh_cookie(response, str(refresh))
        return response


class CookieRefreshView(APIView):
    """用 Cookie 中的 refresh_token 换新的 access_token，滑动窗口续期"""
    permission_classes = [AllowAny]

    def post(self, request):
        raw_token = request.COOKIES.get("refresh_token")
        if not raw_token:
            return Response({"detail": "无刷新凭证"}, status=401)

        try:
            old_refresh = RefreshToken(raw_token)
        except (InvalidToken, TokenError):
            return Response({"detail": "刷新凭证无效或已过期"}, status=401)

        # 生成新 Token 对（滑动窗口：每次刷新重置 30 天）
        user_id = old_refresh["user_id"]
        user = User.objects.get(id=user_id, is_active=True)
        new_refresh = RefreshToken.for_user(user)
        old_refresh.blacklist()

        response = Response({"access": str(new_refresh.access_token)})
        _set_refresh_cookie(response, str(new_refresh))
        return response


class LogoutView(APIView):
    """退出登录：黑名单 refresh_token + 清除 Cookie"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw_token = request.COOKIES.get("refresh_token")
        if raw_token:
            try:
                refresh = RefreshToken(raw_token)
                refresh.blacklist()
            except (InvalidToken, TokenError):
                pass

        response = Response({"message": "已退出登录"})
        response.delete_cookie("refresh_token", path="/api/auth")
        return response


class ProfileView(APIView):
    """获取/更新当前用户信息"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user, context={"request": request}).data)

    def put(self, request):
        user = request.user
        if "old_password" in request.data:
            ser = ChangePasswordSerializer(data=request.data, context={"request": request})
            ser.is_valid(raise_exception=True)
            user.set_password(ser.validated_data["new_password"])
            user.save()
            return Response({"message": "密码已修改"})
        return Response({"message": "无更新"})


class AvatarUploadView(APIView):
    """上传头像到 MinIO（POST，需 JWT）/ 从 MinIO 获取头像（GET，token 通过 query 传递）"""
    parser_classes = [MultiPartParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        """代理返回当前用户的头像图片，通过 ?token=xxx 认证"""
        raw_token = request.query_params.get("token", "")
        if not raw_token:
            return HttpResponse(status=401)

        try:
            access_token = AccessToken(raw_token)
            user_id = access_token["user_id"]
            user = User.objects.get(id=user_id, is_active=True)
        except (InvalidToken, TokenError, User.DoesNotExist):
            return HttpResponse(status=401)

        if not user.avatar:
            return HttpResponse(status=404)

        try:
            client = get_minio_client()
            resp = client.get_object(AVATAR_BUCKET, user.avatar)
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            data = resp.read()
            resp.close()
            resp.release_conn()
            return HttpResponse(data, content_type=content_type)
        except Exception:
            return HttpResponse(status=404)

    def post(self, request):
        avatar = request.FILES.get("avatar")
        if not avatar:
            return Response({"error": "请选择图片"}, status=400)

        # 限制 2MB
        if avatar.size > 2 * 1024 * 1024:
            return Response({"error": "图片大小不能超过 2MB"}, status=400)

        ext = mimetypes.guess_extension(avatar.content_type) or ".jpg"
        object_name = f"{uuid.uuid4().hex}{ext}"

        # 读取文件全部字节
        data = avatar.read()

        # 删除旧头像
        if request.user.avatar:
            delete_from_bucket(AVATAR_BUCKET, request.user.avatar)

        content_type = avatar.content_type or "application/octet-stream"
        upload_to_bucket(AVATAR_BUCKET, object_name, data, content_type)

        request.user.avatar = object_name
        request.user.save()

        return Response({"avatar": request.build_absolute_uri("/api/auth/avatar/")})

    def delete(self, request):
        """恢复默认头像：删除 MinIO 中的头像文件，清空 avatar 字段"""
        if request.user.avatar:
            delete_from_bucket(AVATAR_BUCKET, request.user.avatar)
            request.user.avatar = ""
            request.user.save()
        return Response({"avatar": None})
