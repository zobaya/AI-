"""
记忆存储层

提供存储抽象和 Django API 实现。
ai-service 通过 HTTP 调用 Django 后端的记忆 API。
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class MemoryStorage(ABC):
    """记忆存储抽象基类"""

    @abstractmethod
    async def load_facts(
        self, user_id: int, agent_name: str = "default", limit: int = 15
    ) -> List[Dict[str, Any]]:
        """
        加载高置信度事实。

        Returns:
            [{"id": 1, "fact": "...", "category": "preference", "confidence": 0.9}, ...]
        """
        ...

    @abstractmethod
    async def save_facts(
        self,
        user_id: int,
        facts: List[Dict[str, Any]],
        agent_name: str = "default",
        conversation_id: Optional[int] = None,
    ) -> int:
        """
        保存抽取的事实。

        Args:
            facts: [{"fact": "...", "category": "...", "confidence": 0.9}, ...]

        Returns:
            创建的记录数
        """
        ...

    @abstractmethod
    async def delete_facts(self, user_id: int, fact_ids: List[int]) -> int:
        """
        删除事实。

        Returns:
            删除的记录数
        """
        ...


class DjangoMemoryStorage(MemoryStorage):
    """
    通过 Django API 存储记忆到 MySQL。

    Django 端的 API 端点：
    - GET  /api/chat/memory/          — 获取高置信度记忆
    - POST /api/chat/memory/batch/    — 批量写入记忆
    - DELETE /api/chat/memory/batch/  — 批量删除记忆
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or getattr(settings, "DJANGO_API_BASE_URL", "http://localhost:8000")
        self._token: Optional[str] = None

    def _get_headers(self) -> dict:
        """获取认证 headers（使用服务间通信 token）"""
        headers = {"Content-Type": "application/json"}
        service_token = getattr(settings, "SERVICE_AUTH_TOKEN", None)
        if service_token:
            headers["Authorization"] = f"Service {service_token}"
            logger.debug(f"[MemoryStorage] Using Service token auth, token={service_token[:8]}...")
        else:
            logger.warning("[MemoryStorage] SERVICE_AUTH_TOKEN not configured, requests will fail auth")
        return headers

    async def load_facts(
        self, user_id: int, agent_name: str = "default", limit: int = 15
    ) -> List[Dict[str, Any]]:
        """加载高置信度事实"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/api/chat/memory/",
                    params={"limit": limit, "agent_name": agent_name, "user_id": user_id},
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("facts", [])
        except Exception as e:
            logger.warning(f"[MemoryStorage] load_facts failed for user={user_id}: {e}")
            return []

    async def save_facts(
        self,
        user_id: int,
        facts: List[Dict[str, Any]],
        agent_name: str = "default",
        conversation_id: Optional[int] = None,
    ) -> int:
        """批量保存事实"""
        if not facts:
            return 0

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat/memory/batch/",
                    json={
                        "facts": facts,
                        "agent_name": agent_name,
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                    },
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                return resp.json().get("created", 0)
        except Exception as e:
            logger.error(f"[MemoryStorage] save_facts failed for user={user_id}: {e}")
            return 0

    async def delete_facts(self, user_id: int, fact_ids: List[int]) -> int:
        """批量删除事实"""
        if not fact_ids:
            return 0

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"{self.base_url}/api/chat/memory/batch/",
                    json={"ids": fact_ids, "user_id": user_id},
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                return resp.json().get("deleted", 0)
        except Exception as e:
            logger.error(f"[MemoryStorage] delete_facts failed for user={user_id}: {e}")
            return 0
