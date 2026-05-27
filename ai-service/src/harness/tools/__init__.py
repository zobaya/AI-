"""
动态工具系统

启动时调用 register_all_tools() 注册所有内置工具。
节点通过 ToolRegistry 查询可用工具和执行器。
"""
from .registry import ToolRegistry
from .es_search import ESSearchTool
from .file_parse import FileParseTool
from .calculate import CalculateTool
from .ppt_generate import PPTGenerateTool

# 内置工具列表（按注册顺序）
_BUILTIN_TOOLS = [ESSearchTool, FileParseTool, CalculateTool, PPTGenerateTool]


def register_all_tools():
    """注册所有内置工具 — 在应用启动时调用一次"""
    for tool_cls in _BUILTIN_TOOLS:
        ToolRegistry.register(tool_cls())
