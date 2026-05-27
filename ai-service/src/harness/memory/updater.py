"""
记忆更新器

使用 LLM 从对话中抽取事实，并通过存储层持久化。
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional

from .storage import MemoryStorage
from .prompt import build_extraction_prompt

logger = logging.getLogger(__name__)


class MemoryUpdater:
    """使用 LLM 从对话中抽取事实并更新记忆"""

    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    async def update_from_conversation(
        self,
        user_id: int,
        messages: List[Dict[str, str]],
        agent_name: str = "default",
        conversation_id: Optional[int] = None,
    ):
        """
        从一次对话中抽取事实并持久化。

        流程：
        1. 加载现有记忆作为上下文
        2. 构建事实抽取 Prompt
        3. 调用 LLM（no_think 模式，低成本）
        4. 解析 LLM 返回的 JSON
        5. 通过存储层写入

        Args:
            user_id: 用户 ID
            messages: [{"role": "user/assistant", "content": "..."}]
            agent_name: Agent 标识
            conversation_id: 来源会话 ID
        """
        try:
            # 1. 加载现有记忆
            existing_facts = await self.storage.load_facts(
                user_id, agent_name, limit=30
            )

            # 2. 构建 Prompt
            llm_messages = build_extraction_prompt(messages, existing_facts)

            # 3. 调用 LLM（no_think 模式）
            response_text = await self._call_llm(llm_messages)
            if not response_text:
                return

            # 4. 解析结果
            updates = self._parse_response(response_text)

            # 5. 持久化
            facts_to_add = updates.get("add", [])
            ids_to_delete = updates.get("delete", [])

            if facts_to_add:
                saved = await self.storage.save_facts(
                    user_id, facts_to_add, agent_name, conversation_id
                )
                logger.info(
                    f"[MemoryUpdater] Saved {saved} facts for user={user_id}"
                )

            if ids_to_delete:
                deleted = await self.storage.delete_facts(user_id, ids_to_delete)
                logger.info(
                    f"[MemoryUpdater] Deleted {deleted} facts for user={user_id}"
                )

        except Exception as e:
            logger.error(f"[MemoryUpdater] update_from_conversation failed: {e}")

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """调用 LLM 进行事实抽取（no_think 模式）"""
        try:
            from src.harness.llm import get_llm_client
            from core.config import settings

            client = get_llm_client()
            response = await client.chat.completions.create(
                model=settings.VLLM_MODEL_NAME,
                messages=messages,
                stream=False,
                temperature=0.3,
                max_tokens=1024,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            content = response.choices[0].message.content
            if content:
                # 清理可能残留的 think 标签
                cleaned = re.sub(
                    r"<think[^>]*>.*?</think[^>]*>", "", content, flags=re.S
                ).strip()
                return cleaned
            return None

        except Exception as e:
            logger.error(f"[MemoryUpdater] LLM call failed: {e}")
            return None

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的 JSON。

        预期格式：
        {
            "add": [{"fact": "...", "category": "...", "confidence": 0.9}],
            "delete": [1, 2, 3]
        }
        """
        try:
            # 尝试提取 JSON 块
            json_match = re.search(r"```json\s*(.*?)\s*```", text, re.S)
            if json_match:
                text = json_match.group(1)
            else:
                # 尝试直接解析
                json_match = re.search(r"\{.*\}", text, re.S)
                if json_match:
                    text = json_match.group(0)

            result = json.loads(text)

            # 校验格式
            if not isinstance(result, dict):
                return {"add": [], "delete": []}

            add = result.get("add", [])
            delete = result.get("delete", [])

            # 过滤无效条目
            valid_add = []
            for item in add:
                if isinstance(item, dict) and item.get("fact"):
                    valid_add.append({
                        "fact": str(item["fact"]).strip(),
                        "category": item.get("category", "context"),
                        "confidence": float(item.get("confidence", 0.5)),
                    })

            valid_delete = [int(d) for d in delete if isinstance(d, (int, str)) and str(d).isdigit()]

            return {"add": valid_add, "delete": valid_delete}

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[MemoryUpdater] Failed to parse LLM response: {e}")
            return {"add": [], "delete": []}


def filter_messages_for_memory(messages: list) -> List[Dict[str, str]]:
    """
    过滤消息：只保留 user + 最终 assistant 回答（避免中间工具调用干扰）。

    Args:
        messages: LangChain 消息列表

    Returns:
        [{"role": "user/assistant", "content": "..."}]
    """
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    result = []
    skip_until_next_human = False

    for msg in messages:
        if isinstance(msg, HumanMessage):
            skip_until_next_human = False
            result.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage) and not msg.tool_calls:
            if not skip_until_next_human:
                result.append({"role": "assistant", "content": str(msg.content)})
        elif isinstance(msg, ToolMessage):
            # 跳过工具消息
            skip_until_next_human = True

    return result
