"""
记忆中间件

职责：
1. before_node(agent): 加载高置信度事实注入 state["memory_facts"]
2. after_node(agent): 异步防抖抽取新事实（不阻塞响应）
"""
import asyncio
import logging
from typing import Any, Dict

from src.harness.middlewares.base import AgentMiddleware
from src.harness.memory.storage import DjangoMemoryStorage
from src.harness.memory.updater import MemoryUpdater, filter_messages_for_memory

logger = logging.getLogger(__name__)


class MemoryMiddleware(AgentMiddleware):
    """
    记忆中间件：对话前注入记忆，对话后异步抽取新事实。

    执行流程：
    - before_node("agent"): 从存储加载高置信度事实 → state["memory_facts"]
    - after_node("agent"): 如果 agent 产生了最终回答（output），异步抽取事实
    """

    name = "memory"

    def __init__(
        self,
        storage: DjangoMemoryStorage | None = None,
        debounce_delay: int = 30,
    ):
        self.storage = storage or DjangoMemoryStorage()
        self.updater = MemoryUpdater(self.storage)
        self.debounce_delay = debounce_delay

    async def before_node(
        self, node_name: str, state: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对话前注入记忆"""
        # 只在 agent 节点注入
        if node_name != "agent":
            return state

        user_id = config.get("configurable", {}).get("user_id")
        if not user_id:
            return state

        try:
            facts = await self.storage.load_facts(user_id, agent_name="default", limit=15)
            if facts:
                state["memory_facts"] = facts
                logger.info(f"[MemoryMiddleware] Loaded {len(facts)} facts for user={user_id}")
        except Exception as e:
            logger.warning(f"[MemoryMiddleware] Failed to load facts: {e}")

        return state

    async def after_node(
        self,
        node_name: str,
        state: Dict[str, Any],
        result: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """对话后异步抽取事实（防抖）"""
        # 只在 agent 节点且有最终回答时触发
        if node_name != "agent":
            return result

        # 只在有最终输出（非工具调用轮）时抽取
        if not result.get("output"):
            return result

        user_id = config.get("configurable", {}).get("user_id")
        if not user_id:
            return result

        # 异步提交（不阻塞响应）
        messages = state.get("messages", [])
        filtered = filter_messages_for_memory(messages)

        if len(filtered) >= 2:  # 至少有一问一答
            asyncio.create_task(
                self._debounced_update(
                    user_id, filtered,
                    conversation_id=config.get("configurable", {}).get("conversation_id"),
                )
            )

        return result

    async def _debounced_update(
        self,
        user_id: int,
        messages: list,
        conversation_id: int | None = None,
    ):
        """防抖更新：等待一段时间后执行"""
        try:
            await asyncio.sleep(self.debounce_delay)
            await self.updater.update_from_conversation(
                user_id=user_id,
                messages=messages,
                agent_name="default",
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.error(f"[MemoryMiddleware] Debounced update failed: {e}")
