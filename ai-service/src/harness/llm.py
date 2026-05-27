"""
LLM 客户端 - 支持 Tool Calling 的 vLLM 接口

核心能力：
1. 流式 Tool Calling：Qwen3-8B + hermes parser 原生输出 tool_calls
2. Think 标签处理：兼容 reasoning_content 字段和 <think\\> 标签两种格式
3. 非流式调用：用于简单场景
"""
import logging
import json
from typing import AsyncGenerator, List, Dict, Any, Optional

from openai import AsyncOpenAI

from core.config import settings

logger = logging.getLogger(__name__)

# ---------- 客户端单例 ----------

_client: Optional[AsyncOpenAI] = None


def get_llm_client() -> AsyncOpenAI:
    """获取异步 OpenAI 客户端（复用连接池）"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.VLLM_BASE_URL + "/v1",
            api_key="none",
            timeout=120.0,
        )
    return _client


# ---------- 流式 Tool Calling ----------


async def stream_chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 0.7,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    流式调用 LLM，支持 Tool Calling。

    Yields:
        {"type": "thinking", "content": "..."}  -- 思考内容
        {"type": "text", "content": "..."}      -- 普通文本
        {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}  -- 工具调用
        {"type": "done"}                        -- 流结束

    关键点：
    - vLLM + hermes parser 会在 delta.tool_calls 中输出结构化调用
    - Qwen3: 思考内容在 reasoning_content 字段
    - Qwen3.5: 思考内容在 reasoning 字段
    - 两者 content 都是回答
    - tool_calls 是增量拼接的（第一个 delta 有 name，后续 delta 拼接 arguments）
    """
    client = get_llm_client()

    # 动态 max_tokens：根据输入长度预留足够的输出空间
    total_chars = sum(len(str(m.get("content", ""))) for m in messages if m.get("content"))
    estimated_input = int(total_chars / 1.5)
    max_tokens = min(
        settings.VLLM_MAX_TOKENS,
        max(2048, settings.VLLM_MAX_MODEL_LEN - estimated_input - 4096),
    )

    kwargs: Dict[str, Any] = {
        "model": settings.VLLM_MODEL_NAME,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream_options": {"include_usage": True},
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    logger.info(f"[LLM] stream_chat_with_tools, messages={len(messages)}, has_tools={tools is not None}")

    # 增量拼接 tool_calls
    pending_tool_calls: Dict[int, Dict[str, Any]] = {}

    try:
        response = await client.chat.completions.create(**kwargs)

        async for chunk in response:
            if not chunk.choices:
                # usage 信息在流结束时通过空 choices 的 chunk 返回
                if chunk.usage:
                    yield {
                        "type": "usage",
                        "prompt_tokens": chunk.usage.prompt_tokens or 0,
                        "completion_tokens": chunk.usage.completion_tokens or 0,
                    }
                continue

            delta = chunk.choices[0].delta

            # 1) 处理 thinking（思考内容在独立字段，content 均为回答）
            #    Qwen3:   delta.reasoning_content
            #    Qwen3.5: delta.reasoning
            #
            # 【Qwen3 旧写法】
            # reasoning = getattr(delta, "reasoning_content", None)
            #
            # 【Qwen3.5 新写法】
            # reasoning = getattr(delta, "reasoning", None)
            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning:
                yield {"type": "thinking", "content": reasoning}
                # 注意：不能 continue，同一个 delta 可能同时有 content 或 tool_calls

            # 2) 处理 tool_calls（增量拼接）
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in pending_tool_calls:
                        pending_tool_calls[idx] = {
                            "id": tc.id or "",
                            "name": getattr(tc.function, "name", None) or "",
                            "arguments": getattr(tc.function, "arguments", "") or "",
                        }
                    else:
                        # 增量拼接
                        if tc.id:
                            pending_tool_calls[idx]["id"] = tc.id
                        fn = tc.function
                        if fn and fn.name:
                            pending_tool_calls[idx]["name"] = fn.name
                        if fn and fn.arguments:
                            pending_tool_calls[idx]["arguments"] += fn.arguments
                continue

            # 3) 处理普通 content
            content = delta.content
            if content:
                yield {"type": "text", "content": content}

        # 流结束，yield 所有完整的 tool_calls
        for idx in sorted(pending_tool_calls.keys()):
            tc_data = pending_tool_calls[idx]
            # 解析 arguments JSON
            try:
                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except json.JSONDecodeError:
                logger.warning(f"[LLM] Failed to parse tool arguments: {tc_data['arguments']}")
                args = {}

            yield {
                "type": "tool_call",
                "id": tc_data["id"],
                "name": tc_data["name"],
                "arguments": args,
            }

        yield {"type": "done"}

    except Exception as e:
        logger.error(f"[LLM] stream_chat_with_tools error: {e}")
        raise


# ---------- 非流式调用 ----------


async def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """
    非流式调用 LLM，返回完整响应。

    Returns:
        {
            "content": "文本内容" | None,
            "tool_calls": [{"id": "...", "name": "...", "arguments": {...}}] | None,
            "thinking": "思考内容" | None,
        }
    """
    client = get_llm_client()

    # 动态 max_tokens：根据输入长度预留足够的输出空间
    total_chars = sum(len(str(m.get("content", ""))) for m in messages if m.get("content"))
    estimated_input = int(total_chars / 1.5)
    max_tokens = min(
        settings.VLLM_MAX_TOKENS,
        max(2048, settings.VLLM_MAX_MODEL_LEN - estimated_input - 4096),
    )

    kwargs: Dict[str, Any] = {
        "model": settings.VLLM_MODEL_NAME,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        result: Dict[str, Any] = {
            "content": msg.content,
            "tool_calls": None,
            "thinking": None,
        }

        # 提取 thinking（reasoning_content）
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            result["thinking"] = reasoning

        # 提取 tool_calls
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                    if isinstance(tc.function.arguments, str)
                    else tc.function.arguments,
                }
                for tc in msg.tool_calls
            ]

        return result

    except Exception as e:
        logger.error(f"[LLM] chat_with_tools error: {e}")
        raise


# ---------- 查询改写（no_think 模式） ----------


# REWRITE_SYSTEM = (
#     "你是一个意图保留与指代消解专家。"
#     "你的唯一任务是将用户的口语化提问改写为一个脱离上下文也能独立理解的精准句子。\n\n"
#     "核心要求：\n"
#     "1. 补全所有代词（如把它替换成具体的设备名或概念）\n"
#     "2. 绝对保留用户原有的操作意图动词！如果用户说'计算一下'、'查询'、'搜索'，"
#     "改写后的句子必须保留这些动词\n"
#     "3. 不要自己回答问题，只做改写\n"
#     "4. 直接输出改写后的句子，不要任何解释"
# )

# REWRITE_SYSTEM = (
#     "你是一个无情的文本改写与指代消解算法组件，绝对不是对话助手！"
#     "你的唯一任务是将用户的最新提问改写为一个脱离上下文也能独立理解的精准句子。\n\n"
#     "核心要求：\n"
#     "1. 【判断独立性】：如果当前提问是全新话题，原样输出或仅作句法润色，严禁生搬硬套前文实体。\n"
#     "2. 【补全代词】：仅在确定存在上下文指代关系时，才将代词替换为前文实体。\n"
#     "3. 【保留意图】：绝对保留用户原有的操作意图动词。\n"
#     "4. 【纯净输出】：直接输出改写结果，绝对不要自己回答问题，不要任何解释。\n\n"
#     "⚠️【极度重要：特殊场景处理】⚠️\n"
#     "- 如果用户的输入是问候语（如“你好”、“在吗”）、感谢语（如“谢谢”、“好的”）、或纯闲聊：\n"
#     "  必须【原样输出】！\n"
#     "  绝对严禁生成类似“你好，需要我帮您查询关于[前文实体]的信息吗？”这种客服式回答！你的任务是改写，不是搭话！"
# )

REWRITE_SYSTEM = (
    "你是一个无情的文本改写与指代消解算法组件，绝对不是对话助手！\n"
    "你的唯一任务是：评估用户的【最新提问】，并在必要时进行指代消解和信息补全，使其成为一个脱离上下文也能独立理解的精准句子。\n\n"
    "🎯 【核心改写法则（按顺序严格执行）】\n"
    "1. 【评估完整性（原样优先）】：如果最新提问本身主谓宾完整，或者是一个全新的独立话题，**绝对严禁**生搬硬套前文实体，必须【原样输出】！\n"
    "2. 【意图继承（顺承补全）】：如果用户的最新输入是简短的确认/拒绝词（如“需要”、“好的”、“可以”、“不用了”），你必须查看上一轮【助手】的提议或问句，将其还原为完整的动作指令。\n"
    "3. 【指代消解】：仅当最新提问中包含代词（如“它”、“这个”、“刚才的”）或明显缺失主语/宾语时，才从【对话历史】中提取最近的相关实体进行替换或补全。\n"
    "4. 【保留原意】：绝对保留用户原有的操作意图动词（如：计算、查一下、搜索等），不要做过度发散和润色。\n"
    "5. 【纯净输出】：直接输出改写后的句子，绝对不要回答问题，不要输出任何解释词！\n\n"
    "⚠️ 【极度重要：不可改写的特殊场景】 ⚠️\n"
    "- 纯问候/感谢/语气词（如“你好”、“在吗”、“谢谢”）：必须【原样输出】！严禁生成类似“你好，需要查询[前文]吗？”这种搭话。\n"
    "（注意：如果“好的”是对助手提议的确认，请按法则2处理；如果是对话结束的客套，则原样输出。）\n\n"
    "👇 【改写决策演示示例】 👇\n"
    "历史：助手问了“需要我帮您把这些数据生成详细的报告吗？”\n"
    "最新提问：“需要”\n"
    "输出：请帮我把这些数据生成详细的报告。\n"
    "（原因：用户在回应助手的提议，必须继承意图补全完整指令）\n\n"

    "历史：用户问了“0Cr25Al5的密度是多少”\n"
    "最新提问：“那它的电阻率呢？”\n"
    "输出：0Cr25Al5的电阻率呢？\n"
    "（原因：存在代词“它”，需要消解）\n\n"

    "历史：用户问了“怎么预防高处坠落”\n"
    "最新提问：“发生火灾怎么办”\n"
    "输出：发生火灾怎么办\n"
    "（原因：全新完整话题，绝对不要把高处坠落塞进去）\n\n"

    "历史：用户问了“知识库有操作指南吗”\n"
    "最新提问：“谢谢你”\n"
    "输出：谢谢你\n"
    "（原因：闲聊感谢，原样输出）"
)


async def rewrite_query(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    查询改写：将口语化提问转为精准搜索 query。

    使用 Qwen3 no_think 模式（enable_thinking=False），
    不绑定 tools，纯文本输出，快速轻量。

    Args:
        user_query: 用户原始提问
        history: 对话历史 [{"role": "user/assistant", "content": "..."}]

    Returns:
        改写后的查询字符串。失败时返回原始 user_query。
    """
    client = get_llm_client()

    # 构建 messages
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": REWRITE_SYSTEM},
    ]

    # 有历史时，把历史拼入 user message 让 LLM 做上下文补全
    if history:
        history_text = "\n".join(
            f"{h.get('role', 'user')}: {h.get('content', '')}"
            for h in history[-5:]
        )
        user_content = (
            f"【对话历史】:\n{history_text}\n\n"
            f"【用户最新提问】:\n{user_query}\n\n"
            f"请结合历史上下文，将用户最新提问改写为一个独立、完整、精准的句子。"
            f"必须保留原始操作意图动词（如'计算'、'查询'、'搜索'等）。"
            f"直接输出改写后的句子，不要任何解释。"
        )
    else:
        user_content = (
            f"请将以下口语化提问改写为精准的独立句子。"
            f"必须保留原始操作意图动词（如'计算'、'查询'、'搜索'等）。"
            f"直接输出改写后的句子，不要任何解释。\n\n"
            f"原始提问：{user_query}"
        )

    messages.append({"role": "user", "content": user_content})

    try:
        response = await client.chat.completions.create(
            model=settings.VLLM_MODEL_NAME,
            messages=messages,
            stream=False,
            temperature=0.7,
            max_tokens=256,
            # no_think 模式：关闭 Qwen3 思考，快速输出纯文本
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        content = response.choices[0].message.content
        if content:
            # 清理可能残留的 think 标签
            import re
            cleaned = re.sub(r"<think[^>]*>.*?</think[^>]*>", "", content, flags=re.S).strip()
            return cleaned or user_query
        return user_query

    except Exception as e:
        logger.warning(f"[LLM] rewrite_query failed, using original: {e}")
        return user_query


# ---------- 猜你想问（no_think 模式） ----------


MAYBE_SYSTEM = (
    "你是一个专门生成对话标题和后续推荐问题的辅助智能体。请根据当前的【用户提问】与【助手回答】，生成简短标题和后续追问。\n\n"
    "【输出格式严格要求】（绝对不要输出多余的引导语）\n"
    "第一行：15字以内的简短标题（概括核心主题，严禁以标点符号结尾）\n"
    "第二行：空一行\n"
    "第三行及以后：每行1个推荐问题（生成2-3个）\n\n"
    "🎯 【推荐问题生成规范（角色与视角极其重要）】\n"
    "这些推荐问题将作为按钮展示给【真实用户】，供用户点击后继续向AI提问！\n"
    "1. 必须是【用户求助视角】：问题必须是用户遇到具体疑惑时向AI发出的真实求问，口语化、接地气。\n"
    "2. 绝对严禁【客服反问语气】：严禁生成任何AI助理询问用户的句子！绝对不能出现“有什么需要帮助吗”、“您需要了解什么信息”、“今天有什么特别需要解决的问题吗”等客服废话。\n"
    "3. 紧扣上下文细节：必须针对刚才助手回答的具体内容进行深度追问、横向扩展或参数替换，不要泛泛而谈。\n\n"
    "❌ 错误示例（角色错位/客服废话）：有什么问题需要帮助吗？ / 您需要了解什么信息？ / 今天有什么特别需要解决的？\n"
    "✅ 正确示例（真实用户追问）：那我具体第一步该怎么操作？ / 你刚才说的那个数值是怎么算出来的？ / 如果现场没有领导在场该怎么办？\n\n"
    "【示例输出】\n"
    "高处坠落应急处置\n\n"
    "应急处置卡有哪些注意事项\n"
    "如何预防高处坠落事故"
)


async def generate_maybe_questions(
    user_query: str,
    answer: str,
) -> Dict[str, Any]:
    """
    根据用户提问和助手回答，生成标题和推荐问题。

    使用 no_think 模式，快速输出纯文本。

    Returns:
        {"title": "标题", "questions": ["问题一", "问题二"]} 或空 dict。
    """
    client = get_llm_client()

    # 截断过长的回答，避免超出上下文
    truncated_answer = answer[:2000] if len(answer) > 2000 else answer

    messages = [
        {"role": "system", "content": MAYBE_SYSTEM},
        {"role": "user", "content": f"用户提问：{user_query}\n\n助手回答：{truncated_answer}"},
    ]

    try:
        response = await client.chat.completions.create(
            model=settings.VLLM_MODEL_NAME,
            messages=messages,
            stream=False,
            temperature=0.7,
            max_tokens=256,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        content = response.choices[0].message.content
        if content:
            import re
            cleaned = re.sub(r"<think[^>]*>.*?</think[^>]*>", "", content, flags=re.S).strip()
            # 解析：第一行为标题，空行之后为推荐问题
            lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
            result = {}
            if lines:
                result["title"] = lines[0][:15]
            if len(lines) > 1:
                result["questions"] = lines[1:]
            return result
        return {}

    except Exception as e:
        logger.warning(f"[LLM] generate_maybe_questions failed: {e}")
        return {}
