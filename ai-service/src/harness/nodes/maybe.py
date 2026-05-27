"""
标题 + 推荐问题节点

职责：根据用户提问和助手回答，生成标题和推荐问题。
使用 no_think 模式快速调用 LLM。
"""
from typing import Dict, Any

from langchain_core.callbacks.manager import adispatch_custom_event

from src.harness.llm import generate_maybe_questions


async def maybe_node(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    标题+推荐问题节点：根据对话生成标题和推荐问题。
    """
    await adispatch_custom_event(
        "progress",
        {"node": "maybe", "message": "生成推荐问题..."},
        config=config,
    )

    user_query = state.get("user_query", "")
    output = state.get("output", "")

    result = await generate_maybe_questions(user_query, output or "")

    # 仅首次对话生成标题（history 为空表示第一条消息）
    history = state.get("history") or []
    if not history:
        title = result.get("title")
        if title:
            await adispatch_custom_event("title", {"content": title}, config=config)

    # 发送推荐问题
    questions = result.get("questions", [])
    if questions:
        await adispatch_custom_event(
            "maybe",
            {"questions": questions[:3]},
            config=config,
        )

    return {}
