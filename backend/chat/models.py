"""会话、消息、快捷提示词模型"""
from django.db import models
from django.conf import settings


class ConversationFolder(models.Model):
    """会话文件夹"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="用户",
        related_name="chat_folders",
    )
    name = models.CharField("文件夹名称", max_length=100)
    sort_order = models.IntegerField("排序权重", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "会话文件夹"
        verbose_name_plural = "会话文件夹"
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return f"{self.user.username}/{self.name}"


class Conversation(models.Model):
    """会话"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="用户",
        related_name="conversations",
    )
    folder = models.ForeignKey(
        ConversationFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="文件夹",
        related_name="conversations",
    )
    title = models.CharField("会话标题", max_length=200, default="新对话")
    agent_name = models.CharField("Agent 标识", max_length=100, blank=True, default="")
    is_pinned = models.BooleanField("置顶", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "会话"
        verbose_name_plural = "会话"
        ordering = ["-is_pinned", "-updated_at"]

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class Message(models.Model):
    """消息"""

    ROLE_CHOICES = [
        ("user", "用户"),
        ("assistant", "AI 助手"),
    ]
    FEEDBACK_CHOICES = [
        ("like", "点赞"),
        ("dislike", "点踩"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        verbose_name="会话",
        related_name="messages",
    )
    role = models.CharField("角色", max_length=20, choices=ROLE_CHOICES)
    content = models.TextField("内容")
    workflow_id = models.CharField("LangGraph 执行 ID", max_length=100, blank=True, default="")
    metadata_json = models.JSONField(
        "Agent 执行轨迹",
        default=dict,
        blank=True,
        help_text="存放 Agent 完整执行轨迹（entries 数组），用于前端还原思考步骤",
    )
    tokens_used = models.IntegerField("Token 消耗", default=0)
    feedback = models.CharField(
        "反馈", max_length=10, null=True, blank=True, choices=FEEDBACK_CHOICES
    )
    feedback_detail = models.JSONField(
        "反馈详情", null=True, blank=True,
        help_text='{"reasons": ["内容准确"], "comment": "可选文本"}',
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "消息"
        verbose_name_plural = "消息"
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:50]}"


class MessageAttachment(models.Model):
    """消息附件 — 聊天中上传的临时文件，与知识库文档隔离"""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        verbose_name="消息",
        related_name="attachments",
    )
    file_name = models.CharField("原始文件名", max_length=500)
    file_path_minio = models.CharField("MinIO 存储路径", max_length=500)
    file_size = models.IntegerField("文件大小", default=0)
    content_type = models.CharField("MIME 类型", max_length=100, blank=True, default="")
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "消息附件"
        verbose_name_plural = "消息附件"

    def __str__(self):
        return self.file_name


class PromptLibrary(models.Model):
    """快捷提示词库"""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="所有者（null=系统预设）",
        related_name="prompts",
    )
    title = models.CharField("标题", max_length=200)
    content = models.TextField("提示词内容")
    is_system = models.BooleanField("系统预设", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "快捷提示词"
        verbose_name_plural = "快捷提示词"
        ordering = ["-is_system", "-created_at"]

    def __str__(self):
        prefix = "[系统]" if self.is_system else "[用户]"
        return f"{prefix} {self.title}"


class UserMemory(models.Model):
    """用户长期记忆 — 存储从对话中抽取的事实"""

    CATEGORY_CHOICES = [
        ("preference", "偏好"),
        ("knowledge", "知识"),
        ("goal", "目标"),
        ("context", "背景"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="用户",
        related_name="memories",
    )
    agent_name = models.CharField("Agent 标识", max_length=100, default="default")

    # 记忆内容
    fact = models.TextField("事实内容")
    category = models.CharField("分类", max_length=50, choices=CATEGORY_CHOICES)
    confidence = models.FloatField("置信度", default=0.5)

    # 元数据
    source_conv_id = models.IntegerField("来源会话 ID", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    access_count = models.IntegerField("被使用次数", default=0)

    class Meta:
        verbose_name = "用户记忆"
        verbose_name_plural = "用户记忆"
        db_table = "chat_memory"
        indexes = [
            models.Index(fields=["user", "agent_name", "-confidence"], name="idx_memory_user_conf"),
            models.Index(fields=["user", "category"], name="idx_memory_user_cat"),
        ]

    def __str__(self):
        return f"[{self.category}] {self.fact[:50]}"


class GeneratedFile(models.Model):
    """AI 生成的文件（PPT 等）"""

    FILE_TYPE_CHOICES = [
        ("pptx", "PowerPoint"),
        ("pdf", "PDF"),
        ("xlsx", "Excel"),
        ("other", "其他"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="所属用户",
        related_name="generated_files",
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="关联会话",
        related_name="generated_files",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="关联消息",
        related_name="generated_files",
    )
    file_name = models.CharField("文件名", max_length=500)
    minio_path = models.CharField("MinIO 路径", max_length=500)
    file_size = models.IntegerField("文件大小(bytes)", default=0)
    file_type = models.CharField("文件类型", max_length=20, choices=FILE_TYPE_CHOICES, default="pptx")
    # PPT 特有元数据
    slide_count = models.IntegerField("幻灯片页数", default=0)
    theme = models.CharField("主题风格", max_length=50, blank=True, default="")
    # 过期管理
    expires_at = models.DateTimeField("过期时间", null=True, blank=True, help_text="为空表示不过期")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "AI 生成文件"
        verbose_name_plural = "AI 生成文件"
        db_table = "chat_generated_file"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_genfile_user_created"),
        ]

    def __str__(self):
        return f"{self.user.username}/{self.file_name}"
