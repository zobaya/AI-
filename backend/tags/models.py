from django.db import models


class Tag(models.Model):
    """标签分类（两级层次结构）"""

    name = models.CharField("标签名称", max_length=100)
    description = models.TextField("描述", blank=True, default="")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="父级标签",
    )
    level = models.PositiveSmallIntegerField("层级", default=1)
    sort_order = models.IntegerField("排序序号", default=0)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="创建人",
        related_name="created_tags",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "标签"
        verbose_name_plural = "标签"
        ordering = ["sort_order", "id"]
        unique_together = [("parent", "name")]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.parent:
            if self.parent.level != 1:
                raise ValidationError("最多支持两级标签层次")
            self.level = 2
        else:
            self.level = 1
