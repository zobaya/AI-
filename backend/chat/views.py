"""Chat 模块 Views — 会话管理 & SSE 流式代理"""
import json
from io import BytesIO
from urllib.parse import quote
from django.http import StreamingHttpResponse, FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.db import models as db_models
from django.db.models import Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Conversation, ConversationFolder, Message, MessageAttachment, PromptLibrary, UserMemory, GeneratedFile
from .serializers import (
    ConversationFolderSerializer,
    ConversationListSerializer,
    ConversationDetailSerializer,
    MessageSerializer,
    ChatSendSerializer,
    PromptLibrarySerializer,
    UserMemorySerializer,
    MemoryBatchWriteSerializer,
)
from .services import AIServiceClient
from rest_framework_simplejwt.authentication import JWTAuthentication
from .auth import ServiceTokenAuthentication


# ── 会话文件夹 ──────────────────────────────────────────────────

class FolderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        folders = ConversationFolder.objects.filter(user=request.user)
        data = []
        for f in folders:
            d = ConversationFolderSerializer(f).data
            d["conversation_count"] = f.conversations.count()
            data.append(d)
        return Response(data)

    def post(self, request):
        ser = ConversationFolderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        folder = ConversationFolder.objects.create(user=request.user, **ser.validated_data)
        return Response(ConversationFolderSerializer(folder).data, status=201)


class FolderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        folder = get_object_or_404(ConversationFolder, pk=pk, user=request.user)
        if "name" in request.data:
            folder.name = request.data["name"]
        if "sort_order" in request.data:
            folder.sort_order = request.data["sort_order"]
        folder.save()
        return Response(ConversationFolderSerializer(folder).data)

    def delete(self, request, pk):
        folder = get_object_or_404(ConversationFolder, pk=pk, user=request.user)
        folder.delete()
        return Response({"message": "已删除"})


# ── 会话管理 ────────────────────────────────────────────────────

class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.query_params.get("user_id")
        if user_id and request.user.role in ("dept_admin", "sys_admin"):
            qs = Conversation.objects.filter(user_id=user_id).select_related("folder")
        else:
            qs = Conversation.objects.filter(user=request.user).select_related("folder")

        folder_id = request.query_params.get("folder_id")
        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(messages__content__icontains=search)
            ).distinct()

        qs = qs.annotate(message_count=Count("messages")).order_by(
            "-is_pinned", "-updated_at"
        )
        return Response(ConversationListSerializer(qs, many=True).data)

    def post(self, request):
        conv = Conversation.objects.create(
            user=request.user,
            folder_id=request.data.get("folder_id"),
            title=request.data.get("title", "新对话"),
        )
        return Response(ConversationListSerializer(conv).data, status=201)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if request.user.role in ("dept_admin", "sys_admin"):
            conv = get_object_or_404(Conversation, pk=pk)
        else:
            conv = get_object_or_404(Conversation, pk=pk, user=request.user)
        return Response(ConversationDetailSerializer(conv).data)

    def patch(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, user=request.user)
        if "title" in request.data:
            conv.title = request.data["title"]
        if "folder_id" in request.data:
            conv.folder_id = request.data["folder_id"]
        if "is_pinned" in request.data:
            conv.is_pinned = request.data["is_pinned"]
        conv.save()
        return Response(ConversationListSerializer(conv).data)

    def delete(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, user=request.user)
        conv.delete()
        return Response({"message": "已删除"})


# ── 会话导出 ──────────────────────────────────────────────────


class ConversationExportView(APIView):
    """导出会话为 PDF / DOCX / TXT"""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        fmt = request.query_params.get("export_format", "pdf").lower()
        if fmt not in ("pdf", "docx", "txt"):
            return Response({"error": "不支持的格式"}, status=400)

        # 权限：所有者或管理员
        if request.user.role in ("dept_admin", "sys_admin"):
            conv = get_object_or_404(Conversation, pk=pk)
        else:
            conv = get_object_or_404(Conversation, pk=pk, user=request.user)

        messages = list(conv.messages.all())

        from .export import generate_txt, generate_pdf, generate_docx

        if fmt == "pdf":
            data = generate_pdf(conv, messages)
            content_type = "application/pdf"
        elif fmt == "docx":
            data = generate_docx(conv, messages)
            content_type = (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            )
        else:
            data = generate_txt(conv, messages)
            content_type = "text/plain; charset=utf-8"

        ext = fmt
        filename = f"{conv.title}.{ext}"
        encoded_filename = quote(filename)

        resp = HttpResponse(data, content_type=content_type)
        resp["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{encoded_filename}"
        )
        return resp


# ── 消息截断（重新生成 / 编辑重发）──────────────────────────────


class MessageTruncateView(APIView):
    """删除指定消息及其后续所有消息，用于重新生成和编辑重发"""

    permission_classes = [IsAuthenticated]

    def delete(self, request, conv_id):
        conv = get_object_or_404(Conversation, pk=conv_id, user=request.user)
        from_message_id = request.data.get("from_message_id")
        if not from_message_id:
            return Response({"error": "缺少 from_message_id"}, status=400)

        # 验证目标消息属于该会话
        get_object_or_404(Message, pk=from_message_id, conversation=conv)

        deleted_count, _ = Message.objects.filter(
            conversation=conv, id__gte=from_message_id
        ).delete()
        return Response({"deleted_count": deleted_count})


# ── 消息反馈 ────────────────────────────────────────────────────

class MessageFeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, conversation__user=request.user)
        feedback = request.data.get("feedback")
        if feedback not in ("like", "dislike"):
            return Response({"error": "反馈类型无效"}, status=400)

        detail = request.data.get("feedback_detail")

        # 再次点击同一个反馈且无详情 → 取消（清除记录）
        # 有 feedback_detail 时视为更新操作，不触发 toggle
        if msg.feedback == feedback and detail is None:
            msg.feedback = None
            msg.feedback_detail = None
            msg.save()
            return Response({"message": "反馈已取消"})

        msg.feedback = feedback

        # 保存反馈详情
        if detail and isinstance(detail, dict):
            reasons = detail.get("reasons", [])
            comment = detail.get("comment", "")
            if reasons or comment:
                msg.feedback_detail = detail
            else:
                msg.feedback_detail = None
        else:
            msg.feedback_detail = None

        msg.save()
        return Response({"message": "反馈已记录"})


# ── SSE 流式聊天代理 ────────────────────────────────────────────

class ChatSendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        # 获取或创建会话
        if data.get("conversation_id"):
            conv = get_object_or_404(Conversation, pk=data["conversation_id"], user=user)
        else:
            conv = Conversation.objects.create(user=request.user)

        # 保存用户消息
        user_msg = Message.objects.create(
            conversation=conv,
            role="user",
            content=data["query"],
        )

        # 创建附件记录
        file_paths = data.get("file_paths", [])
        file_names = data.get("file_names", [])
        for i, path in enumerate(file_paths):
            name = file_names[i] if i < len(file_names) else path.split("/")[-1]
            MessageAttachment.objects.create(
                message=user_msg,
                file_name=name,
                file_path_minio=path,
            )

        # 构建历史上下文（排除刚保存的当前消息）
        prev_messages = list(conv.messages.order_by("created_at"))
        history = [{"role": m.role, "content": m.content} for m in prev_messages[:-1]]

        # 获取知识库权限
        kb_ids = AIServiceClient.get_allowed_kb_ids(user)

        # 构建 AI 服务请求
        ai_payload = {
            "user_query": data["query"],
            "history": history,
            "user_id": user.id,
            "conversation_id": conv.id,
        }
        if file_paths:
            ai_payload["minio_paths"] = file_paths
        if file_names:
            ai_payload["file_names"] = file_names
        if data.get("allowed_tools"):
            ai_payload["allowed_tools"] = data["allowed_tools"]
        if kb_ids is not None:
            ai_payload["kb_ids"] = kb_ids

        response = StreamingHttpResponse(
            self._generate(conv, ai_payload),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Conversation-Id"] = str(conv.id)
        return response

    def _generate(self, conversation, payload):
        """流式生成 SSE，同时收集 entries 并保存回答到数据库

        ReAct Agent 可能多轮循环（agent ⇄ tools），每轮都可能产生独立的 think 阶段。
        因此 think buffer 在遇到非 think 事件时立即 flush 为独立 entry，
        而非等流结束后一次性聚合。
        """
        full_answer = ""
        current_event = ""
        workflow_id = ""
        think_buffer = ""
        entries = []
        tokens_used = 0

        for line in AIServiceClient.stream_chat(payload):
            yield line + "\n"

            if line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    event_data = json.loads(line[6:])
                except (json.JSONDecodeError, IndexError):
                    continue

                # 收集 workflow_id
                if current_event == "workflow_id":
                    workflow_id = event_data.get("workflow_id", "")

                # think 逐 Token 累积到 buffer
                if current_event == "think":
                    think_buffer += event_data.get("content", "")
                else:
                    # 遇到非 think 事件 → 立即 flush 已累积的 think 为独立 entry
                    if think_buffer:
                        entries.append({"event": "think", "content": think_buffer})
                        think_buffer = ""

                    # 收集结构化事件
                    if current_event in ("progress", "title", "maybe", "error"):
                        entries.append({"event": current_event, **event_data})

                if current_event == "output":
                    full_answer += event_data.get("content", "")
                elif current_event == "title":
                    title = event_data.get("content", "").strip()
                    if title and conversation.title == "新对话":
                        conversation.title = title
                        conversation.save()
                elif current_event == "token_usage":
                    tokens_used = event_data.get("prompt_tokens", 0) + event_data.get("completion_tokens", 0)

        # flush 最后的 think buffer（如果流以 think 结尾）
        if think_buffer:
            entries.append({"event": "think", "content": think_buffer})

        # 保存 AI 回答（含 workflow_id、token 使用量和完整 entries）
        if full_answer.strip():
            Message.objects.create(
                conversation=conversation,
                role="assistant",
                content=full_answer.strip(),
                workflow_id=workflow_id,
                metadata_json={"entries": entries} if entries else {},
                tokens_used=tokens_used,
            )
            # 更新会话 updated_at，使侧边栏时间分组正确反映最新消息时间
            conversation.save()


# ── 文件上传代理 ────────────────────────────────────────────────

class FileUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            return Response({"error": "请选择文件"}, status=400)
        try:
            paths, names = AIServiceClient.upload_file(files)
            return Response({"paths": paths, "names": names})
        except Exception as e:
            return Response({"error": f"上传失败: {e}"}, status=500)


# ── 快捷提示词 ──────────────────────────────────────────────────

class PromptLibraryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PromptLibrary.objects.filter(
            is_system=True
        ) | PromptLibrary.objects.filter(
            owner=request.user, is_system=False
        )
        return Response(PromptLibrarySerializer(qs, many=True).data)

    def post(self, request):
        ser = PromptLibrarySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prompt = PromptLibrary.objects.create(
            owner=request.user,
            is_system=False,
            **ser.validated_data,
        )
        return Response(PromptLibrarySerializer(prompt).data, status=201)


class PromptLibraryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        prompt = get_object_or_404(PromptLibrary, pk=pk, owner=request.user, is_system=False)
        prompt.title = request.data.get("title", prompt.title)
        prompt.content = request.data.get("content", prompt.content)
        prompt.save()
        return Response(PromptLibrarySerializer(prompt).data)

    def delete(self, request, pk):
        prompt = get_object_or_404(PromptLibrary, pk=pk, owner=request.user, is_system=False)
        prompt.delete()
        return Response({"message": "已删除"})


# ── 用户记忆 ──────────────────────────────────────────────────────

class UserMemoryListView(APIView):
    """获取当前用户的高置信度记忆（支持 JWT 和 Service Token 双认证）"""
    authentication_classes = [JWTAuthentication, ServiceTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        limit = int(request.query_params.get("limit", 15))
        agent_name = request.query_params.get("agent_name", "default")

        memories = list(UserMemory.objects.filter(
            user=user,
            agent_name=agent_name,
            confidence__gte=0.5,
        ).order_by("-confidence", "-updated_at")[:limit])

        # 更新访问计数
        if memories:
            UserMemory.objects.filter(
                pk__in=[m.pk for m in memories]
            ).update(access_count=db_models.F("access_count") + 1)

        return Response({
            "facts": UserMemorySerializer(memories, many=True).data,
        })


class UserMemoryBatchView(APIView):
    """批量写入/更新/删除记忆（ai-service 调用，支持 JWT 和 Service Token 双认证）"""
    authentication_classes = [JWTAuthentication, ServiceTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MemoryBatchWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        agent_name = data["agent_name"]
        conversation_id = data.get("conversation_id")
        facts = data.get("facts", [])

        created = []
        for fact_data in facts:
            fact_text = fact_data.get("fact", "").strip()
            if not fact_text:
                continue

            memory = UserMemory.objects.create(
                user=user,
                agent_name=agent_name,
                fact=fact_text,
                category=fact_data.get("category", "context"),
                confidence=fact_data.get("confidence", 0.5),
                source_conv_id=conversation_id,
            )
            created.append(memory)

        return Response({
            "created": len(created),
            "facts": UserMemorySerializer(created, many=True).data,
        }, status=201)

    def delete(self, request):
        """批量删除记忆"""
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"deleted": 0})
        deleted = UserMemory.objects.filter(
            user=request.user,
            id__in=ids,
        ).delete()[0]
        return Response({"deleted": deleted})


class UserMemoryDetailView(APIView):
    """单条记忆的查看/更新/删除（支持 JWT 和 Service Token 双认证）"""
    authentication_classes = [JWTAuthentication, ServiceTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        memory = get_object_or_404(UserMemory, pk=pk, user=request.user)
        return Response(UserMemorySerializer(memory).data)

    def put(self, request, pk):
        memory = get_object_or_404(UserMemory, pk=pk, user=request.user)
        if "fact" in request.data:
            memory.fact = request.data["fact"]
        if "category" in request.data:
            memory.category = request.data["category"]
        if "confidence" in request.data:
            memory.confidence = request.data["confidence"]
        memory.save()
        return Response(UserMemorySerializer(memory).data)

    def delete(self, request, pk):
        memory = get_object_or_404(UserMemory, pk=pk, user=request.user)
        memory.delete()
        return Response({"message": "已删除"})


# ── AI 生成文件下载 ──────────────────────────────────────────────


class FileDownloadView(APIView):
    """AI 生成文件下载 — 通过 file_id 下载，校验归属（JWT 认证）"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # 查找文件记录，校验归属
        gen_file = get_object_or_404(GeneratedFile, pk=pk, user=request.user)

        try:
            from knowledge.minio_client import get_minio_client

            client = get_minio_client()
            minio_path = gen_file.minio_path
            parts = minio_path.split("/", 1)
            if len(parts) != 2:
                return Response({"error": "路径格式错误"}, status=400)
            bucket_name, object_name = parts

            response = client.get_object(bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()

            content_types = {
                "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "pdf": "application/pdf",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            return FileResponse(
                BytesIO(data),
                as_attachment=True,
                filename=gen_file.file_name,
                content_type=content_types.get(gen_file.file_type, "application/octet-stream"),
            )
        except Exception as e:
            return Response({"error": f"文件下载失败：{e}"}, status=500)


class GeneratedFileListView(APIView):
    """AI 生成文件列表 — 当前用户的文件（JWT 认证）"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        files = GeneratedFile.objects.filter(user=request.user).order_by("-created_at")

        # 可选过滤：file_type
        file_type = request.query_params.get("file_type")
        if file_type:
            files = files.filter(file_type=file_type)

        data = [
            {
                "id": f.id,
                "file_name": f.file_name,
                "file_size": f.file_size,
                "file_type": f.file_type,
                "slide_count": f.slide_count,
                "theme": f.theme,
                "conversation_id": f.conversation_id,
                "created_at": f.created_at.isoformat(),
            }
            for f in files[:50]  # 最多返回 50 条
        ]
        return Response({"files": data})

    def delete(self, request):
        """删除指定文件（仅限本人）"""
        file_id = request.data.get("id")
        if not file_id:
            return Response({"error": "缺少 id"}, status=400)

        gen_file = get_object_or_404(GeneratedFile, pk=file_id, user=request.user)

        # 从 MinIO 删除
        try:
            from knowledge.minio_client import get_minio_client

            client = get_minio_client()
            minio_path = gen_file.minio_path
            parts = minio_path.split("/", 1)
            if len(parts) == 2:
                client.remove_object(parts[0], parts[1])
        except Exception as e:
            # MinIO 删除失败不影响 DB 删除
            import logging
            logging.getLogger(__name__).warning(f"MinIO 删除失败: {e}")

        gen_file.delete()
        return Response({"message": "已删除"})


class GeneratedFileCreateView(APIView):
    """AI 生成文件记录创建 — 仅供 ai-service 内部调用（Service Token 认证）"""
    authentication_classes = [JWTAuthentication, ServiceTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        file_name = request.data.get("file_name", "")
        minio_path = request.data.get("minio_path", "")
        file_size = request.data.get("file_size", 0)
        file_type = request.data.get("file_type", "pptx")
        slide_count = request.data.get("slide_count", 0)
        theme = request.data.get("theme", "")
        conversation_id = request.data.get("conversation_id")

        if not file_name or not minio_path:
            return Response({"error": "缺少 file_name 或 minio_path"}, status=400)

        gen_file = GeneratedFile.objects.create(
            user=user,
            conversation_id=conversation_id,
            file_name=file_name,
            minio_path=minio_path,
            file_size=file_size,
            file_type=file_type,
            slide_count=slide_count,
            theme=theme,
        )

        return Response({
            "id": gen_file.id,
            "file_name": gen_file.file_name,
            "created_at": gen_file.created_at.isoformat(),
        }, status=201)
