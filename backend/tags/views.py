"""标签管理 Views"""
import logging
import os

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from users.permissions import IsSysAdmin
from .models import Tag

logger = logging.getLogger(__name__)


def _tag_dict(tag):
    """将 Tag 对象转为包含 doc_count 和 created_by 的字典"""
    # 动态计算引用计数
    doc_count = tag.documents_l1.count() + tag.documents_l2.count()
    return {
        "id": tag.id,
        "name": tag.name,
        "description": tag.description,
        "parent": tag.parent_id,
        "level": tag.level,
        "sort_order": tag.sort_order,
        "created_by": tag.created_by.username if tag.created_by else None,
        "doc_count": doc_count,
        "created_at": tag.created_at,
        "updated_at": tag.updated_at,
    }


def _invalidate_tag_cache():
    """通知 AI Service 清除标签注册表缓存"""
    try:
        import requests

        service_token = os.getenv("SERVICE_AUTH_TOKEN", "")
        ai_base = settings.AI_SERVICE_BASE_URL
        requests.post(
            f"{ai_base}/api/kb/internal/cache/invalidate",
            headers={"Authorization": f"Service {service_token}"},
            json={"scope": "tag_registry"},
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"清除 AI Service 标签缓存失败: {e}")


def _cleanup_es_tags(tag_ids: list[int]):
    """通知 AI Service 从 ES 中清洗已删除的标签 ID"""
    try:
        import requests

        service_token = os.getenv("SERVICE_AUTH_TOKEN", "")
        ai_base = settings.AI_SERVICE_BASE_URL
        requests.post(
            f"{ai_base}/api/kb/internal/tags/cleanup",
            headers={"Authorization": f"Service {service_token}"},
            json={"tag_ids": tag_ids},
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"ES 标签清洗失败: {e}")


class TagTreeView(APIView):
    """获取标签树"""

    permission_classes = [IsAuthenticated, IsSysAdmin]

    def get(self, request):
        roots = Tag.objects.filter(parent=None).prefetch_related(
            "children", "children__documents_l1", "children__documents_l2",
            "documents_l1", "documents_l2",
        )
        data = []
        for root in roots:
            item = _tag_dict(root)
            item["parent"] = None
            item["children"] = [_tag_dict(c) for c in root.children.all()]
            data.append(item)
        return Response(data)


class TagCreateView(APIView):
    """创建标签"""

    permission_classes = [IsAuthenticated, IsSysAdmin]

    def post(self, request):
        name = request.data.get("name", "").strip()
        if not name:
            return Response({"error": "标签名称不能为空"}, status=400)

        description = request.data.get("description", "").strip()
        parent_id = request.data.get("parent_id")

        if parent_id:
            parent = Tag.objects.filter(pk=parent_id, level=1).first()
            if not parent:
                return Response({"error": "父级标签不存在或不是一级标签"}, status=400)
            if Tag.objects.filter(parent=parent, name=name).exists():
                return Response({"error": "该一级分类下已存在同名二级标签"}, status=400)
            tag = Tag.objects.create(
                name=name, description=description, parent=parent, level=2,
                created_by=request.user,
            )
        else:
            if Tag.objects.filter(parent=None, name=name).exists():
                return Response({"error": "已存在同名一级标签"}, status=400)
            tag = Tag.objects.create(
                name=name, description=description, level=1,
                created_by=request.user,
            )

        # 清除 AI Service 标签缓存
        _invalidate_tag_cache()
        return Response(_tag_dict(tag), status=201)


class TagDetailView(APIView):
    """更新 / 删除标签"""

    permission_classes = [IsAuthenticated, IsSysAdmin]

    def put(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        name = request.data.get("name")
        if name is not None:
            name = name.strip()
            if not name:
                return Response({"error": "标签名称不能为空"}, status=400)
            # 检查同级是否重名
            dup_qs = Tag.objects.filter(name=name).exclude(pk=pk)
            if tag.parent:
                dup_qs = dup_qs.filter(parent=tag.parent)
            else:
                dup_qs = dup_qs.filter(parent=None)
            if dup_qs.exists():
                return Response({"error": "同级已存在同名标签"}, status=400)
            tag.name = name

        description = request.data.get("description")
        if description is not None:
            tag.description = description.strip()

        sort_order = request.data.get("sort_order")
        if sort_order is not None:
            tag.sort_order = sort_order

        tag.save()
        # 清除 AI Service 标签缓存（标签名/描述可能影响分类）
        _invalidate_tag_cache()
        return Response(_tag_dict(tag))

    def delete(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        # 收集需要清洗的标签 ID（包含级联删除的子标签）
        child_ids = list(
            tag.children.values_list("id", flat=True)
        ) if tag.level == 1 else []
        tag_ids_to_clean = [pk] + child_ids
        child_count = len(child_ids)

        tag.delete()

        # 同步清洗 ES 中引用了这些标签 ID 的 chunk
        _cleanup_es_tags(tag_ids_to_clean)
        # 清除 AI Service 标签缓存
        _invalidate_tag_cache()

        return Response({"message": "已删除", "child_count": child_count})


class TagRegistryInternalView(APIView):
    """
    标签注册表内部接口 — 供 AI Service 获取分类体系。

    认证：Authorization: Service <token>（仅需验证 Token，无需 user_id）
    返回格式包含 id 字段的树状 JSON。
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from chat.auth import SERVICE_TOKEN

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Service "):
            return Response({"error": "未授权"}, status=401)
        token = auth_header[8:].strip()
        if not SERVICE_TOKEN or token != SERVICE_TOKEN:
            return Response({"error": "无效的认证 Token"}, status=401)

        l1_tags = Tag.objects.filter(parent=None).prefetch_related(
            "children"
        ).order_by("sort_order", "id")

        categories = []
        for l1 in l1_tags:
            categories.append({
                "id": l1.id,
                "category_l1": l1.name,
                "description": l1.description or "",
                "category_l2": [
                    {
                        "id": child.id,
                        "name": child.name,
                        "description": child.description or "",
                    }
                    for child in l1.children.all().order_by("sort_order", "id")
                ],
            })

        return Response({"categories": categories})


class TagDocumentsView(APIView):
    """获取标签关联的文档列表"""

    permission_classes = [IsAuthenticated, IsSysAdmin]

    def get(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        from knowledge.models import Document

        qs = Document.objects.filter(
            Q(category_l1=tag) | Q(category_l2=tag)
        ).select_related("kb")
        total = qs.count()
        docs = [
            {
                "id": d.id,
                "file_name": d.file_name,
                "kb_name": d.kb.name if d.kb else None,
            }
            for d in qs[:50]
        ]
        return Response({"documents": docs, "total": total})
