"""
死循环检测中间件

职责：
1. 检查工具调用总次数是否超限
2. 检测连续重复调用同一工具+参数

这些检测原本分散在 graph.py 的 tool_node 和 should_continue 中，
提取到中间件后，节点代码更纯粹。
"""
import logging

from .base import AgentMiddleware

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware(AgentMiddleware):
    """死循环检测：总调用次数 + 连续重复调用"""

    name = "loop_detection"

    # 可通过构造函数自定义阈值
    def __init__(self, max_total_calls: int = 10, max_repeated_calls: int = 2):
        self.max_total_calls = max_total_calls
        self.max_repeated_calls = max_repeated_calls

    async def on_tool_call(self, tool_name, tool_args, state, config):
        """
        工具执行前检查是否超限。

        返回错误字符串则拦截，返回 None 放行。
        """
        # 检查总调用次数
        total = state.get("tool_calls_count", 0)
        if total >= self.max_total_calls:
            logger.warning(
                f"[loop_detection] Total tool calls ({total}) >= limit ({self.max_total_calls})"
            )
            return (
                f"已达工具调用上限（{self.max_total_calls} 次）。"
                f"请基于已有信息给出最佳回答，不要再调用工具。"
            )

        # 检查连续重复调用
        last_name = state.get("last_tool_name")
        last_args = state.get("last_tool_args")
        repeated = state.get("repeated_calls", 0)

        if tool_name == last_name and tool_args == last_args:
            repeated += 1
        else:
            repeated = 1

        if repeated >= self.max_repeated_calls:
            logger.warning(
                f"[loop_detection] Repeated tool call detected: "
                f"{tool_name}({tool_args}), count={repeated}"
            )
            return (
                f"已连续 {repeated} 次以相同参数调用 {tool_name}，停止重复调用。"
                f"请基于已有信息给出最佳回答。"
            )

        return None  # 放行
