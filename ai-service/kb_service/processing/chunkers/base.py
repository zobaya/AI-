"""
分块器基类 - 定义所有分块器的统一接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class ChunkLevel(Enum):
    """分块层级"""
    PARENT = 1    # 父块
    CHILD = 2     # 子块


@dataclass
class ChunkMetadata:
    """
    分块元数据（ES metadata 字段）
    """
    doc_id: str
    chunk_id: str
    parent_id: Optional[str] = None
    chunk_level: int = ChunkLevel.PARENT.value
    chunk_length: int = 0
    file_name: str = ""
    kb_id: Optional[str] = None
    department: Optional[str] = None
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    is_active: bool = True
    upload_time: Optional[str] = None
    update_time: Optional[str] = None
    delete_time: Optional[str] = None


@dataclass
class ChunkResult:
    """
    分块结果

    ES 格式的文档块
    """
    content: str                  # 文本内容
    headers: str                  # 标题路径（字符串格式，用 " > " 分隔）
    metadata: ChunkMetadata       # 元数据对象

    def to_dict(self) -> Dict:
        """转换为 ES 文档格式（v2 mapping）"""
        return {
            "content": self.content,
            "headers": self.headers,
            "metadata": {
                "doc_id": self.metadata.doc_id,
                "chunk_id": self.metadata.chunk_id,
                "parent_id": self.metadata.parent_id,
                "chunk_level": self.metadata.chunk_level,
                "chunk_length": self.metadata.chunk_length,
                "file_name": self.metadata.file_name,
                "kb_id": self.metadata.kb_id,
                "department": self.metadata.department,
                "category_l1": self.metadata.category_l1,
                "category_l2": self.metadata.category_l2,
                "is_active": self.metadata.is_active,
                "upload_time": self.metadata.upload_time,
                "update_time": self.metadata.update_time,
                "delete_time": self.metadata.delete_time,
            }
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ChunkResult':
        """从字典创建 ChunkResult"""
        metadata = ChunkMetadata(**data.get("metadata", {}))
        return cls(
            content=data.get("content", ""),
            headers=data.get("headers", ""),
            metadata=metadata
        )


class BaseChunker(ABC):
    """
    分块器基类

    所有分块器必须继承此类并实现 chunk() 方法
    """

    @abstractmethod
    def chunk(
        self,
        markdown: str,
        doc_id: str,
        file_name: str
    ) -> List[Dict]:
        """
        将 Markdown 文本分块为 ES 格式的文档块列表

        Args:
            markdown: Markdown 文本内容
            doc_id: 文档 ID
            file_name: 文件名

        Returns:
            List[Dict]: ES 格式的文档块列表，每个文档块包含：
                - content: str           # 文本内容
                - headers: str           # 标题路径
                - metadata: Dict         # 元数据（v2 格式，嵌套结构）
        """
        pass

    def _create_chunk_id(
        self,
        doc_id: str,
        parent_idx: int,
        child_idx: Optional[int] = None
    ) -> str:
        """
        生成统一的 chunk_id 格式

        格式：
        - 父块: {doc_id}_P_{parent_idx:03d}
        - 子块: {doc_id}_P_{parent_idx:03d}_C_{child_idx:03d}

        Args:
            doc_id: 文档 ID
            parent_idx: 父块索引
            child_idx: 子块索引（None 表示父块）

        Returns:
            str: chunk_id
        """
        if child_idx is None:
            return f"{doc_id}_P_{parent_idx:03d}"
        else:
            return f"{doc_id}_P_{parent_idx:03d}_C_{child_idx:03d}"

    def _format_headers(self, headers: list) -> str:
        """
        将 headers 数组格式化为字符串

        Args:
            headers: 标题路径数组，如 ["第一章", "1.1 节"]

        Returns:
            str: 格式化的标题路径，如 "第一章 > 1.1 节"
        """
        if not headers:
            return ""
        if isinstance(headers, str):
            return headers
        return " > ".join(headers)
