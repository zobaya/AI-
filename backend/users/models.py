"""用户、部门、知识库权限模型"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """自定义用户管理器（不依赖 PermissionsMixin）"""

    def _create_user(self, username, password, **extra_fields):
        if not username:
            raise ValueError("必须设置用户名")
        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(username, password, **extra_fields)

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        return self._create_user(username, password, **extra_fields)


class Department(models.Model):
    """部门"""

    name = models.CharField("部门名称", max_length=100, unique=True)
    description = models.TextField("描述", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "部门"
        verbose_name_plural = "部门"
        ordering = ["id"]

    def __str__(self):
        return self.name


class User(AbstractBaseUser):
    """用户（扩展 AbstractBaseUser，无 PermissionsMixin）"""

    ROLE_CHOICES = [
        ("user", "普通用户"),
        ("dept_admin", "部门管理员"),
        ("sys_admin", "系统管理员"),
    ]

    username = models.CharField(
        "用户名",
        max_length=150,
        unique=True,
        validators=[UnicodeUsernameValidator()],
    )
    is_staff = models.BooleanField("staff status", default=False)
    is_active = models.BooleanField("激活状态", default=True)
    date_joined = models.DateTimeField("注册时间", default=timezone.now)

    # 自定义字段
    role = models.CharField(
        "角色", max_length=20, choices=ROLE_CHOICES, default="user"
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="所属部门",
        related_name="members",
    )
    phone = models.CharField("手机号", max_length=20, unique=True)
    avatar = models.CharField("头像", max_length=500, blank=True, default="")

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"
        ordering = ["id"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class KnowledgeBase(models.Model):
    """知识库（与 ES 中的 kb_id 对应）"""

    kb_id = models.CharField("ES 知识库 ID", max_length=100, unique=True)
    name = models.CharField("知识库名称", max_length=200)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        verbose_name="所属部门",
        related_name="knowledge_bases",
    )
    description = models.TextField("描述", blank=True, default="")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="创建者",
        related_name="created_knowledge_bases",
    )
    is_active = models.BooleanField("激活状态", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "知识库"
        verbose_name_plural = "知识库"

    def __str__(self):
        return f"{self.name} ({self.department.name})"


class UserKBPermission(models.Model):
    """用户-知识库权限"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name="用户", related_name="kb_permissions"
    )
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        verbose_name="知识库",
        related_name="user_permissions",
    )
    created_at = models.DateTimeField("授权时间", auto_now_add=True)
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="授权人",
        related_name="granted_kb_permissions",
    )

    class Meta:
        verbose_name = "知识库权限"
        verbose_name_plural = "知识库权限"
        unique_together = ("user", "knowledge_base")

    def __str__(self):
        return f"{self.user.username} -> {self.knowledge_base.name}"


class UserAgentPermission(models.Model):
    """用户-Agent 权限"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="用户",
        related_name="agent_permissions",
    )
    agent_name = models.CharField("Agent 名称", max_length=100)

    class Meta:
        verbose_name = "Agent 权限"
        verbose_name_plural = "Agent 权限"
        unique_together = ("user", "agent_name")

    def __str__(self):
        return f"{self.user.username} -> {self.agent_name}"
