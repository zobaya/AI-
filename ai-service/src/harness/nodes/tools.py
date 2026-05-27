"""
工具执行节点

职责：遍历最后一条 AIMessage 的 tool_calls，通过中间件钩子执行工具。

与原 graph.py 的区别：
- 进度事件和截断逻辑交给 ProgressMiddleware
- 死循环检测交给 LoopDetectionMiddleware
- 工具查找通过 ToolRegistry 动态获取
- 节点只负责：查找工具 → 调用中间件钩子 → 执行 → 返回 ToolMessage
"""
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, ToolMessage

from src.harness.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _find_last_ai_message(messages: List) -> AIMessage | None:
    """从 messages 中找到最后一条 AIMessage"""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg
    return None


async def tool_node(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    工具执行节点：遍历 tool_calls，通过中间件钩子执行工具。

    中间件通过 config["configurable"]["_middlewares"] 注入，
    每个工具调用经过 on_tool_call → execute → on_tool_result 三阶段。
    """
    messages = state.get("messages", [])
    last_ai_msg = _find_last_ai_message(messages)

    if not last_ai_msg or not last_ai_msg.tool_calls:
        return {"messages": []}

    # 获取中间件列表
    middlewares = config.get("configurable", {}).get("_middlewares", [])

    tool_messages: List[ToolMessage] = []

    # 记录本次调用的工具信息（用于死循环检测，保留在 state 中）
    first_tc = last_ai_msg.tool_calls[0]
    current_tool_name = first_tc["name"]
    current_tool_args = first_tc.get("args", {})

    # 计算重复调用计数
    last_tool_name = state.get("last_tool_name")
    last_tool_args = state.get("last_tool_args")
    prev_repeated = state.get("repeated_calls", 0)

    if current_tool_name == last_tool_name and current_tool_args == last_tool_args:
        new_repeated = prev_repeated + 1
    else:
        new_repeated = 1

    for tc in last_ai_msg.tool_calls:
        tool_name = tc["name"]
        tool_args = dict(tc.get("args", {}))
        tool_call_id = tc.get("id", "")

        # ---- 中间件钩子：on_tool_call ----
        result = None
        for mw in middlewares:
            intercepted = await mw.on_tool_call(tool_name, tool_args, state, config)
            if intercepted is not None:
                result = intercepted
                break

        # ---- 执行工具（如果中间件没有拦截） ----
        if result is None:
            try:
                tool = ToolRegistry.get_executor(tool_name)
                if not tool:
                    result = f"未知工具：{tool_name}"
                else:
                    # 注入 state 中的 kb_ids（仅由 API 请求传入）
                    if tool_name == "es_search":
                        kb_ids = state.get("kb_ids")
                        if kb_ids is not None:
                            tool_args["kb_ids"] = kb_ids

                    # 注入 config（用于子图内部发送进度事件）
                    tool_args["config"] = config

                    # file_parse：将文件名解析为 MinIO 路径
                    if tool_name == "file_parse":
                        file_path = tool_args.get("file_path", "")
                        minio_paths = state.get("minio_paths") or []
                        file_names_list = state.get("file_names") or []
                        for j, mp in enumerate(minio_paths):
                            clean_name = (
                                file_names_list[j]
                                if file_names_list and j < len(file_names_list)
                                else mp.split("/")[-1]
                            )
                            minio_filename = mp.split("/")[-1]
                            if file_path in (clean_name, minio_filename, mp):
                                tool_args["file_path"] = mp
                                tool_args["display_name"] = clean_name
                                logger.info(
                                    f"[tool_node] file_parse: '{file_path}' -> '{mp}' "
                                    f"(display: '{clean_name}')"
                                )
                                break

                    logger.info(f"[tool_node] Executing: {tool_name}({list(tool_args.keys())})")
                    result = await tool.execute(**tool_args)

            except Exception as e:
                logger.error(f"[tool_node] {tool_name} error: {e}")
                result = f"工具执行失败：{str(e)}"

        # ---- 中间件钩子：on_tool_result ----
        result_str = str(result)
        for mw in middlewares:
            result_str = await mw.on_tool_result(tool_name, result_str, state, config)

        tool_messages.append(
            ToolMessage(content=result_str, tool_call_id=tool_call_id)
        )

    return {
        "messages": tool_messages,
        "last_tool_name": current_tool_name,
        "last_tool_args": current_tool_args,
        "repeated_calls": new_repeated,
    }
