"""
向量化器基类 - 定义向量化器的统一接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict


class BaseVectorizer(ABC):
    """
    向量化器基类

    所有向量化器必须继承此类并实现 vectorize() 方法
    """

    @abstractmethod
    def vectorize(self, chunks: List[Dict]) -> List[Dict]:
        """
        为文档块列表生成 embedding 向量

        Args:
            chunks: 文档块列表，每个文档块包含：
                - content: str
                - headers: str
                - metadata: Dict

        Returns:
            List[Dict]: 添加了 content_vector 字段的文档块列表
        """
        pass

    def _add_vector_to_chunk(self, chunk: Dict, vector: List[float]) -> Dict:
        """
        为单个文档块添加向量字段

        Args:
            chunk: 文档块
            vector: embedding 向量

        Returns:
            Dict: 添加了 content_vector 字段的文档块
        """
        chunk_with_vector = chunk.copy()
        chunk_with_vector["content_vector"] = vector
        return chunk_with_vector
