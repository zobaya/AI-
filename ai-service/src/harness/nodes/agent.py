"""
主 Agent 决策节点

职责：流式调用 LLM，处理 thinking/output/tool_call，
收集结果并通过 SSE 事件推送。
"""
import json
import logging
import re
from typing import Dict, Any, List

from langchain_core.messages import AIMessage
from langchain_core.callbacks.manager import adispatch_custom_event

from src.harness.llm import stream_chat_with_tools
from src.harness.tools.registry import ToolRegistry
from src.harness.prompts import build_system_prompt
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)


async def agent_node(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    主 Agent 节点：流式调用 LLM 决策下一步。

    处理流程：
    1. 构建 LLM 输入（system prompt + history + messages）
    2. 流式调用，逐 token 解析 thinking / output / tool_call
    3. 有 tool_calls → 返回 AIMessage 给 tool_node
    4. 无 tool_calls → 返回最终回答
    """
    messages = state.get("messages", [])

    # 构建 LLM 输入
    llm_messages = _build_llm_messages(state, messages)

    # 发送进度事件
    await adispatch_custom_event(
        "progress",
        {"node": "agent", "message": "正在分析问题..."},
        config=config,
    )

    # 根据权限过滤可用工具
    allowed = state.get("allowed_tools")
    tools_schema = ToolRegistry.get_schemas(allowed_tools=allowed)

    full_thinking = ""
    full_content = ""
    collected_tool_calls: List[Dict[str, Any]] = []

    # 用于解析 <think\n> 标签的状态机
    text_buffer = ""
    in_think = False

    # Token 使用量累计
    turn_prompt_tokens = 0
    turn_completion_tokens = 0

    async for chunk in stream_chat_with_tools(
        messages=llm_messages,
        tools=tools_schema,
        temperature=0.7,
    ):
        chunk_type = chunk.get("type")

        if chunk_type == "usage":
            turn_prompt_tokens += chunk.get("prompt_tokens", 0)
            turn_completion_tokens += chunk.get("completion_tokens", 0)
            continue

        if chunk_type == "thinking":
            piece = chunk.get("content", "")
            full_thinking += piece
            await adispatch_custom_event(
                "think",
                {"node": "agent", "content": piece},
                config=config,
            )

        elif chunk_type == "text":
            text_buffer += chunk.get("content", "")
            while True:
                if in_think:
                    close_match = re.search(r"</think\n?>", text_buffer)
                    if close_match:
                        think_piece = text_buffer[:close_match.start()]
                        if think_piece:
                            full_thinking += think_piece
                            await adispatch_custom_event(
                                "think",
                                {"node": "agent", "content": think_piece},
                                config=config,
                            )
                        text_buffer = text_buffer[close_match.end():]
                        in_think = False
                    else:
                        if text_buffer:
                            full_thinking += text_buffer
                            await adispatch_custom_event(
                                "think",
                                {"node": "agent", "content": text_buffer},
                                config=config,
                            )
                            text_buffer = ""
                        break
                else:
                    open_match = re.search(r"<think\n?>", text_buffer)
                    if open_match:
                        before = text_buffer[:open_match.start()]
                        if before:
                            full_content += before
                            await adispatch_custom_event("output", {"content": before}, config=config)
                        text_buffer = text_buffer[open_match.end():]
                        in_think = True
                    else:
                        if text_buffer:
                            full_content += text_buffer
                            await adispatch_custom_event("output", {"content": text_buffer}, config=config)
                            text_buffer = ""
                        break

        elif chunk_type == "tool_call":
            collected_tool_calls.append({
                "id": chunk.get("id", ""),
                "name": chunk.get("name", ""),
                "arguments": chunk.get("arguments", {}),
            })

        elif chunk_type == "done":
            if text_buffer:
                if in_think:
                    full_thinking += text_buffer
                    await adispatch_custom_event(
                        "think",
                        {"node": "agent", "content": text_buffer},
                        config=config,
                    )
                else:
                    full_content += text_buffer
                    await adispatch_custom_event("output", {"content": text_buffer}, config=config)
                text_buffer = ""
            break

    # 有 tool_calls → 返回 AIMessage 给 tool_node
    if collected_tool_calls:
        ai_msg = AIMessage(
            content=full_content or "",
            tool_calls=[
                {"id": tc["id"], "name": tc["name"], "args": tc["arguments"]}
                for tc in collected_tool_calls
            ],
        )
        tool_names = [tc["name"] for tc in collected_tool_calls]
        await adispatch_custom_event(
            "progress",
            {"node": "agent", "message": f"调用工具：{', '.join(tool_names)}"},
            config=config,
        )
        return {
            "messages": [ai_msg],
            "tool_calls_count": state.get("tool_calls_count", 0) + len(collected_tool_calls),
            "token_usage": _accumulate_tokens(state, turn_prompt_tokens, turn_completion_tokens),
        }

    # 无 tool_calls → 返回回答内容
    return {
        "messages": [AIMessage(content=full_content or "")],
        "output": full_content,
        "token_usage": _accumulate_tokens(state, turn_prompt_tokens, turn_completion_tokens),
    }


# ========== 辅助函数 ==========


def _build_llm_messages(
    state: Dict[str, Any],
    messages: List[BaseMessage],
) -> List[Dict[str, Any]]:
    """构建 LLM 输入的 messages 列表"""
    system_content = build_system_prompt(
        allowed_tools=state.get("allowed_tools"),
        memory_facts=state.get("memory_facts"),
    )

    # 文件列表仅在 file_parse 可用时追加
    allowed_tools = state.get("allowed_tools")
    file_parse_allowed = allowed_tools is None or "file_parse" in (allowed_tools or [])
    minio_paths = state.get("minio_paths")
    if minio_paths and file_parse_allowed:
        file_names = state.get("file_names")
        file_list = []
        for i, p in enumerate(minio_paths):
            name = file_names[i] if file_names and i < len(file_names) else p.split("/")[-1]
            file_list.append(f"  - {name}")
        system_content += (
            f"\n\n## 当前可用文件\n\n"
            f"用户已上传以下文件，你可以使用 file_parse 工具解析它们（传入文件名即可）：\n"
            + "\n".join(file_list)
            + "\n\n注意：只有当用户的问题需要读取文件内容时才调用 file_parse。"
            "如果用户只是闲聊或不涉及文件内容，不需要调用。"
        )

    result = [{"role": "system", "content": system_content}]

    # 添加历史对话
    history = state.get("history", [])
    if history:
        for h in history[-10:]:
            result.append(h)

    # 添加当前对话链
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                result.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
            else:
                result.append({"role": "assistant", "content": str(msg.content)})
        elif isinstance(msg, ToolMessage):
            result.append({
                "role": "tool",
                "content": str(msg.content),
                "tool_call_id": msg.tool_call_id,
            })

    return result


def _accumulate_tokens(
    state: Dict[str, Any],
    turn_prompt: int,
    turn_completion: int,
) -> Dict[str, int]:
    """累加当前轮次的 token 使用量到 state 中的 token_usage"""
    prev = state.get("token_usage") or {}
    return {
        "prompt_tokens": (prev.get("prompt_tokens") or 0) + turn_prompt,
        "completion_tokens": (prev.get("completion_tokens") or 0) + turn_completion,
    }
