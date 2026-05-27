"""
工具注册表

全局单例，管理所有已注册的工具实例。
支持按名称、分组、上下文条件筛选工具。
"""
import logging
from typing import Dict, List, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """全局工具注册表"""

    _tools: Dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        """注册一个工具实例"""
        cls._tools[tool.name] = tool
        logger.info(f"[ToolRegistry] Registered tool: {tool.name} (group={tool.group})")

    @classmethod
    def unregister(cls, tool_name: str):
        """注销一个工具"""
        cls._tools.pop(tool_name, None)

    @classmethod
    def get_available_tools(
        cls,
        allowed_tools: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        context: Optional[dict] = None,
    ) -> List[BaseTool]:
        """
        根据条件筛选可用工具。

        Args:
            allowed_tools: 显式白名单（用户权限），None=全部
            groups: 分组过滤（如 ["search", "parse"]）
            context: 运行时上下文（如 {"kb_ids": [...], "minio_paths": [...]}）
        """
        tools = list(cls._tools.values())

        if allowed_tools is not None:
            tools = [t for t in tools if t.name in allowed_tools]

        if groups is not None:
            tools = [t for t in tools if t.group in groups]

        if context:
            tools = [t for t in tools if t.should_activate(context)]

        return tools

    @classmethod
    def get_schemas(
        cls,
        allowed_tools: Optional[List[str]] = None,
        context: Optional[dict] = None,
    ) -> List[dict]:
        """获取筛选后工具的 JSON Schema 列表（直接传给 LLM 的 tools 参数）"""
        tools = cls.get_available_tools(allowed_tools=allowed_tools, context=context)
        return [t.get_schema() for t in tools]

    @classmethod
    def get_executor(cls, tool_name: str) -> Optional[BaseTool]:
        """按名称获取工具实例"""
        return cls._tools.get(tool_name)

    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有已注册的工具名"""
        return list(cls._tools.keys())
