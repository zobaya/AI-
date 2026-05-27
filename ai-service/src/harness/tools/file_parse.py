"""
文件解析工具

包装 file_parse subgraph，提供 BaseTool 接口。
"""
import logging
from typing import Any

from .base import BaseTool

logger = logging.getLogger(__name__)


class FileParseTool(BaseTool):
    """文件解析工具"""

    name = "file_parse"
    description = "解析用户上传的文件（PDF/DOCX/XLSX/TXT），提取文本内容"
    group = "parse"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "file_parse",
                "description": (
                    "解析用户上传的文档（支持 PDF、DOCX、XLSX、TXT），提取其中的文本内容。"
                    "当用户上传了文件并希望基于文件内容提问时使用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件名（如 工作汇报.docx）",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }

    async def execute(self, file_path: str, display_name: str = None, config=None, **kwargs) -> str:
        """
        执行文件解析。

        Args:
            file_path: MinIO 文件路径（由 tool_node 从 state 中的 minio_paths 解析）
            display_name: 显示用文件名
            config: LangGraph config（用于发送进度事件）
        """
        from src.harness.subgraphs.file_parse.file_parse import file_parse

        return await file_parse(
            file_path=file_path,
            display_name=display_name,
            config=config,
        )

    def should_activate(self, context: dict) -> bool:
        """只有上传了文件时才激活"""
        return bool(context.get("minio_paths"))
