"""用户认证 Serializers"""
from rest_framework import serializers
from .models import User, Department


class DepartmentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    department = DepartmentBriefSerializer(read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "role", "department",
            "phone", "avatar", "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri("/api/auth/avatar/")
        return f"/api/auth/avatar/"


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone = attrs["phone"]
        password = attrs["password"]
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise serializers.ValidationError("手机号或密码错误")
        if not user.check_password(password):
            raise serializers.ValidationError("手机号或密码错误")
        if not user.is_active:
            raise serializers.ValidationError("账号已被禁用")
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("旧密码错误")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    department = DepartmentBriefSerializer(read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "role", "department", "phone", "avatar", "date_joined"]
        read_only_fields = ["id", "username", "role", "department", "date_joined"]

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri("/api/auth/avatar/")
        return f"/api/auth/avatar/"
