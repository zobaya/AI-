"""
ES 检索子图状态定义
"""
from typing import List, Optional, Dict, Any

from typing_extensions import TypedDict


class SearchState(TypedDict):
    """es_search 子图专属状态"""

    # 输入
    original_query: str  # 用户的原始搜索词（来自主 Agent tool_call）
    current_search_query: str  # 当前这轮去 ES 搜的关键词（可能被评估节点改写）
    kb_ids: Optional[List[str]]  # 知识库 ID 过滤
    top_k: int  # 返回数量

    # 累积
    accumulated_context: List[Dict[str, Any]]  # 累积查到的所有文档片段
    seen_chunk_ids: List[str]  # 已见过的 chunk_id，用于去重

    # 标签分类
    category_l1: Optional[int]  # 当前使用的 L1 标签 ID（null 表示不加过滤）
    category_l2: Optional[List[int]]  # 当前使用的 L2 标签 ID 列表
    tried_tags: List[Dict[str, Any]]  # 已尝试过的标签组合 [{l1: ..., l2: [...]}]
    tag_retry_count: int  # 标签重试次数（超过阈值后放弃标签）
    broaden_search: bool  # 是否放弃标签过滤（全量搜索）

    # 控制
    retry_count: int  # 已经重试了几次（防止死循环）
    is_sufficient: bool  # 评估结果：信息是否充足
    next_query: str  # 下一轮搜索关键词（insufficient 时由评估节点生成）
    evaluate_action: str  # 评估节点的路由动作: retry_query / retry_tags / retry_broad
