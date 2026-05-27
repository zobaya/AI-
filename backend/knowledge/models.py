"""知识库文档模型"""
from django.db import models
from users.models import KnowledgeBase, User


class Document(models.Model):
    """知识库文档（Django 本地持久化）"""

    STATUS_CHOICES = [
        ("pending", "待处理"),
        ("processing", "处理中"),
        ("completed", "已完成"),
        ("failed", "处理失败"),
    ]

    doc_id = models.CharField("文档 ID", max_length=100, unique=True)
    kb = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="所属知识库",
    )
    file_name = models.CharField("原始文件名", max_length=500)
    minio_path = models.CharField("MinIO 路径", max_length=500)
    file_size = models.PositiveIntegerField("文件大小(字节)", default=0)
    content_type = models.CharField("MIME 类型", max_length=100, blank=True)
    category_l1 = models.ForeignKey(
        "tags.Tag",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_l1",
        verbose_name="一级分类",
    )
    category_l2 = models.ForeignKey(
        "tags.Tag",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_l2",
        verbose_name="二级分类",
    )
    status = models.CharField(
        "处理状态", max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    is_active = models.BooleanField("激活状态", default=True)
    task_id = models.CharField("Celery 任务 ID", max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name="上传者"
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "文档"
        verbose_name_plural = "文档"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file_name} ({self.doc_id})"
