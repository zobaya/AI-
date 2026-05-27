"""AI Service 客户端 — 调用 FastAPI ai-service"""
import requests
from django.conf import settings


class AIServiceClient:
    BASE = settings.AI_SERVICE_BASE_URL

    @classmethod
    def upload_file(cls, files_list):
        """上传文件到 ai-service，返回 (paths, names)"""
        files = [("files", (f.name, f.read(), f.content_type)) for f in files_list]
        resp = requests.post(f"{cls.BASE}/agent/api/upload", files=files, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get("paths", []), data.get("names", [])

    @classmethod
    def stream_chat(cls, payload):
        """流式请求 ai-service，逐行 yield SSE 文本"""
        resp = requests.post(
            f"{cls.BASE}/agent/api/chat",
            json=payload,
            stream=True,
            timeout=600,
        )
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                yield line

    @classmethod
    def get_allowed_kb_ids(cls, user):
        """获取用户有权访问的知识库 ID 列表（仅显式授权）"""
        from users.models import UserKBPermission

        if user.role == "sys_admin":
            return None  # 全部

        kb_ids = list(
            UserKBPermission.objects.filter(user=user).values_list(
                "knowledge_base__kb_id", flat=True
            )
        )
        return kb_ids
