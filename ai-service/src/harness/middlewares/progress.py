"""
进度推送中间件

职责：
1. 工具执行前发送 progress 事件
2. 工具结果过长时自动截断 + 发送警告
"""
import logging

from langchain_core.callbacks.manager import adispatch_custom_event

from .base import AgentMiddleware

logger = logging.getLogger(__name__)

# 单次工具结果最大字符数（约 8000-16000 token），超过则截断
MAX_TOOL_RESULT_CHARS = 16000


class ProgressMiddleware(AgentMiddleware):
    """统一管理工具执行相关的 SSE 进度事件"""

    name = "progress"

    async def on_tool_call(self, tool_name, tool_args, state, config):
        """工具执行前发送进度事件"""
        await adispatch_custom_event(
            "progress",
            {"node": "tool", "message": f"执行工具 {tool_name}..."},
            config=config,
        )
        return None  # 放行

    async def on_tool_result(self, tool_name, result, state, config):
        """工具返回后处理截断"""
        if len(result) > MAX_TOOL_RESULT_CHARS:
            original_len = len(result)
            truncated = (
                result[:MAX_TOOL_RESULT_CHARS]
                + f"\n\n...[截断，原始结果共 {original_len} 字，仅保留前 {MAX_TOOL_RESULT_CHARS} 字]"
            )
            await adispatch_custom_event(
                "progress",
                {
                    "node": "tool",
                    "message": f"⚠️ 结果过长（{original_len} 字），已截断至 {MAX_TOOL_RESULT_CHARS} 字",
                },
                config=config,
            )
            return truncated
        return result
