"""
查询改写节点

职责：将口语化提问转为精准搜索 query。
使用 Qwen3 no_think 模式，不绑 tools，纯文本快速输出。
"""
import logging
from typing import Dict, Any

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.callbacks.manager import adispatch_custom_event

from src.harness.llm import rewrite_query

logger = logging.getLogger(__name__)


async def rewrite_node(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    查询改写节点：将口语化提问转为精准搜索 query。

    改写结果替换 messages 中最后一条 HumanMessage 的 content，
    下游 agent_node 和 es_search 工具看到的都是精准查询词。
    """
    messages = state.get("messages", [])
    history = state.get("history")

    # 发送进度
    await adispatch_custom_event(
        "progress",
        {"node": "rewrite", "message": "正在优化查询..."},
        config=config,
    )

    # 提取用户原始提问
    original_query = state.get("user_query", "")

    # 调用 no_think 改写
    rewritten = await rewrite_query(
        user_query=original_query,
        history=history,
    )

    logger.info(f"[rewrite] '{original_query}' -> '{rewritten}'")

    # 用 RemoveMessage + 新 HumanMessage 替换最后一条用户消息
    new_messages = []
    last_msg = messages[-1] if messages else None
    if last_msg and isinstance(last_msg, HumanMessage):
        new_messages.append(RemoveMessage(id=last_msg.id))
        new_messages.append(HumanMessage(content=rewritten))

    await adispatch_custom_event(
        "progress",
        {"node": "rewrite", "message": f"查询已优化: {rewritten[:60]}"},
        config=config,
    )

    return {
        "messages": new_messages,
        "standalone_query": rewritten,
    }
