"""
中间件基类

所有中间件必须继承此类，通过生命周期钩子介入 Agent 执行流程。

生命周期钩子：
- before_node(node_name, state, config): 节点执行前，可修改 state
- after_node(node_name, state, result, config): 节点执行后，可修改 result
- on_tool_call(tool_name, tool_args, state, config): 工具执行前，返回 str 拦截，None 放行
- on_tool_result(tool_name, result, state, config): 工具返回后，可修改结果
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class AgentMiddleware(ABC):
    """中间件抽象基类"""

    name: str = "base"

    async def before_node(
        self, node_name: str, state: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """节点执行前的钩子，返回修改后的 state"""
        return state

    async def after_node(
        self,
        node_name: str,
        state: Dict[str, Any],
        result: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """节点执行后的钩子，返回修改后的 result"""
        return result

    async def on_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        state: Dict[str, Any],
        config: Dict[str, Any],
    ) -> str | None:
        """
        工具执行前的钩子。

        返回 None 表示放行（正常执行工具），
        返回 str 则替代工具结果（拦截）。
        """
        return None

    async def on_tool_result(
        self,
        tool_name: str,
        result: str,
        state: Dict[str, Any],
        config: Dict[str, Any],
    ) -> str:
        """工具返回后的钩子，返回修改后的结果"""
        return result
