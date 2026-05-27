"""
重排序工具 - 使用远程 BGE Reranker 模型

对 ES 检索结果进行智能重排序，提高相关性
"""
import time
import requests
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """重排序结果"""
    results: List[Dict[str, Any]]  # 重排序后的结果
    scores: List[float]  # 重排序分数
    elapsed_time: float  # 耗时


class RemoteReranker:
    """远程重排序服务（BGE Reranker）"""

    # 工具接口属性
    name = "reranker"
    description = "使用 BGE Reranker 模型对检索结果进行重排序"

    def __init__(self):
        """初始化远程重排序器"""
        # 使用 core.config 中的配置，如果没有专门的 reranker 配置，则使用 ES 相关配置
        self.base_url = getattr(settings, 'RERANKER_BASE_URL', 'http://10.199.194.246:9997/v1')
        self.model_name = getattr(settings, 'RERANKER_MODEL_NAME', 'bge-reranker-v2-m3')
        self.model_uid = getattr(settings, 'RERANKER_MODEL_UID', 'bge-reranker-v2-m3')
        self.api_key = getattr(settings, 'RERANKER_API_KEY', 'none')
        self.timeout = getattr(settings, 'RERANKER_TIMEOUT', 30)

        logger.info(f"RemoteReranker 初始化 - 模型: {self.model_name}, 服务: {self.base_url}")

    def run(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = None,
    ) -> Dict[str, Any]:
        """
        统一工具接口 - 执行重排序

        Args:
            query: 查询文本
            results: 检索结果列表
            top_k: 返回前 K 个结果

        Returns:
            Dict 包含重排序结果
        """
        rerank_result = self.rerank(query, results, top_k)

        return {
            "success": True,
            "results": rerank_result.results,
            "scores": rerank_result.scores,
            "elapsed_time": rerank_result.elapsed_time,
        }

    def _extract_text_from_result(self, result: Dict[str, Any]) -> str:
        """
        从检索结果中提取文本内容

        Args:
            result: 单个检索结果（字典格式）

        Returns:
            提取的文本内容
        """
        # 优先使用 text 字段
        text = result.get("text", "")

        if text:
            return text

        # 如果没有 text 字段，尝试从 _source 提取
        if "_source" in result:
            source = result["_source"]
            # 优先使用 content
            content = source.get("content", "")
            if content:
                return content

            # 尝试组合其他字段
            parts = []
            if source.get("headers"):
                parts.append(f"[{source['headers']}]")
            if source.get("chunk_tags"):
                parts.append(f"标签: {source['chunk_tags']}")
            if content:
                parts.append(content)

            return " ".join(parts).strip()

        # 最后尝试 page_content
        page_content = result.get("page_content", "")
        if page_content:
            return page_content

        return ""

    def _build_enhanced_text(
        self,
        result: Dict[str, Any],
        query: str,
        selected_intents: Optional[List[str]] = None
    ) -> str:
        """
        构建增强的文本内容（包含意图信息）

        Args:
            result: 检索结果
            query: 用户查询
            selected_intents: 用户选中的意图列表

        Returns:
            增强后的文本
        """
        base_text = self._extract_text_from_result(result)

        # 如果是 manual 知识库且有意图信息，添加意图上下文
        if selected_intents and result.get("kb_id") == "kb_manual":
            intent_info = result.get("intent", [])
            if intent_info:
                # 将意图列表转换为字符串
                intent_str = "、".join(intent_info) if isinstance(intent_info, list) else str(intent_info)
                base_text = f"[业务意图: {intent_str}] {base_text}"

        return base_text

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = None,
        selected_intents: Optional[List[str]] = None
    ) -> RerankResult:
        """
        调用远程重排序服务

        Args:
            query: 查询文本
            results: ES 检索结果列表
            top_k: 返回前 K 个结果
            selected_intents: 用户选中的意图列表（用于构建增强文本）

        Returns:
            RerankResult: 重排序结果
        """
        start_time = time.time()

        try:
            # 数据验证
            if not query or not query.strip():
                logger.warning("查询文本为空，跳过重排序")
                return RerankResult(results=[], scores=[], elapsed_time=0.0)

            if not results:
                logger.warning("检索结果为空，跳过重排序")
                return RerankResult(results=[], scores=[], elapsed_time=0.0)

            # 提取文档文本
            documents = []
            valid_indices = []
            for idx, result in enumerate(results):
                # 使用增强文本提取
                text = self._build_enhanced_text(result, query, selected_intents)

                # 只保留非空文档
                if text and text.strip():
                    documents.append(text)
                    valid_indices.append(idx)
                else:
                    logger.debug(f"文档 {idx} 文本为空，跳过")

            if not documents:
                logger.warning("所有文档文本均为空，跳过重排序")
                return RerankResult(results=[], scores=[], elapsed_time=0.0)

            # 构建 Enhanced Query（包含意图信息）
            enhanced_query = query.strip()
            if selected_intents:
                intent_desc = "、".join(selected_intents)
                enhanced_query = f"[业务意图: {intent_desc}] {query}"

            # 构建请求
            url = f"{self.base_url}/rerank"
            payload = {
                "model": self.model_uid,
                "query": enhanced_query,
                "documents": documents,
                "top_n": top_k if top_k else len(documents),
            }

            headers = {"Content-Type": "application/json; charset=UTF-8"}

            # 如果需要 API key
            if self.api_key and self.api_key != "none":
                headers["Authorization"] = f"Bearer {self.api_key}"

            logger.info(f"请求重排序: {len(documents)} 条文档")
            logger.info(f"  - 查询: {enhanced_query[:100]}...")
            logger.info(f"  - 模型: {self.model_uid}")
            logger.info(f"  - Top-N: {top_k if top_k else len(documents)}")
            if selected_intents:
                logger.info(f"  - 使用意图增强: {selected_intents}")

            # 发送请求
            logger.debug(f"Reranker 请求 URL: {url}")
            logger.debug(f"Reranker 请求 Payload (前500字符): {str(payload)[:500]}")

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )

            # 检查响应状态
            logger.debug(f"Reranker 响应状态: {response.status_code}")

            # 如果返回 400，打印响应内容
            if response.status_code == 400:
                logger.error(f"Reranker 400 错误: {response.text}")
                logger.error(f"请求 URL: {url}")
                logger.error(f"请求 Payload: {payload}")

            response.raise_for_status()

            # 解析响应
            data = response.json()
            rerank_items = data.get("results", [])

            # 根据返回的索引和分数重新排序
            # 注意：Reranker 返回的 index 对应 documents 列表的索引
            # 需要通过 valid_indices 映射回原始 results 列表
            reranked_results = []
            reranked_scores = []

            for item in rerank_items:
                doc_idx = item.get("index")  # documents 列表中的索引
                score = item.get("relevance_score", 0.0)

                # 映射回原始 results 索引
                if doc_idx < len(valid_indices):
                    original_idx = valid_indices[doc_idx]
                    if original_idx < len(results):
                        reranked_results.append(results[original_idx])
                        reranked_scores.append(score)

            elapsed = time.time() - start_time

            # 阈值过滤：移除低于阈值的结果
            threshold = getattr(settings, 'QA_RERANKER_SCORE_THRESHOLD', 0)
            if threshold > 0 and reranked_scores:
                original_count = len(reranked_results)
                filtered_pairs = [
                    (r, s) for r, s in zip(reranked_results, reranked_scores) if s >= threshold
                ]
                reranked_results = [p[0] for p in filtered_pairs]
                reranked_scores = [p[1] for p in filtered_pairs]
                filtered_count = original_count - len(reranked_results)
                if filtered_count > 0:
                    logger.info(
                        f"阈值过滤（{threshold}）：保留 {len(reranked_results)} 条，"
                        f"过滤掉 {filtered_count} 条低分结果"
                    )

            logger.info(f"重排序完成，返回 {len(reranked_results)} 条结果，耗时 {elapsed:.3f}秒")

            return RerankResult(
                results=reranked_results,
                scores=reranked_scores,
                elapsed_time=elapsed,
            )

        except Exception as e:
            logger.error(f"重排序失败: {e}")
            logger.warning("返回原始 ES 结果")

            # 失败时返回原始 ES 结果
            elapsed = time.time() - start_time
            top_results = results[:top_k] if top_k else results
            return RerankResult(
                results=top_results,
                scores=[r.get("score", 0.0) if isinstance(r, dict) else 0.0 for r in top_results],
                elapsed_time=elapsed,
            )


def get_reranker() -> RemoteReranker:
    """获取重排序器实例"""
    return RemoteReranker()
