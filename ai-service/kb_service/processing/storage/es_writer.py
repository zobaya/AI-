"""
ES 写入器 - 将文档块写入 Elasticsearch
"""
from typing import List, Dict
from kb_service.es_store import es_service_store


class ESWriter:
    """
    Elasticsearch 写入器

    负责将文档块列表写入 ES
    """

    @staticmethod
    def write(kb_id: str, doc_id: str, chunks: List[Dict]) -> None:
        """
        将文档块列表写入 Elasticsearch

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID
            chunks: 文档块列表（ES 格式）
        """
        if not chunks:
            print("[ESWriter] Warning: No chunks to write")
            return

        print(f"[ESWriter] Writing {len(chunks)} chunks to Elasticsearch")
        print(f"[ESWriter] KB ID: {kb_id}, Doc ID: {doc_id}")

        try:
            # 调用 es_store 的 add_document 方法
            es_service_store.add_document(
                kb_id=kb_id,
                doc_id=doc_id,
                chunks=chunks
            )
            print(f"[ESWriter] Successfully wrote {len(chunks)} chunks")

        except Exception as e:
            print(f"[ESWriter] Error writing to Elasticsearch: {e}")
            raise
