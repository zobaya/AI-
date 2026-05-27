"""
通用知识库检索器 - 五步检索流程（Small-to-Big 架构）

基于 Elasticsearch 父子分块架构，结合全文检索（BM25）、向量检索（KNN）
与交叉编码器重排序（BGE Reranker），完整的企业级检索流水线。

五步检索流程：
1. 前置硬性过滤 (Pre-Filtering) - 只检索子块
2. 双路召回 (Dual-Path Recall) - BM25 + KNN
3. RRF 融合 (Reciprocal Rank Fusion) - 统一排序
4. 交叉编码器重排序 (Cross-Encoder Reranking) - BGE Reranker
5. 父块溯源与上下文组装 (Small-to-Big Context Assembly)

索引结构（v2 格式）：
- 根级字段：content, headers, content_vector
- 嵌套字段：metadata（包含所有元数据）
  - 文档级字段：doc_id, kb_id, chunk_id, file_name
  - 宏观管理字段：department, category_l1, category_l2
  - 分块级字段：parent_id, chunk_level, chunk_length
  - 状态字段：is_active, upload_time, update_time, delete_time
"""
import logging
import re
import requests
from typing import Dict, List, Any, Optional, Set
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from core.config import settings
from src.harness.subgraphs.es_search.core.reranker import RemoteReranker

logger = logging.getLogger(__name__)


# ========== 数据模型 ==========


class SearchResult(BaseModel):
    """搜索结果模型"""
    text: str
    title: str = ""
    score: float = 0.0
    page: Optional[int] = None
    doc_id: str = ""
    chunk_id: str = ""
    kb_id: str = ""
    source_file: str = ""
    chunk_index: int = 0
    chunk_level: int = 1  # 分块层级（1=父块，2=子块）
    parent_id: Optional[str] = None  # 父块 ID


class SearchResponse(BaseModel):
    """搜索响应模型"""
    total: int = 0
    hits: List[Dict[str, Any]] = []
    success: bool = False
    error: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None  # 调试信息
    reranked: bool = False  # 是否进行了重排序
    rerank_scores: List[float] = []  # 重排序分数列表


# ========== 检索器实现 ==========


class GeneralKBRetriever:
    """通用知识库检索器 - 五步检索流程（Small-to-Big 架构）"""
    name: str = "general_kb_retriever"
    description: str = "通用知识库检索工具，支持父子分块和五步检索流程"

    def __init__(self):
        """初始化 ES 客户端和 Reranker"""
        self.es = self._create_es_client()
        self.index_name = "kb_service"  # 固定使用 kb_service 索引
        self.reranker = RemoteReranker() if settings.QA_ENABLE_RERANKER else None
        logger.info(f"通用知识库检索器初始化完成: {settings.ES_HOST}, index={self.index_name}")
        logger.info(f"  - 启用 Reranker: {settings.QA_ENABLE_RERANKER}")
        logger.info(f"  - 启用父块溯源: {settings.QA_PARENT_CHUNK_ENABLED}")

    def _create_es_client(self) -> Elasticsearch:
        """创建 ES 客户端连接"""
        try:
            client = Elasticsearch(
                settings.ES_URL,
                request_timeout=30
            )
            logger.info("ES 客户端创建成功")
            return client
        except Exception as e:
            logger.error(f"ES 客户端创建失败: {str(e)}")
            raise

    def health_check(self) -> bool:
        """检查 ES 服务健康状态"""
        try:
            return self.es.ping()
        except Exception as e:
            logger.error(f"ES 健康检查失败: {str(e)}")
            return False

    def _get_query_embedding(self, query_text: str) -> Optional[List[float]]:
        """获取查询向量 - 使用 Ollama bge-m3 模型"""
        try:
            url = settings.OLLAMA_EMBED_URL
            payload = {
                "model": settings.OLLAMA_BGE_M3_MODEL,
                "input": query_text
            }
            headers = {"Content-Type": "application/json; charset=UTF-8"}

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=settings.OLLAMA_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            # Ollama 格式 v1: {"embedding": [0.1, 0.2, ...]}
            if "embedding" in data:
                embedding = data["embedding"]
                logger.info(f"获取向量成功 (Ollama v1)，维度: {len(embedding)}")
                return embedding

            # Ollama 格式 v2: {"embeddings": [[0.1, 0.2, ...]]}
            if "embeddings" in data and len(data["embeddings"]) > 0:
                embedding = data["embeddings"][0]
                logger.info(f"获取向量成功 (Ollama v2)，维度: {len(embedding)}")
                return embedding

            logger.warning(f"Embedding 响应格式不正确: {data.keys()}")
            return None

        except Exception as e:
            logger.error(f"获取 embedding 失败: {str(e)}")
            return None

    # ========== 第一步：前置硬性过滤 ==========

    def _build_pre_filters(
        self,
        filters: Optional[Dict[str, Any]] = None,
        only_children: bool = True,
        kb_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        构建前置硬性过滤条件

        Args:
            filters: 业务过滤条件（department, category_l1, category_l2）
            only_children: 是否只检索子块（默认 True）
            kb_ids: 知识库ID列表，用于按 metadata.kb_id 过滤

        Returns:
            ES filter 子句列表
        """
        filter_clauses = []

        # 1. 状态过滤：只返回激活的分块
        filter_clauses.append({"term": {"metadata.is_active": True}})

        # 2. 层级过滤：只检索子块（chunk_level > 0）
        if only_children:
            filter_clauses.append({"range": {"metadata.chunk_level": {"gt": 0}}})

        # 3. 知识库过滤：按 metadata.kb_id 过滤
        if kb_ids is not None and len(kb_ids) > 0:
            if len(kb_ids) == 1:
                filter_clauses.append({"term": {"metadata.kb_id": kb_ids[0]}})
            else:
                filter_clauses.append({"terms": {"metadata.kb_id": kb_ids}})

        # 4. 业务过滤：department, category_l1, category_l2
        if filters:
            if filters.get("department"):
                filter_clauses.append({"term": {"metadata.department": filters["department"]}})
            if filters.get("category_l1"):
                filter_clauses.append({"term": {"metadata.category_l1": filters["category_l1"]}})
            if filters.get("category_l2"):
                category_l2_values = filters["category_l2"]
                if isinstance(category_l2_values, str):
                    category_l2_values = [category_l2_values]
                filter_clauses.append({"terms": {"metadata.category_l2": category_l2_values}})

        return filter_clauses

    # ========== 第二步：双路召回 ==========

    def _bm25_recall(
        self,
        query_text: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        kb_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        BM25 全文召回 - 通用知识库检索策略（v2 格式）

        检索策略：
            1. Headers: 标题匹配 (Boost: 2.0)
            2. Content: 全文匹配 (Boost: 1.0)
            3. File Name: 文件名匹配 (Boost: 1.5)

        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            filters: 业务过滤条件
            kb_ids: 知识库ID列表

        Returns:
            搜索命中结果列表
        """
        # 构建过滤条件（只检索子块）
        filter_clauses = self._build_pre_filters(filters, only_children=True, kb_ids=kb_ids)

        # 构建 Should 子句（检索策略）
        should_clauses = []

        # 1. Headers: 标题匹配，高权重 (Boost: 2.0)
        should_clauses.append({
            "match": {
                "headers": {
                    "query": query_text,
                    "boost": 2.0
                }
            }
        })

        # 2. Content: 全文匹配，基础权重 (Boost: 1.0)
        should_clauses.append({
            "match": {
                "content": {
                    "query": query_text,
                    "minimum_should_match": "50%",
                    "boost": 1.0
                }
            }
        })

        # 3. File Name: 文件名匹配，中等权重 (Boost: 1.5)
        should_clauses.append({
            "match": {
                "metadata.file_name": {
                    "query": query_text,
                    "boost": 1.5
                }
            }
        })

        # 构建查询
        query_body = {
            "bool": {
                "should": should_clauses,
                "filter": filter_clauses,
                "minimum_should_match": 1
            }
        }

        try:
            res = self.es.search(
                index=self.index_name,
                query=query_body,
                size=top_k
            )
            hits = res["hits"]["hits"]
            logger.info(f"BM25 召回返回 {len(hits)} 条结果（子块）")
            return hits
        except Exception as e:
            logger.error(f"BM25 召回失败: {str(e)}")
            return []

    def _knn_recall(
        self,
        query_vec: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        kb_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        KNN 向量召回 - 使用 content_vector 字段（v2 格式）

        Args:
            query_vec: 查询向量
            top_k: 返回结果数量
            filters: 业务过滤条件
            kb_ids: 知识库ID列表

        Returns:
            搜索命中结果列表
        """
        try:
            # 构建过滤条件（只检索子块）
            filter_clauses = self._build_pre_filters(filters, only_children=True, kb_ids=kb_ids)

            # 使用 KNN 搜索
            knn_body = {
                "size": top_k,
                "query": {
                    "bool": {
                        "must": {"match_all": {}},
                        "filter": filter_clauses
                    }
                },
                "knn": {
                    "field": "content_vector",
                    "query_vector": query_vec,
                    "k": top_k,
                    "num_candidates": top_k * 2
                }
            }

            url = f"{settings.ES_URL}/{self.index_name}/_search"
            headers = {"Content-Type": "application/json; charset=UTF-8"}

            response = requests.post(url, headers=headers, json=knn_body, timeout=30)
            response.raise_for_status()
            res = response.json()

            hits = res["hits"]["hits"]
            logger.info(f"KNN 召回返回 {len(hits)} 条结果（子块）")
            return hits

        except Exception as e:
            logger.warning(f"KNN 召回失败: {str(e)}")
            return []

    # ========== 第三步：RRF 融合 ==========

    def _rrf_fusion(
        self,
        bm25_hits: List[Dict],
        knn_hits: List[Dict],
        top_k: int,
        k: int = 60
    ) -> List[Dict]:
        """
        RRF (Reciprocal Rank Fusion) 融合算法

        公式：score = sum(1 / (k + rank)) for each ranking

        Args:
            bm25_hits: BM25 召回结果
            knn_hits: KNN 召回结果
            top_k: 返回前 K 条融合结果
            k: RRF 参数（默认 60）

        Returns:
            融合后的结果列表（包含 _rrf_score 字段）
        """
        # 构建排名字典
        scores: Dict[str, float] = {}
        hit_map: Dict[str, Dict] = {}  # 保存完整的 hit 信息

        # 处理 BM25 结果
        for rank, hit in enumerate(bm25_hits, start=1):
            key = f"{hit['_index']}|{hit['_id']}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            hit_map[key] = hit
            hit["_bm25_rank"] = rank

        # 处理 KNN 结果
        for rank, hit in enumerate(knn_hits, start=1):
            key = f"{hit['_index']}|{hit['_id']}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            hit_map[key] = hit
            hit["_knn_rank"] = rank

        # 按 RRF 得分排序
        sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # 构建融合结果
        fused_hits = []
        for key in sorted_keys[:top_k]:
            hit = hit_map[key]
            hit["_rrf_score"] = scores[key]
            fused_hits.append(hit)

        logger.info(f"RRF 融合完成，返回 {len(fused_hits)} 条结果")
        return fused_hits

    # ========== 第四步：交叉编码器重排序 ==========

    def _rerank(
        self,
        query: str,
        hits: List[Dict],
        top_k: int
    ) -> List[Dict]:
        """
        使用 BGE Reranker 进行重排序

        Args:
            query: 查询文本
            hits: 待重排序的结果列表
            top_k: 返回前 K 条结果

        Returns:
            重排序后的结果列表
        """
        if not self.reranker:
            logger.warning("Reranker 未启用，跳过重排序")
            return hits[:top_k]

        if not hits:
            logger.warning("待重排序结果为空")
            return []

        # 构建 Reranker 输入格式
        documents = []
        for hit in hits:
            src = hit["_source"]
            # 提取文本（优先使用 content，其次 headers）
            text = src.get("content", "")
            headers = src.get("headers", "")
            if headers:
                text = f"[{headers}]\n{text}"
            documents.append(text)

        try:
            # 调用 Reranker
            rerank_result = self.reranker.rerank(
                query=query,
                results=[{"text": doc} for doc in documents],
                top_k=top_k
            )

            # 提取重排序后的索引，映射回原始 hits
            reranked_hits = []
            for i, result in enumerate(rerank_result.results):
                original_idx = documents.index(result["text"])
                hit = hits[original_idx]
                hit["_rerank_score"] = rerank_result.scores[i]
                hit["_rerank_rank"] = i + 1
                reranked_hits.append(hit)

            logger.info(f"重排序完成，返回 {len(reranked_hits)} 条结果")
            return reranked_hits

        except Exception as e:
            logger.error(f"重排序失败: {str(e)}，返回原始结果")
            return hits[:top_k]

    # ========== 第五步：父块溯源与上下文组装 ==========

    def _fetch_parent_chunks(
        self,
        parent_ids: Set[str],
        max_size: int = 5000
    ) -> Dict[str, Dict]:
        """
        批量获取父块内容

        Args:
            parent_ids: 父块 ID 集合
            max_size: 父块最大字符数（超过则截断）

        Returns:
            父块 ID -> 父块内容的映射
        """
        if not parent_ids:
            return {}

        try:
            # 使用 mget 批量获取父块
            parent_ids_list = list(parent_ids)
            response = self.es.mget(
                index=self.index_name,
                ids=parent_ids_list
            )

            parent_chunks = {}
            for doc in response.get("docs", []):
                if doc.get("found"):
                    src = doc["_source"]
                    parent_id = src.get("metadata", {}).get("chunk_id", "")

                    # 组装父块内容（headers + content）
                    headers = src.get("headers", "")
                    content = src.get("content", "")

                    # 截断过长的内容
                    if len(content) > max_size:
                        content = content[:max_size] + "..."

                    if headers:
                        text = f"[{headers}]\n{content}"
                    else:
                        text = content

                    parent_chunks[parent_id] = {
                        "text": text,
                        "headers": headers,
                        "content": content,
                        "doc_id": src.get("metadata", {}).get("doc_id", ""),
                        "file_name": src.get("metadata", {}).get("file_name", ""),
                    }

            logger.info(f"获取父块内容: {len(parent_chunks)}/{len(parent_ids_list)}")
            return parent_chunks

        except Exception as e:
            logger.error(f"获取父块内容失败: {str(e)}")
            return {}

    def _assemble_parent_context(
        self,
        child_hits: List[Dict],
        max_size: int = 5000
    ) -> List[SearchResult]:
        """
        组装父块上下文（Small-to-Big）

        Args:
            child_hits: 子块命中结果列表
            max_size: 父块最大字符数

        Returns:
            组装后的搜索结果列表（使用父块内容）
        """
        # 1. 提取并去重 parent_id
        parent_ids: Set[str] = set()
        for hit in child_hits:
            src = hit["_source"]
            parent_id = src.get("metadata", {}).get("parent_id")
            if parent_id:
                parent_ids.add(parent_id)

        if not parent_ids:
            logger.warning("没有找到 parent_id，无法组装父块上下文")
            return []

        # 2. 批量获取父块内容
        parent_chunks = self._fetch_parent_chunks(parent_ids, max_size)

        if not parent_chunks:
            logger.warning("获取父块内容失败")
            return []

        # 3. 组装搜索结果（使用父块内容）
        results = []
        seen_parent_ids = set()

        for hit in child_hits:
            src = hit["_source"]
            metadata = src.get("metadata", {})
            parent_id = metadata.get("parent_id")

            # 去重：同一个父块只返回一次
            if parent_id in seen_parent_ids:
                continue
            if parent_id not in parent_chunks:
                continue

            seen_parent_ids.add(parent_id)

            parent_chunk = parent_chunks[parent_id]

            # 提取元数据
            page = metadata.get("page")
            doc_id = metadata.get("doc_id", "")
            chunk_id = metadata.get("chunk_id", "")
            file_name = metadata.get("file_name", "")

            results.append(SearchResult(
                text=parent_chunk["text"],
                title=parent_chunk["headers"],
                score=hit.get("_rerank_score", hit.get("_rrf_score", hit.get("_score", 0.0))),
                page=page,
                doc_id=doc_id,
                chunk_id=chunk_id,
                kb_id=self.index_name,
                source_file=file_name,
                chunk_index=0,
                chunk_level=1,  # 父块
                parent_id=None
            ))

        logger.info(f"组装父块上下文完成，返回 {len(results)} 条结果")
        return results

    # ========== 辅助方法 ==========

    def _extract_chunk_index(self, chunk_id: str) -> int:
        """从 chunk_id 中提取索引号"""
        try:
            # 父子-子块格式: _P_\d+_C_(\d+)$
            match = re.search(r'_P_\d+_C_(\d+)$', chunk_id)
            if match:
                return int(match.group(1))

            # 父子-父块格式: _P_(\d+)$
            match = re.search(r'_P_(\d+)$', chunk_id)
            if match:
                return int(match.group(1))

            # 层级格式: _L\d+_(\d+)$
            match = re.search(r'_L\d+_(\d+)$', chunk_id)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 0

    # ========== 主流程 ==========

    def run(
        self,
        query_text: str,
        top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        status_callback: Optional[callable] = None,
        kb_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        执行通用知识库五步检索流程

        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            filters: 业务过滤条件（department, category_l1, category_l2）
            status_callback: 状态回调函数
            kb_ids: 知识库ID列表，用于按 metadata.kb_id 过滤

        Returns:
            搜索响应字典
        """
        debug_info = {}

        try:
            if not query_text:
                return SearchResponse(success=False, error="查询文本不能为空").dict()

            search_top_k = top_k if top_k is not None else settings.QA_DEFAULT_TOP_K

            logger.info(f"开始五步检索流程: query_len={len(query_text)}, index={self.index_name}, top_k={search_top_k}, kb_ids={kb_ids}")

            def send_status(message: str, stage: str = "processing"):
                if status_callback:
                    try:
                        status_callback({"stage": stage, "message": message})
                    except Exception as e:
                        logger.warning(f"状态回调失败: {e}")

            # ========== 第一步：前置硬性过滤 ==========
            send_status("正在构建前置过滤条件...", "pre_filter")
            filter_clauses = self._build_pre_filters(filters, only_children=True, kb_ids=kb_ids)
            debug_info["pre_filter_count"] = len(filter_clauses)
            logger.info(f"[第一步] 前置硬性过滤: {len(filter_clauses)} 个过滤条件, kb_ids={kb_ids}")

            # ========== 第二步：双路召回 ==========
            send_status("正在执行双路召回（BM25 + KNN）...", "recall")

            # 2.1 BM25 召回
            send_status("正在执行 BM25 全文召回...", "bm25_recall")
            bm25_hits = self._bm25_recall(
                query_text=query_text,
                top_k=settings.QA_RECALL_BM25_TOP_K,
                filters=filters,
                kb_ids=kb_ids
            )
            debug_info["bm25_recall_count"] = len(bm25_hits)
            logger.info(f"[第二步] BM25 召回: {len(bm25_hits)} 条结果")

            # 2.2 KNN 召回
            knn_hits = []
            query_vec = self._get_query_embedding(query_text)
            if query_vec:
                send_status("正在执行 KNN 向量召回...", "knn_recall")
                knn_hits = self._knn_recall(
                    query_vec=query_vec,
                    top_k=settings.QA_RECALL_KNN_TOP_K,
                    filters=filters,
                    kb_ids=kb_ids
                )
                debug_info["knn_recall_count"] = len(knn_hits)
                logger.info(f"[第二步] KNN 召回: {len(knn_hits)} 条结果")
            else:
                debug_info["knn_recall_count"] = 0
                logger.warning("[第二步] KNN 召回失败（向量生成失败）")

            # ========== 第三步：RRF 融合 ==========
            send_status("正在执行 RRF 融合...", "rrf_fusion")
            fused_hits = self._rrf_fusion(
                bm25_hits=bm25_hits,
                knn_hits=knn_hits,
                top_k=settings.QA_RRF_TOP_K,
                k=settings.QA_RRF_K
            )
            debug_info["rrf_fusion_count"] = len(fused_hits)
            logger.info(f"[第三步] RRF 融合: {len(fused_hits)} 条结果")

            # ========== 第四步：交叉编码器重排序 ==========
            reranked_hits = fused_hits
            rerank_scores = []  # 收集重排序分数
            if settings.QA_ENABLE_RERANKER:
                send_status("正在执行重排序...", "rerank")
                reranked_hits = self._rerank(
                    query=query_text,
                    hits=fused_hits,
                    top_k=settings.QA_RERANKER_TOP_K
                )
                # 收集重排序分数
                rerank_scores = [hit.get("_rerank_score", 0.0) for hit in reranked_hits]
                debug_info["rerank_count"] = len(reranked_hits)
                logger.info(f"[第四步] 重排序: {len(reranked_hits)} 条结果")
            else:
                debug_info["rerank_count"] = len(fused_hits)
                logger.info(f"[第四步] 重排序跳过（未启用）")

            # ========== 第五步：父块溯源与上下文组装 ==========
            if settings.QA_PARENT_CHUNK_ENABLED:
                send_status("正在组装父块上下文...", "parent_assembly")
                results = self._assemble_parent_context(
                    child_hits=reranked_hits,
                    max_size=settings.QA_PARENT_CHUNK_MAX_SIZE
                )
                debug_info["parent_assembly_count"] = len(results)
                logger.info(f"[第五步] 父块溯源: {len(results)} 条结果")
            else:
                # 不启用父块溯源，直接返回子块结果
                results = []
                for hit in reranked_hits[:search_top_k]:
                    src = hit["_source"]
                    metadata = src.get("metadata", {})

                    results.append(SearchResult(
                        text=src.get("content", ""),
                        title=src.get("headers", ""),
                        score=hit.get("_rerank_score", hit.get("_rrf_score", hit.get("_score", 0.0))),
                        page=metadata.get("page"),
                        doc_id=metadata.get("doc_id", ""),
                        chunk_id=metadata.get("chunk_id", ""),
                        kb_id=self.index_name,
                        source_file=metadata.get("file_name", ""),
                        chunk_index=self._extract_chunk_index(metadata.get("chunk_id", "")),
                        chunk_level=metadata.get("chunk_level", 1),
                        parent_id=metadata.get("parent_id")
                    ))
                debug_info["parent_assembly_count"] = len(results)
                logger.info(f"[第五步] 父块溯源跳过（未启用），返回 {len(results)} 条子块结果")

            # ========== 返回结果 ==========
            # 转换为字典格式（按 top_k 切片）
            hits = [result.dict() for result in results[:search_top_k]]

            # 发送最终结果数量
            send_status(f"检索完成，共 {len(hits)} 条结果", "completed")

            logger.info(f"五步检索流程完成，返回 {len(hits)} 条结果（从 {len(results)} 条中筛选）")

            return SearchResponse(
                total=len(hits),
                hits=hits,
                success=True,
                debug_info=debug_info,
                # 添加重排序信息
                reranked=len(rerank_scores) > 0,
                rerank_scores=rerank_scores[:len(hits)]  # 只返回实际返回的分数
            ).dict()

        except Exception as e:
            error_msg = f"五步检索流程失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return SearchResponse(
                success=False,
                error=error_msg,
                debug_info=debug_info
            ).dict()
