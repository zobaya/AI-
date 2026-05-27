"""
ES 检索子图 - 核心节点

节点 1: search_node   — 执行 ES 检索，追加到累积上下文
节点 2: evaluate_node — LLM 反思评估，判断信息是否充足

进度事件由 subgraph.py 的 _dispatch_node_progress 统一发送，
节点内部不发 adispatch_custom_event，避免与 wrapper 层重复。
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional

from src.harness.subgraphs.es_search.state import SearchState
from src.harness.subgraphs.es_search.prompts import SEARCH_EVALUATOR_PROMPT
from src.harness.subgraphs.es_search.core.general_kb_retriever import GeneralKBRetriever
from src.harness.llm import get_llm_client

from core.config import settings

logger = logging.getLogger(__name__)

# ========== 单例检索器 ==========

_retriever: Optional[GeneralKBRetriever] = None


def _get_retriever() -> GeneralKBRetriever:
    global _retriever
    if _retriever is None:
        _retriever = GeneralKBRetriever()
    return _retriever


# ========== 节点 1: 执行检索 ==========


async def search_node(state: SearchState, config) -> Dict[str, Any]:
    """
    拿 current_search_query 去 Elasticsearch 查询，
    把查到的文本追加到 accumulated_context（去重）。
    """
    query = state.get("current_search_query", "")
    kb_ids = state.get("kb_ids")
    top_k = state.get("top_k", 10)
    retry_count = state.get("retry_count", 0)

    logger.info(
        f"[es_search_subgraph] search_node: query='{query}', "
        f"retry={retry_count}, kb_ids={kb_ids}"
    )

    # 构建 category 过滤条件
    filters = None
    if not state.get("broaden_search"):
        cat_l1 = state.get("category_l1")
        cat_l2 = state.get("category_l2")
        if cat_l1 or cat_l2:
            filters = {}
            if cat_l1:
                filters["category_l1"] = cat_l1
            if cat_l2:
                filters["category_l2"] = cat_l2

    logger.info(
        f"[es_search_subgraph] search_node: filters={filters}, "
        f"broaden_search={state.get('broaden_search', False)}"
    )

    retriever = _get_retriever()
    response = retriever.run(
        query_text=query,
        top_k=top_k,
        kb_ids=kb_ids,
        filters=filters,
    )

    hits = response.get("hits", [])
    total = response.get("total", 0)

    # 空结果 → 直接标记充足（没必要继续搜）
    if not hits:
        logger.info("[es_search_subgraph] search_node: 无结果，标记 is_sufficient=True")
        return {
            "is_sufficient": True,
        }

    # 去重追加到累积上下文
    accumulated = list(state.get("accumulated_context", []))
    seen_ids = set(state.get("seen_chunk_ids", []))
    new_count = 0

    for hit in hits:
        chunk_id = hit.get("chunk_id", "")
        if chunk_id and chunk_id in seen_ids:
            continue
        accumulated.append(hit)
        if chunk_id:
            seen_ids.add(chunk_id)
        new_count += 1

    logger.info(
        f"[es_search_subgraph] search_node: {total} hits, "
        f"{new_count} new unique -> accumulated={len(accumulated)}"
    )

    return {
        "accumulated_context": accumulated,
        "seen_chunk_ids": list(seen_ids),
    }


# ========== 节点 2: 反思评估 ==========


async def evaluate_node(state: SearchState, config) -> Dict[str, Any]:
    """
    把 original_query 和 accumulated_context 喂给 LLM，
    让它评估"信息够了吗？"
    """
    original_query = state.get("original_query", "")
    accumulated = state.get("accumulated_context", [])
    retry_count = state.get("retry_count", 0)

    # 拼接上下文摘要（限制长度）
    context_text = _format_context_for_eval(accumulated, max_chars=8000)

    user_message = (
        f"【用户的原始提问】\n{original_query}\n\n"
        f"【已有参考资料】（共 {len(accumulated)} 条）\n{context_text}"
    )

    logger.info(
        f"[es_search_subgraph] evaluate_node: retry={retry_count}, "
        f"context_len={len(context_text)}"
    )

    # 调用 LLM（no_think 模式，非流式）
    try:
        client = get_llm_client()
        resp = await client.chat.completions.create(
            model=settings.VLLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SEARCH_EVALUATOR_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=256,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        raw_output = resp.choices[0].message.content.strip()
        logger.info(f"[es_search_subgraph] evaluate_node LLM output: {raw_output}")

    except Exception as e:
        logger.error(f"[es_search_subgraph] evaluate_node LLM error: {e}")
        # LLM 调用失败 → 安全退出
        return {"is_sufficient": True}

    # 解析 JSON
    eval_result = _parse_eval_json(raw_output)
    status = eval_result.get("status", "sufficient")
    next_query = eval_result.get("next_query", "")
    action = eval_result.get("action", "retry_query") if status != "sufficient" else ""

    is_sufficient = status == "sufficient"

    logger.info(
        f"[es_search_subgraph] evaluate_node: status={status}, "
        f"is_sufficient={is_sufficient}, action={action}, next_query='{next_query}'"
    )

    result: Dict[str, Any] = {
        "is_sufficient": is_sufficient,
        "retry_count": retry_count + 1,
        "evaluate_action": action if not is_sufficient else "",
    }

    if not is_sufficient and next_query:
        result["next_query"] = next_query

    return result


# ========== 辅助函数 ==========


def _format_context_for_eval(accumulated: List[Dict[str, Any]], max_chars: int = 8000) -> str:
    """
    将累积的检索结果格式化为评估 LLM 可读的文本。
    如果总字符数超过 max_chars，只保留前面的（相关度更高）。
    """
    parts = []
    total_len = 0

    for i, hit in enumerate(accumulated, 1):
        text = hit.get("text", "")
        source = hit.get("source_file", "")
        score = hit.get("score", 0)
        title = hit.get("title", "")

        header = f"[{i}]"
        if title:
            header += f" [{title}]"
        if source:
            header += f" 来源: {source}"
        header += f" (相关度: {score:.2f})"

        entry = f"{header}\n{text}\n"

        if total_len + len(entry) > max_chars:
            break

        parts.append(entry)
        total_len += len(entry)

    return "\n".join(parts)


def _parse_eval_json(raw: str) -> Dict[str, str]:
    """
    从 LLM 输出中解析 JSON 评估结果。
    容错：处理 markdown 代码块包裹、多余文本等。
    解析失败时返回 sufficient（安全退出）。
    """
    # 尝试从 markdown 代码块中提取
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)

    # 直接找 JSON 对象
    brace_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not brace_match:
        logger.warning(f"[es_search_subgraph] JSON parse failed: {raw}")
        return {"status": "sufficient", "next_query": ""}

    try:
        data = json.loads(brace_match.group())
        # 验证字段
        if data.get("status") not in ("sufficient", "insufficient"):
            data["status"] = "sufficient"
        if "next_query" not in data:
            data["next_query"] = ""
        if "action" not in data:
            data["action"] = "retry_query"
        if data.get("action") not in ("retry_query", "retry_tags", "retry_broad", ""):
            data["action"] = "retry_query"
        return data
    except json.JSONDecodeError:
        logger.warning(f"[es_search_subgraph] JSON decode failed: {raw}")
        return {"status": "sufficient", "next_query": ""}
