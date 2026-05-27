"""知识库管理 Views — 本地 KB/Document CRUD + 代理 ai-service 分块"""
import uuid
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers

from users.models import KnowledgeBase, Department, UserKBPermission
from users.permissions import IsDeptAdmin, IsSysAdmin
from tags.models import Tag
from .models import Document
from .minio_client import upload_to_minio, delete_doc_folder_from_minio, get_minio_client
from django.conf import settings


AI_BASE = settings.AI_SERVICE_BASE_URL


def _proxy(method, path, params=None, json_data=None, timeout=120):
    """代理请求到 ai-service，错误时抛出 Django 可处理的异常。"""
    url = f"{AI_BASE}{path}"
    kwargs: dict = {"timeout": timeout}
    if params:
        kwargs["params"] = params
    if json_data:
        kwargs["json"] = json_data
    resp = getattr(requests, method)(url, **kwargs)
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        from rest_framework.exceptions import APIException
        exc = APIException(detail=detail)
        exc.status_code = resp.status_code
        raise exc
    return resp.json()


def _tag_info(tag):
    """将 Tag 对象转为 {id, name} 字典，None 时返回 None"""
    return {"id": tag.id, "name": tag.name} if tag else None


def _check_kb_permission(request, kb):
    """检查用户是否有权访问指定知识库，无权限返回 403 Response，否则返回 None"""
    if request.user.role == "sys_admin":
        return None
    if not UserKBPermission.objects.filter(
        user=request.user, knowledge_base=kb
    ).exists():
        return Response({"error": "无权访问此知识库"}, status=403)
    return None


def _check_doc_permission(request, doc):
    """检查用户是否有权访问文档所属的知识库"""
    return _check_kb_permission(request, doc.kb)


# ════════════════════════════════════════════════════════════════
#  知识库管理 (本地 Django DB)
# ════════════════════════════════════════════════════════════════

class KBCreatorSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    department_id = serializers.IntegerField()
    description = serializers.CharField(required=False, allow_blank=True, default="")


class KnowledgeBaseListView(APIView):
    """知识库列表（按权限过滤）"""
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        qs = KnowledgeBase.objects.select_related("department", "created_by")
        if request.user.role != "sys_admin":
            permitted_kb_ids = UserKBPermission.objects.filter(
                user=request.user
            ).values_list("knowledge_base__kb_id", flat=True)
            qs = qs.filter(kb_id__in=permitted_kb_ids)
        data = []
        for kb in qs:
            data.append({
                "kb_id": kb.kb_id,
                "name": kb.name,
                "department": {"id": kb.department.id, "name": kb.department.name},
                "description": kb.description,
                "created_by": {"id": kb.created_by.id, "username": kb.created_by.username} if kb.created_by else None,
                "is_active": kb.is_active,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        ser = KBCreatorSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        dept = get_object_or_404(Department, pk=d["department_id"])
        if request.user.role != "sys_admin" and dept.id != request.user.department_id:
            return Response({"error": "只能为本部门创建知识库"}, status=403)

        # 系统自动生成 kb_id
        kb_id = f"kb_{uuid.uuid4().hex[:8]}"

        kb = KnowledgeBase.objects.create(
            kb_id=kb_id,
            name=d["name"],
            department=dept,
            description=d.get("description", ""),
            created_by=request.user,
        )
        # 自动为创建者分配知识库权限
        UserKBPermission.objects.create(
            user=request.user, knowledge_base=kb, granted_by=request.user
        )
        return Response({
            "kb_id": kb.kb_id,
            "name": kb.name,
            "department": {"id": dept.id, "name": dept.name},
        }, status=201)


class KnowledgeBaseDetailView(APIView):
    """知识库详情/修改/删除"""
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request, kb_id):
        kb = get_object_or_404(KnowledgeBase, kb_id=kb_id)
        err = _check_kb_permission(request, kb)
        if err:
            return err
        return Response({
            "kb_id": kb.kb_id,
            "name": kb.name,
            "department": {"id": kb.department.id, "name": kb.department.name},
            "description": kb.description,
            "created_by": {"id": kb.created_by.id, "username": kb.created_by.username} if kb.created_by else None,
            "is_active": kb.is_active,
            "created_at": kb.created_at.isoformat(),
            "updated_at": kb.updated_at.isoformat(),
        })

    def put(self, request, kb_id):
        kb = get_object_or_404(KnowledgeBase, kb_id=kb_id)
        err = _check_kb_permission(request, kb)
        if err:
            return err
        if "name" in request.data:
            kb.name = request.data["name"]
        if "description" in request.data:
            kb.description = request.data["description"]
        if "department_id" in request.data and request.user.role == "sys_admin":
            kb.department_id = request.data["department_id"]
        if "is_active" in request.data:
            kb.is_active = request.data["is_active"]
        kb.save()
        return Response({"kb_id": kb.kb_id, "name": kb.name})

    def delete(self, request, kb_id):
        kb = get_object_or_404(KnowledgeBase, kb_id=kb_id)
        err = _check_kb_permission(request, kb)
        if err:
            return err
        kb.delete()
        return Response({"message": "知识库记录已删除（ES/MinIO 数据未删除）"})


# ════════════════════════════════════════════════════════════════
#  文档管理 (本地 Django DB + MinIO + 代理 ai-service 处理)
# ════════════════════════════════════════════════════════════════

class DocumentListView(APIView):
    """文档列表（从 Django DB 查询）"""
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        kb_id = request.query_params.get("kb_id")
        qs = Document.objects.select_related("kb", "uploaded_by", "category_l1", "category_l2")

        if kb_id:
            qs = qs.filter(kb__kb_id=kb_id)

        # 权限过滤：仅显示用户有权限的知识库下的文档
        if request.user.role != "sys_admin":
            permitted_kb_ids = UserKBPermission.objects.filter(
                user=request.user
            ).values_list("knowledge_base__kb_id", flat=True)
            qs = qs.filter(kb__kb_id__in=permitted_kb_ids)

        # 搜索过滤
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(file_name__icontains=search)

        # 状态过滤
        status_filter = request.query_params.get("status")
        if status_filter == "completed":
            qs = qs.filter(status="completed")
        elif status_filter == "other":
            qs = qs.exclude(status="completed")

        # 分页
        total = qs.count()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        docs = qs[(page - 1) * page_size : page * page_size]

        data = []
        for doc in docs:
            data.append({
                "doc_id": doc.doc_id,
                "file_name": doc.file_name,
                "minio_path": doc.minio_path,
                "file_size": doc.file_size,
                "category_l1": _tag_info(doc.category_l1),
                "category_l2": _tag_info(doc.category_l2),
                "status": doc.status,
                "is_active": doc.is_active,
                "task_id": doc.task_id,
                "uploaded_by": doc.uploaded_by.username if doc.uploaded_by else None,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            })
        return Response({"documents": data, "total": total})


class DocumentUploadView(APIView):
    """上传文档 — Django 直接上传 MinIO + 写 DB + 调 ai-service 处理"""
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request):
        upload_file = request.FILES.get("file")
        if not upload_file:
            return Response({"error": "请选择文件"}, status=400)

        kb_id = request.data.get("kb_id")
        if not kb_id:
            return Response({"error": "请指定 kb_id"}, status=400)

        kb = get_object_or_404(KnowledgeBase, kb_id=kb_id)
        err = _check_kb_permission(request, kb)
        if err:
            return err

        # 生成唯一 doc_id 和文件名
        doc_id = f"doc-{uuid.uuid4()}"
        ext = upload_file.name.rsplit(".", 1)[-1] if "." in upload_file.name else ""
        unique_filename = f"{uuid.uuid4()}.{ext}" if ext else str(uuid.uuid4())

        # 上传到 MinIO
        object_name = f"{kb_id}/{doc_id}/{unique_filename}"
        file_data = upload_file.read()
        minio_path = upload_to_minio(
            object_name=object_name,
            data=file_data,
            content_type=upload_file.content_type or "application/octet-stream",
        )

        # 解析标签 FK
        category_l1_id = request.data.get("category_l1_id")
        category_l2_id = request.data.get("category_l2_id")
        tag_l1 = Tag.objects.filter(pk=category_l1_id).first() if category_l1_id else None
        tag_l2 = Tag.objects.filter(pk=category_l2_id).first() if category_l2_id else None

        # 部门名称（从知识库关联获取，用于 ai-service）
        department_name = kb.department.name if kb.department else ""

        doc = Document.objects.create(
            doc_id=doc_id,
            kb=kb,
            file_name=upload_file.name,
            minio_path=minio_path,
            file_size=len(file_data),
            content_type=upload_file.content_type or "",
            category_l1=tag_l1,
            category_l2=tag_l2,
            status="pending",
            uploaded_by=request.user,
        )

        # 调 ai-service 触发处理（传标签 ID，ES 存储 integer）
        try:
            process_data = _proxy(
                "post",
                "/api/kb/upload",
                json_data={
                    "minio_path": minio_path,
                    "file_name": upload_file.name,
                    "department": department_name,
                    "category_l1": tag_l1.id if tag_l1 else None,
                    "category_l2": tag_l2.id if tag_l2 else None,
                },
            )
            task_id = process_data.get("task_id", "")
            doc.task_id = task_id
            doc.status = "processing"
            doc.save()
        except Exception as e:
            doc.status = "failed"
            doc.save()
            return Response({"error": f"触发处理失败: {e}"}, status=500)

        return Response({
            "doc_id": doc.doc_id,
            "task_id": task_id,
            "kb_id": kb_id,
            "file_name": doc.file_name,
            "minio_path": minio_path,
            "status": doc.status,
        }, status=201)


class DocumentDetailView(APIView):
    """文档详情/删除"""
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request, doc_id):
        doc = get_object_or_404(Document, doc_id=doc_id)
        err = _check_doc_permission(request, doc)
        if err:
            return err
        return Response({
            "doc_id": doc.doc_id,
            "file_name": doc.file_name,
            "minio_path": doc.minio_path,
            "file_size": doc.file_size,
            "category_l1": _tag_info(doc.category_l1),
            "category_l2": _tag_info(doc.category_l2),
            "status": doc.status,
            "is_active": doc.is_active,
            "task_id": doc.task_id,
            "kb": {"kb_id": doc.kb.kb_id, "name": doc.kb.name},
            "uploaded_by": doc.uploaded_by.username if doc.uploaded_by else None,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat(),
        })

    def delete(self, request, doc_id):
        doc = get_object_or_404(Document, doc_id=doc_id)
        err = _check_doc_permission(request, doc)
        if err:
            return err
        minio_path = doc.minio_path
        # 删除 ai-service 侧的 ES 数据
        try:
            _proxy("delete", f"/api/kb/documents/{doc_id}")
        except Exception:
            pass
        # 删除 MinIO 中的文件（整个文档目录）
        if minio_path:
            delete_doc_folder_from_minio(minio_path)
        doc.delete()
        return Response({"message": "文档已删除"})


class DocumentEnableView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request, doc_id):
        doc = get_object_or_404(Document, doc_id=doc_id)
        err = _check_doc_permission(request, doc)
        if err:
            return err
        doc.is_active = True
        doc.save()
        _proxy("post", f"/api/kb/documents/{doc_id}/enable")
        return Response({"message": "已启用"})


class DocumentDisableView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request, doc_id):
        doc = get_object_or_404(Document, doc_id=doc_id)
        err = _check_doc_permission(request, doc)
        if err:
            return err
        doc.is_active = False
        doc.save()
        _proxy("post", f"/api/kb/documents/{doc_id}/disable")
        return Response({"message": "已禁用"})


class DocumentMetadataView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def put(self, request, doc_id):
        doc = get_object_or_404(Document, doc_id=doc_id)
        err = _check_doc_permission(request, doc)
        if err:
            return err
        # 更新本地 DB
        if "category_l1_id" in request.data:
            tag_l1_id = request.data["category_l1_id"]
            doc.category_l1 = Tag.objects.filter(pk=tag_l1_id).first() if tag_l1_id else None
        if "category_l2_id" in request.data:
            tag_l2_id = request.data["category_l2_id"]
            doc.category_l2 = Tag.objects.filter(pk=tag_l2_id).first() if tag_l2_id else None
        if "file_name" in request.data:
            doc.file_name = request.data["file_name"]
        doc.save()
        # 同步到 ai-service（ES 分块的 metadata，传标签 ID）
        ai_data = dict(request.data)
        if doc.category_l1:
            ai_data["category_l1"] = doc.category_l1.id
        if doc.category_l2:
            ai_data["category_l2"] = doc.category_l2.id
        if doc.kb.department:
            ai_data["department"] = doc.kb.department.name
        _proxy("put", f"/api/kb/documents/{doc_id}/metadata", json_data=ai_data)
        return Response({"message": "已更新"})


# ════════════════════════════════════════════════════════════════
#  分块管理 (代理 ai-service)
# ════════════════════════════════════════════════════════════════

class ChunkListView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        data = _proxy("get", "/api/kb/chunks", params=request.query_params)
        return Response(data)


class ChunkDetailView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request, chunk_id):
        data = _proxy("get", f"/api/kb/chunks/{chunk_id}")
        return Response(data)

    def put(self, request, chunk_id):
        data = _proxy("put", f"/api/kb/chunks/{chunk_id}", json_data=request.data)
        return Response(data)

    def delete(self, request, chunk_id):
        data = _proxy("delete", f"/api/kb/chunks/{chunk_id}", params=request.query_params)
        return Response(data)


class ChunkEnableView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request, chunk_id):
        data = _proxy("post", f"/api/kb/chunks/{chunk_id}/enable")
        return Response(data)


class ChunkDisableView(APIView):
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def post(self, request, chunk_id):
        data = _proxy("post", f"/api/kb/chunks/{chunk_id}/disable")
        return Response(data)


# ════════════════════════════════════════════════════════════════
#  任务状态 & 标签
# ════════════════════════════════════════════════════════════════

class TaskStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        # 优先查本地 Document 状态
        doc = Document.objects.filter(task_id=task_id).first()
        if doc:
            # 同时查 ai-service 获取实时进度
            try:
                ai_data = _proxy("get", f"/api/kb/tasks/{task_id}")
                # 如果完成，更新本地状态
                if ai_data.get("status") == "SUCCESS" and doc.status != "completed":
                    doc.status = "completed"
                    doc.save()
                elif ai_data.get("status") == "FAILURE" and doc.status != "failed":
                    doc.status = "failed"
                    doc.save()
                return Response(ai_data)
            except Exception:
                pass
            return Response({
                "task_id": task_id,
                "status": "COMPLETED" if doc.status == "completed" else "PROCESSING",
                "progress": 100 if doc.status == "completed" else 0,
                "message": doc.status,
            })
        # fallback：直接代理
        data = _proxy("get", f"/api/kb/tasks/{task_id}")
        return Response(data)


class TagListView(APIView):
    """标签列表（暂返回空，后续实现）"""
    permission_classes = [IsAuthenticated, IsDeptAdmin]

    def get(self, request):
        return Response({"tags": []})


class DocumentReprocessView(APIView):
    """重新处理文档 — 从 MinIO 重新读取并写入 ES（用于 ES 数据丢失后恢复）"""
    permission_classes = [IsAuthenticated, IsSysAdmin]

    def post(self, request):
        docs = Document.objects.select_related("kb", "category_l1", "category_l2").all()

        submitted, skipped, errors = [], [], []
        for doc in docs:
            if not doc.minio_path:
                skipped.append(doc.doc_id)
                continue

            kb = doc.kb
            department_name = kb.department.name if kb and kb.department else ""
            cat_l1 = doc.category_l1.id if doc.category_l1 else None
            cat_l2 = doc.category_l2.id if doc.category_l2 else None

            try:
                process_data = _proxy(
                    "post",
                    "/api/kb/upload",
                    json_data={
                        "minio_path": doc.minio_path,
                        "file_name": doc.file_name,
                        "department": department_name,
                        "category_l1": cat_l1,
                        "category_l2": cat_l2,
                    },
                )
                doc.task_id = process_data.get("task_id", "")
                doc.status = "processing"
                doc.save()
                submitted.append(doc.doc_id)
            except Exception as e:
                errors.append({"doc_id": doc.doc_id, "error": str(e)})

        return Response({
            "submitted": len(submitted),
            "skipped": len(skipped),
            "errors": errors,
            "detail": f"已提交 {len(submitted)} 个文档重新处理",
        })


class DocumentStatusCallbackView(APIView):
    """内部接口：ai-service Celery 任务完成后回调更新文档状态"""
    authentication_classes = []
    permission_classes = []

    def post(self, request, doc_id):
        status = request.data.get("status", "completed")
        doc = Document.objects.filter(doc_id=doc_id).first()
        if not doc:
            return Response({"error": "not found"}, status=404)
        doc.status = status
        doc.save(update_fields=["status", "updated_at"])
        return Response({"doc_id": doc_id, "status": status})


class KnowledgeBaseImageView(APIView):
    """知识库图片代理（支持 ?token= query 参数认证，用于 img src）"""

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD"):
            raw_token = self.request.query_params.get("token", "")
            if raw_token:
                return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, path):
        # query token 认证（img src 无法发送 Header）
        raw_token = request.query_params.get("token", "")
        if raw_token:
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                from users.models import User

                access_token = AccessToken(raw_token)
                User.objects.get(id=access_token["user_id"], is_active=True)
            except Exception:
                return HttpResponse(status=401)
        # else: 标准 Header JWT，DRF permission 已处理

        try:
            client = get_minio_client()
            resp = client.get_object(settings.MINIO_BUCKET, path)
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            data = resp.read()
            resp.close()
            resp.release_conn()
            return HttpResponse(data, content_type=content_type)
        except Exception:
            return HttpResponse(status=404)
