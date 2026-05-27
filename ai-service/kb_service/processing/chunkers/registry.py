"""
分块器注册表 - 根据配置路由到对应的分块器
"""
from typing import Optional
from kb_service.processing.chunkers.base import BaseChunker
from kb_service.processing.chunkers.parent_child_chunker import ParentChildChunker

# 分块器注册表（通过名称索引）
CHUNKER_REGISTRY = {}


def register_chunker(name: str, chunker_class: type) -> None:
    """注册分块器到注册表"""
    CHUNKER_REGISTRY[name] = chunker_class
    print(f"[ChunkerRegistry] Registered: {name} -> {chunker_class.__name__}")


def get_chunker(name: Optional[str] = None) -> BaseChunker:
    """根据名称获取分块器实例"""
    from core.config import settings

    if name is None:
        name = "parent_child" if settings.USE_PARENT_CHILD_CHUNKING else "semantic"

    chunker_class = CHUNKER_REGISTRY.get(name)

    if not chunker_class:
        supported = ", ".join(CHUNKER_REGISTRY.keys())
        raise ValueError(
            f"Unknown chunker: {name}. "
            f"Supported chunkers: {supported}"
        )

    return chunker_class()


def list_chunkers() -> list:
    """返回所有已注册的分块器名称列表"""
    return sorted(CHUNKER_REGISTRY.keys())


# 注册内置分块器
register_chunker("parent_child", ParentChildChunker)
