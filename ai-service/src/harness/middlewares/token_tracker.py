"""
Token 统计中间件

职责：
1. 在 Agent 节点执行后收集 Token 使用量
2. 将统计数据写入 state.token_usage，供 App 层上报

当前为占位实现，Phase 2 中 LLM 返回 usage 时完善。
"""
import logging

from .base import AgentMiddleware

logger = logging.getLogger(__name__)


class TokenTrackerMiddleware(AgentMiddleware):
    """Token 消耗统计中间件"""

    name = "token_tracker"

    async def after_node(self, node_name, state, result, config):
        """
        Agent 节点执行后，提取 token 使用信息。

        当前 LLM 客户端不直接返回 usage 信息，
        后续在 LLM 层接入 usage 返回后完善此中间件。
        """
        # Phase 2 完善：从 LLM 响应中提取 usage
        # if node_name == "agent" and "usage" in result:
        #     usage = result["usage"]
        #     result["token_usage"] = {
        #         "prompt_tokens": usage.get("prompt_tokens", 0),
        #         "completion_tokens": usage.get("completion_tokens", 0),
        #     }
        return result
