"""
工具基类

所有工具必须继承 BaseTool，实现 get_schema() 和 execute()。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """工具抽象基类"""

    name: str = ""              # 工具唯一标识
    description: str = ""       # 工具描述
    group: str = "default"      # 所属分组（search / parse / calculate）

    @abstractmethod
    def get_schema(self) -> dict:
        """
        返回 OpenAI Function Calling 格式的 JSON Schema。

        格式示例：
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回文本结果"""
        ...

    def should_activate(self, context: dict) -> bool:
        """
        根据运行时上下文决定是否激活此工具。

        可在子类中覆盖以实现条件激活逻辑。
        context 可能包含：kb_ids, minio_paths, allowed_tools 等。
        """
        return True
