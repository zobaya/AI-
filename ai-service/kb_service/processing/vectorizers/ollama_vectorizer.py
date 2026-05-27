"""
Ollama 向量化器 - 使用 Ollama bge-m3 模型生成 embedding
"""
from typing import List, Dict
import requests
from core.config import settings
from kb_service.processing.vectorizers.base import BaseVectorizer


class OllamaVectorizer(BaseVectorizer):
    """
    Ollama 向量化器

    使用 Ollama 的 bge-m3 模型生成 embedding 向量
    """

    def __init__(self):
        self.api_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_BGE_M3_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    def vectorize(self, chunks: List[Dict]) -> List[Dict]:
        """
        为文档块列表生成 embedding 向量

        Args:
            chunks: 文档块列表

        Returns:
            List[Dict]: 添加了 content_vector 字段的文档块列表
        """
        if not chunks:
            return []

        print(f"[Vectorizer] Generating embeddings for {len(chunks)} chunks using {self.model}")
        print(f"[Vectorizer] API URL: {self.api_url}")

        chunks_with_vectors = []
        success_count = 0
        fail_count = 0

        for idx, chunk in enumerate(chunks):
            try:
                # 准备文本内容（content + headers）
                text = chunk.get("content", "")
                headers = chunk.get("headers", "")
                if headers:
                    text = f"{headers}\n\n{text}"

                # 调用 Ollama API 生成 embedding
                vector = self._generate_embedding(text)

                if vector:
                    chunk_with_vector = self._add_vector_to_chunk(chunk, vector)
                    chunks_with_vectors.append(chunk_with_vector)
                    success_count += 1

                    if (idx + 1) % 10 == 0:
                        print(f"[Vectorizer] Progress: {idx + 1}/{len(chunks)} chunks")
                else:
                    # 向量生成失败，保留原文档块（没有向量）
                    chunks_with_vectors.append(chunk)
                    fail_count += 1
                    print(f"[Vectorizer] Warning: Failed to generate vector for chunk {idx}")

            except Exception as e:
                print(f"[Vectorizer] Error processing chunk {idx}: {e}")
                chunks_with_vectors.append(chunk)
                fail_count += 1

        print(f"[Vectorizer] Complete: {success_count} success, {fail_count} failed")
        return chunks_with_vectors

    def _generate_embedding(self, text: str) -> List[float]:
        """
        调用 Ollama API 生成单个文本的 embedding

        Args:
            text: 输入文本

        Returns:
            List[float]: embedding 向量
        """
        try:
            # 截断过长的文本
            max_length = 8192  # bge-m3 的最大输入长度
            if len(text) > max_length:
                text = text[:max_length]

            response = requests.post(
                f"{self.api_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                embedding = result.get("embedding")
                if embedding:
                    return embedding
                else:
                    print(f"[Vectorizer] API response missing 'embedding' field")
                    return None
            else:
                print(f"[Vectorizer] API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"[Vectorizer] Exception: {e}")
            return None

    def _add_vector_to_chunk(self, chunk: Dict, vector: List[float]) -> Dict:
        """
        将 embedding 向量添加到文档块

        Args:
            chunk: 原始文档块
            vector: embedding 向量

        Returns:
            添加了 content_vector 字段的文档块
        """
        chunk_with_vector = chunk.copy()
        chunk_with_vector["content_vector"] = vector
        return chunk_with_vector
