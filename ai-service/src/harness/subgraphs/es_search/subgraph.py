"""
ES 检索子图 - LangGraph StateGraph 定义 + 入口函数

子图结构：
    classify → search → evaluate → [条件路由]
                                    ├─ sufficient 或 retry≥3 → END
                                    ├─ retry_query → prepare_search → search（换 query，保持标签）
                                    ├─ retry_tags → classify（换标签）
                                    └─ retry_broad → prepare_broad → search（放弃标签，全量搜索）
"""
import logging
from typing import List, Optional

from langgraph.graph import StateGraph, END
from langchain_core.callbacks.manager import adispatch_custom_event

from src.harness.subgraphs.es_search.state import SearchState
from src.harness.subgraphs.es_search.nodes import search_node, evaluate_node
from src.harness.subgraphs.es_search.classify import classify_node

logger = logging.getLogger(__name__)

# ========== 常量 ==========

MAX_RETRY = 3  # 最大重试次数


# ========== 节点进度事件 ==========


async def _dispatch_node_progress(node_name: str, output: dict, config):
    """
    根据子图节点输出，用主图 config 发送 SSE 进度事件。

    之所以不在子图节点内部发事件，是因为 ainvoke 时子图的
    adispatch_custom_event 无法冒泡到主图的 astream_events。
    所以在 wrapper 层用主图 config 直接发，保证事件能到达前端。
    """
    if node_name == "classify":
        broaden = output.get("broaden_search", False)
        cat_l1 = output.get("category_l1")
        cat_l2 = output.get("category_l2")
        if broaden:
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": "🔀 已尝试多个分类，切换为全量搜索...",
            }, config=config)
        elif cat_l1:
            from src.harness.subgraphs.es_search.classify import get_tag_name
            l1_name = get_tag_name(cat_l1)
            l2_str = ""
            if cat_l2:
                l2_names = " > ".join(get_tag_name(v) for v in cat_l2)
                l2_str = f" > {l2_names}"
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": f"✅ 分类：{l1_name}{l2_str}",
            }, config=config)
        else:
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": "ℹ️ 无法确定分类，全量搜索",
            }, config=config)

    elif node_name == "search":
        accumulated = output.get("accumulated_context", [])
        is_sufficient = output.get("is_sufficient", False)
        if is_sufficient and not accumulated:
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": "⚠️ 未找到相关文档",
            }, config=config)
        elif accumulated:
            count = len(accumulated)
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": f"🔍 检索到 {count} 条结果",
            }, config=config)

    elif node_name == "evaluate":
        is_sufficient = output.get("is_sufficient", True)
        action = output.get("evaluate_action", "")
        next_q = output.get("next_query", "")
        if is_sufficient:
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": "✅ 评估通过，信息充足",
            }, config=config)
        elif action == "retry_tags":
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": "🔄 结果不相关，尝试换分类标签...",
            }, config=config)
        elif action == "retry_broad":
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": "🔄 切换全量搜索...",
            }, config=config)
        else:
            q_preview = next_q[:30] if next_q else ""
            await adispatch_custom_event("progress", {
                "node": "es_search",
                "message": f"🔄 信息不足，补充检索「{q_preview}」...",
            }, config=config)


# ========== 条件路由 ==========


def route_after_evaluate(state: SearchState) -> str:
    """
    评估节点后的条件路由：
    - is_sufficient == True → 结束
    - retry_count >= MAX_RETRY → 结束（安全退出）
    - evaluate_action == "retry_query" → 换搜索词，保持标签
    - evaluate_action == "retry_tags" → 换标签，回到 classify
    - evaluate_action == "retry_broad" → 放弃标签，全量搜索
    """
    if state.get("is_sufficient", False):
        logger.info("[es_search_subgraph] route: sufficient → END")
        return "end"

    retry_count = state.get("retry_count", 0)
    if retry_count >= MAX_RETRY:
        logger.info(
            f"[es_search_subgraph] route: retry_count={retry_count} >= {MAX_RETRY} → END"
        )
        return "end"

    action = state.get("evaluate_action", "retry_query")

    if action == "retry_tags":
        logger.info("[es_search_subgraph] route: retry_tags → classify")
        return "classify"
    elif action == "retry_broad":
        logger.info("[es_search_subgraph] route: retry_broad → prepare_broad")
        return "broad"
    else:
        # retry_query 或默认 → 换搜索词
        next_q = state.get("next_query", "")
        if not next_q:
            logger.warning("[es_search_subgraph] route: no next_query → END")
            return "end"
        logger.info(
            f"[es_search_subgraph] route: retry_query, "
            f"next_query='{next_q}' → search"
        )
        return "search"


# ========== prepare_search: 用 next_query 更新 current_search_query ==========


def prepare_search_node(state: SearchState, config) -> dict:
    """
    在 evaluate → search 之间插入的预处理节点：
    将 next_query 赋给 current_search_query，清空 next_query。
    保持标签不变。
    """
    next_q = state.get("next_query", "")
    logger.info(f"[es_search_subgraph] prepare_search: next_query='{next_q}'")
    return {
        "current_search_query": next_q,
        "next_query": "",
    }


# ========== prepare_broad: 放弃标签，全量搜索 ==========


def prepare_broad_node(state: SearchState, config) -> dict:
    """
    放弃标签过滤，清空 category 并设置 broaden_search=True。
    将 next_query 赋给 current_search_query。
    """
    next_q = state.get("next_query", "")
    logger.info(
        f"[es_search_subgraph] prepare_broad: next_query='{next_q}', "
        "放弃标签过滤，切换全量搜索"
    )
    return {
        "current_search_query": next_q,
        "next_query": "",
        "category_l1": None,
        "category_l2": None,
        "broaden_search": True,
    }


# ========== 图构建 ==========


def create_es_search_subgraph():
    """
    创建 es_search 反思检索子图。

    流程：
        classify → search → evaluate → [route_after_evaluate]
                                        ├─ "end" → END
                                        ├─ "search" → prepare_search → search（换 query）
                                        ├─ "classify" → classify（换标签）
                                        └─ "broad" → prepare_broad → search（全量搜索）
    """
    wf = StateGraph(SearchState)

    wf.add_node("classify", classify_node)
    wf.add_node("search", search_node)
    wf.add_node("evaluate", evaluate_node)
    wf.add_node("prepare_search", prepare_search_node)
    wf.add_node("prepare_broad", prepare_broad_node)

    wf.set_entry_point("classify")

    # classify → search（固定边）
    wf.add_edge("classify", "search")

    # search → evaluate（固定边）
    wf.add_edge("search", "evaluate")

    # evaluate → 条件路由
    wf.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {
            "end": END,
            "search": "prepare_search",
            "classify": "classify",
            "broad": "prepare_broad",
        },
    )

    # prepare_search → search（循环：换 query）
    wf.add_edge("prepare_search", "search")

    # prepare_broad → search（循环：全量搜索）
    wf.add_edge("prepare_broad", "search")

    return wf.compile()


# 全局子图实例
es_search_subgraph = create_es_search_subgraph()


# ========== 入口函数 ==========


async def run_es_search_subgraph(
    query: str,
    kb_ids: Optional[List[str]] = None,
    top_k: int = 10,
    config=None,
) -> str:
    """
    运行 es_search 子图并返回格式化文本。

    这是被 tool_node 调用的入口函数。
    子图内部执行"分类 → 检索 → 评估 → 补充检索"循环，
    最终将所有累积的 context 格式化为一段干净文本返回。
    """
    initial_state = SearchState(
        original_query=query,
        current_search_query=query,
        accumulated_context=[],
        seen_chunk_ids=[],
        kb_ids=kb_ids,
        top_k=top_k,
        retry_count=0,
        is_sufficient=False,
        next_query="",
        # 标签分类
        category_l1=None,
        category_l2=None,
        tried_tags=[],
        tag_retry_count=0,
        broaden_search=False,
        evaluate_action="",
    )

    invoke_config = {"configurable": {}} if config is None else config

    # 用 astream(stream_mode="updates") 代替 ainvoke，
    # 拿到每个节点的输出后用主图 config 直接发 SSE 事件。
    # 这样绕开了子图内部 adispatch_custom_event 事件无法冒泡到主图的问题。
    final_state = {}

    async for chunk in es_search_subgraph.astream(
        initial_state, config=invoke_config, stream_mode="updates"
    ):
        for node_name, node_output in chunk.items():
            if not node_output:
                continue

            # 合并到最终状态
            final_state.update(node_output)

            # 用主图 config 发送进度事件
            await _dispatch_node_progress(node_name, node_output, config)

    # 提取结果
    accumulated = final_state.get("accumulated_context", [])
    retry_count = final_state.get("retry_count", 0)

    if not accumulated:
        return f"未找到与「{query}」相关的文档。"

    # 格式化为 LLM 可读的文本
    parts = [
        f"搜索「{query}」相关结果（经 {retry_count} 轮检索，"
        f"共 {len(accumulated)} 条）：\n"
    ]

    for i, hit in enumerate(accumulated, 1):
        text = hit.get("text", "")
        source = hit.get("source_file", "")
        score = hit.get("score", 0)
        title = hit.get("title", "")

        header = f"--- 结果 {i} ---"
        if title:
            header += f" [{title}]"
        if source:
            header += f" 来源: {source}"
        header += f" (相关度: {score:.2f})"

        parts.append(header)
        parts.append(text)
        parts.append("")

    return "\n".join(parts)
