"""
ES 知识库检索工具

包装 es_search subgraph，提供 BaseTool 接口。
"""
import logging
from typing import Any

from .base import BaseTool

logger = logging.getLogger(__name__)


class ESSearchTool(BaseTool):
    """ES 知识库检索工具"""

    name = "es_search"
    description = "在知识库中检索相关文档片段（支持语义搜索和全文搜索）"
    group = "search"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "es_search",
                "description": (
                    "在知识库（Elasticsearch）中搜索与用户问题相关的文档片段。"
                    "支持语义向量检索和全文检索混合搜索。"
                    "当用户提问涉及知识库中的内容、技术文档、规范标准等时使用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词或查询文本，应提炼用户问题中的核心语义",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数量，默认 10",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, query: str, kb_ids=None, top_k: int = 10, config=None, **kwargs) -> str:
        """
        执行 ES 检索。

        Args:
            query: 搜索关键词
            kb_ids: 知识库 ID 过滤列表（由 tool_node 从 state 注入）
            top_k: 返回结果数量
            config: LangGraph config（用于发送进度事件）
        """
        # 空列表 = 用户无任何知识库权限，直接返回空结果
        if kb_ids is not None and len(kb_ids) == 0:
            return "未找到相关的知识库内容。（用户未获得任何知识库访问权限）"

        from src.harness.subgraphs.es_search.subgraph import run_es_search_subgraph

        return await run_es_search_subgraph(
            query=query,
            kb_ids=kb_ids,
            top_k=top_k,
            config=config,
        )

    def should_activate(self, context: dict) -> bool:
        """没有知识库权限时仍可激活（es_search 内部会处理空 kb_ids）"""
        return True
