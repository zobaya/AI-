"""
分块器模块 - 将 Markdown 文本转换为 ES 格式的文档块

支持的分块策略：
- ParentChildChunker: 父子分块（推荐）
- SemanticChunker: 语义分块
- HeaderChunker: 基于标题的分块
- HybridChunker: 混合分块
"""
from kb_service.processing.chunkers.base import BaseChunker, ChunkResult
from kb_service.processing.chunkers.registry import get_chunker, CHUNKER_REGISTRY

__all__ = [
    "BaseChunker",
    "ChunkResult",
    "get_chunker",
    "CHUNKER_REGISTRY",
]
