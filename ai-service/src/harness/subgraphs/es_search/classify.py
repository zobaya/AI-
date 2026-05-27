"""
ES 检索子图 - 分类节点

根据用户问题和分类体系（从 Django API 动态拉取），用 LLM 判断应该使用哪些标签过滤。
支持重试时换标签：传入已尝试过的标签列表，LLM 会选择不同的组合。

进度事件由 subgraph.py 的 _dispatch_node_progress 统一发送，
节点内部不发 adispatch_custom_event，避免与 wrapper 层重复。
"""
import json
import logging
import os
import re
import time
from typing import Dict, Any, List, Optional

import httpx

from src.harness.subgraphs.es_search.state import SearchState
from src.harness.subgraphs.es_search.prompts import CATEGORY_CLASSIFY_PROMPT
from src.harness.llm import get_llm_client

from core.config import settings

logger = logging.getLogger(__name__)

# ========== 分类体系加载 ==========

_cache_text: Optional[str] = None
_cache_time: float = 0
_cache_id_to_name: Dict[int, str] = {}  # id → name 映射，供进度消息显示
_CACHE_TTL: float = 300.0  # 5 分钟缓存


def _format_categories(categories: List[Dict[str, Any]]) -> str:
    """将分类列表格式化为 LLM 友好的文本（包含 ID）"""
    parts = []
    for cat in categories:
        l1_id = cat.get("id", "")
        l1 = cat.get("category_l1", "")
        desc = cat.get("description", "")
        parts.append(f"- [{l1_id}] {l1}：{desc}")

        for l2 in cat.get("category_l2", []):
            l2_id = l2.get("id", "")
            name = l2.get("name", "")
            l2_desc = l2.get("description", "")
            parts.append(f"  - [{l2_id}] {name}：{l2_desc}")

    return "\n".join(parts)


def _build_id_to_name(categories: List[Dict[str, Any]]) -> Dict[int, str]:
    """从分类列表构建 id → name 映射"""
    mapping: Dict[int, str] = {}
    for cat in categories:
        l1_id = cat.get("id")
        l1_name = cat.get("category_l1", "")
        if l1_id and l1_name:
            mapping[l1_id] = l1_name
        for l2 in cat.get("category_l2", []):
            l2_id = l2.get("id")
            l2_name = l2.get("name", "")
            if l2_id and l2_name:
                mapping[l2_id] = l2_name
    return mapping


def get_tag_name(tag_id: Optional[int]) -> str:
    """根据标签 ID 查询名称，找不到时返回字符串形式的 ID"""
    if tag_id is None:
        return ""
    return _cache_id_to_name.get(tag_id, str(tag_id))


def _load_categories_from_file() -> tuple[str, List[Dict[str, Any]]]:
    """
    Fallback：从本地 categories.json 加载分类体系。
    仅在 API 不可用时使用。

    Returns:
        (格式化文本, 原始 categories 列表)
    """
    json_path = os.path.join(os.path.dirname(__file__), "categories.json")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning(f"[classify] categories.json not found: {json_path}")
        return "", []
    except json.JSONDecodeError as e:
        logger.error(f"[classify] categories.json parse error: {e}")
        return "", []

    categories = data.get("categories", [])
    if not categories:
        return "", []

    logger.info(f"[classify] Fallback: loaded {len(categories)} L1 categories from file")
    return _format_categories(categories), categories


async def _fetch_category_registry() -> str:
    """
    从 Django API 获取分类体系并格式化为文本。

    带 5 分钟 TTL 缓存，API 不可用时回退到本地 categories.json。
    """
    global _cache_text, _cache_time, _cache_id_to_name

    now = time.time()
    if _cache_text is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache_text

    try:
        headers = {"Content-Type": "application/json"}
        service_token = getattr(settings, "SERVICE_AUTH_TOKEN", None)
        if service_token:
            headers["Authorization"] = f"Service {service_token}"
        else:
            logger.warning("[classify] SERVICE_AUTH_TOKEN is None, API call will likely fail 401")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.DJANGO_API_BASE_URL}/api/tags/internal/registry/",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        categories = data.get("categories", [])
        if not categories:
            logger.warning("[classify] API returned empty categories")
            _cache_text = ""
            _cache_time = now
            return ""

        _cache_text = _format_categories(categories)
        _cache_id_to_name = _build_id_to_name(categories)
        _cache_time = now
        logger.info(
            f"[classify] Loaded {len(categories)} L1 categories from API"
        )
        return _cache_text

    except Exception as e:
        logger.warning(f"[classify] API fetch failed: {e}, falling back to file")
        text, categories = _load_categories_from_file()
        if text:
            _cache_text = text
            _cache_id_to_name = _build_id_to_name(categories)
            _cache_time = now
        return text


def invalidate_cache():
    """清除标签注册表缓存（由 Django 标签 CUD 操作后调用）"""
    global _cache_text, _cache_time, _cache_id_to_name
    _cache_text = None
    _cache_time = 0
    _cache_id_to_name = {}
    logger.info("[classify] Tag registry cache invalidated")


def _format_tried_tags(tried_tags: List[Dict[str, Any]]) -> str:
    """将已尝试过的标签格式化为文本（使用 ID）"""
    if not tried_tags:
        return "（无，这是首次分类）"

    lines = []
    for i, tag in enumerate(tried_tags, 1):
        l1 = tag.get("l1", "null")
        l2 = tag.get("l2", [])
        l2_str = ", ".join(str(v) for v in l2) if l2 else "null"
        lines.append(f"{i}. L1_id={l1}, L2_id=[{l2_str}]")
    return "\n".join(lines)


def _parse_classify_json(raw: str) -> Dict[str, Any]:
    """
    从 LLM 输出中解析分类 JSON 结果。
    容错处理：markdown 代码块、多余文本等。
    """
    # 尝试从 markdown 代码块中提取
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)

    # 直接找 JSON 对象
    brace_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not brace_match:
        logger.warning(f"[classify] JSON parse failed: {raw}")
        return {"category_l1": None, "category_l2": None}

    try:
        data = json.loads(brace_match.group())

        # category_l1: 转为整数或 None
        l1 = data.get("category_l1")
        if l1 is not None:
            try:
                l1 = int(l1)
            except (ValueError, TypeError):
                l1 = None
        data["category_l1"] = l1

        # category_l2: 转为整数列表或 None
        l2 = data.get("category_l2")
        if l2 is not None:
            if isinstance(l2, (int, str)):
                try:
                    l2 = [int(l2)]
                except (ValueError, TypeError):
                    l2 = None
            elif isinstance(l2, list):
                converted = []
                for v in l2:
                    try:
                        converted.append(int(v))
                    except (ValueError, TypeError):
                        pass
                l2 = converted if converted else None
        data["category_l2"] = l2

        return data
    except json.JSONDecodeError:
        logger.warning(f"[classify] JSON decode failed: {raw}")
        return {"category_l1": None, "category_l2": None}


# ========== 分类节点 ==========


async def classify_node(state: SearchState, config) -> Dict[str, Any]:
    """
    分类节点：根据用户问题判断应该使用哪些标签来过滤 ES 检索。

    - 首次调用：从完整分类体系中选择
    - 重试调用：避开已尝试的标签，选择新组合
    - 无法分类时返回 null → 后续 search 不加 filter
    """
    query = state.get("original_query", "")
    tried_tags = state.get("tried_tags", [])
    tag_retry_count = state.get("tag_retry_count", 0)

    # 如果标签重试次数已达上限 → 放弃标签，全量搜索
    if tag_retry_count >= 2:
        logger.info(f"[classify] tag_retry_count={tag_retry_count} >= 2, broaden search")
        return {
            "category_l1": None,
            "category_l2": None,
            "broaden_search": True,
        }

    # 加载分类体系（从 Django API 拉取，带缓存）
    registry_text = await _fetch_category_registry()
    if not registry_text:
        # 无分类体系 → 直接全量搜索
        logger.info("[classify] No category registry, skip classification")
        return {
            "category_l1": None,
            "category_l2": None,
        }

    # 构建 prompt
    prompt = CATEGORY_CLASSIFY_PROMPT.format(
        category_registry=registry_text,
        tried_tags=_format_tried_tags(tried_tags),
    )

    # 调用 LLM（no_think 模式，快速分类）
    try:
        client = get_llm_client()
        resp = await client.chat.completions.create(
            model=settings.VLLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"问题：{query}"},
            ],
            temperature=0.1,
            max_tokens=256,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        raw_output = resp.choices[0].message.content.strip()
        logger.info(f"[classify] LLM output: {raw_output}")

    except Exception as e:
        logger.error(f"[classify] LLM error: {e}")
        return {
            "category_l1": None,
            "category_l2": None,
        }

    # 解析 JSON
    result = _parse_classify_json(raw_output)
    category_l1 = result.get("category_l1")
    category_l2 = result.get("category_l2")
    reason = result.get("reason", "")

    logger.info(
        f"[classify] result: L1_id={category_l1}, L2_id={category_l2}, "
        f"reason={reason}"
    )

    # 记录已尝试的标签
    new_tried = list(tried_tags)
    if category_l1 or category_l2:
        new_tried.append({
            "l1": category_l1,
            "l2": category_l2 or [],
        })

    return {
        "category_l1": category_l1,
        "category_l2": category_l2,
        "tried_tags": new_tried,
        "tag_retry_count": tag_retry_count + 1 if (category_l1 or category_l2) else tag_retry_count,
    }
