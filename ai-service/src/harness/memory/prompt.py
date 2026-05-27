"""
事实抽取 Prompt

使用 LLM 从对话中抽取值得长期记住的事实。
"""

FACT_EXTRACTION_SYSTEM = """\
你是一个记忆管理助手。你的任务是从对话中抽取值得长期记住的"事实"。

## 现有记忆
{existing_facts}

## 本次对话
{conversation}

## 指令
1. 从对话中抽取以下类型的"事实"：
   - preference：用户的偏好（如"我喜欢简洁的回答"）
   - knowledge：用户展示的知识或专长（如"我负责合金材料的质检"）
   - goal：用户的目标或任务（如"我正在准备月度安全报告"）
   - context：用户的背景信息（如"我在研发部门工作"）

2. 为每个事实打置信度（0-1）：
   - 0.9+：用户明确、重复表达的
   - 0.7-0.9：可以合理推断的
   - 0.5-0.7：不太确定的

3. 检查现有记忆，如果有冲突或过时的事实，将其 ID 列入 delete 列表。

## 输出格式（严格 JSON，不要输出任何其他内容）
```json
{{
  "add": [
    {{"fact": "事实内容", "category": "preference", "confidence": 0.9}},
    {{"fact": "事实内容", "category": "knowledge", "confidence": 0.8}}
  ],
  "delete": []
}}
```

如果对话中没有值得记住的事实，返回空的 add 和 delete 列表。
不要编造事实，只抽取用户明确表达或可以合理推断的信息。"""


def build_extraction_prompt(
    messages: list,
    existing_facts: list | None = None,
) -> list:
    """
    构建事实抽取的 messages 列表。

    Args:
        messages: 对话消息 [{"role": "user/assistant", "content": "..."}]
        existing_facts: 现有记忆列表 [{"id": 1, "fact": "...", "category": "..."}, ...]

    Returns:
        LLM messages 列表
    """
    # 格式化现有记忆
    if existing_facts:
        facts_text = "\n".join(
            f"- [ID:{f['id']}] [{f.get('category', 'unknown')}] {f['fact']}"
            for f in existing_facts
        )
    else:
        facts_text = "（无）"

    # 格式化对话
    conv_lines = []
    for msg in messages[-10:]:  # 最多取最后 10 条
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            # 截断过长的消息
            if len(content) > 500:
                content = content[:500] + "..."
            conv_lines.append(f"{role}: {content}")
    conversation_text = "\n".join(conv_lines)

    system_content = FACT_EXTRACTION_SYSTEM.format(
        existing_facts=facts_text,
        conversation=conversation_text,
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "请分析上述对话，抽取值得长期记住的事实。"},
    ]
