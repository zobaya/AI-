"""
向量化模块 - 为文档块生成 embedding 向量
"""
from kb_service.processing.vectorizers.base import BaseVectorizer
from kb_service.processing.vectorizers.ollama_vectorizer import OllamaVectorizer

__all__ = [
    "BaseVectorizer",
    "OllamaVectorizer",
]
