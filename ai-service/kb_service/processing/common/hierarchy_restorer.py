"""
LLM 层级还原器 - 修复 PDF Markdown 标题扁平化问题

MinerU 解析 PDF 时将所有识别出的标题统一标记为 #（一级标题），
本模块通过 LLM 分析编号规律和上下文语义，推断真实层级并还原为 ## / ###。
"""
import json
import re
import requests
from typing import List, Dict, Tuple, Optional
from core.config import settings


# SYSTEM_PROMPT = """你是一个专门负责解析和重构文档树状逻辑的顶级算法。你的任务是修复由于 OCR 引擎缺陷导致的 Markdown 标题层级丢失问题。
# 【背景信息】
# 我将给你一组从长篇扫描文档中提取出的"标题骨架"。目前，这些标题全部被错误地统一标记为 `#`（一级标题）。
# 【核心任务】
# 请仔细观察这组骨架中的编号规律（如"第一章"、"一、"、"1"、"1.1"、"(1)"等）和上下文语义逻辑，推断出每个标题在原文中的真实物理层级，并相应地修改行首 `#` 的数量（# 代表一级标题，## 代表二级，### 代表三级）。
# 【严格遵守的铁律】
# 1. **绝对保真**：只能增加行首的 `#` 数量。绝对禁止修改、增删、总结原有标题中的任何汉字、数字、字母或标点。
# 2. **格式锁定**：输入是 JSON 数组，输出也必须是结构完全相同的 JSON 数组，保留原有的 `line`（行号）属性。
# 3. **不要遗漏**：输入有多少个标题元素，输出就必须有多少个，严禁删减。
# 4. **层级限制**：最高使用到三级标题（###），如果遇到更深层级，也统一归入三级。
# 【处理逻辑示例】
# 如果遇到复杂的混合编号，请基于全局逻辑判断：
# 通常 "1" 是 `#`，则 "1.1" 是 `##`， "1.1.1" 是 `###`。
# 通常 "一、" 是 `#`，则 "(一)" 是 `##`， "1." 是 `###`。
#
# 【输出要求】
# 最终的修复结果必须且只能放在 ```json 和 ``` 之间。"""


SYSTEM_PROMPT = """你是一个专门负责解析和重构文档树状逻辑的顶级算法。你的任务是修复由于 OCR 引擎缺陷导致的 Markdown 标题层级丢失问题。

【背景信息】
我将给你一组从长篇扫描文档中提取出的“标题骨架”。目前，这些标题全部被错误地统一标记为 `#`（一级标题）。

【核心任务】
请仔细观察这组骨架中的编号规律（如“前言”、“第一章”、“一、”、“1”、“1.1”、“(1)”等）和上下文语义逻辑，推断出每个标题在原文中的真实物理层级，并相应地修改行首 `#` 的数量（# 代表一级标题，## 代表二级，### 代表三级）。

【严格遵守的铁律（必须执行）】
1. **绝对保真**：只能增加行首的 `#` 数量。绝对禁止修改、增删、总结原有标题中的任何汉字、数字、字母或标点。
2. **格式锁定**：输入是 JSON 数组，输出也必须是结构完全相同的 JSON 数组，保留原有的 `line`（行号）属性。
3. **严禁遗漏**：输入有多少个标题元素，输出就必须有多少个，严禁吞行或删减。
4. **数字层级绝对压制（最高优先级）**：对于带有阿拉伯数字编号的标题，其层级完全由“点号数量”决定，不受任何语义影响！
   - 无点的单数字（如 `1 范围`、`7 外形`）必须是保持同级。
   - 带一个点的双数字（如 `1.1`、`7.4`）必须比单数字低一级（增加一个 `#`）。
   - 带两个点的（如 `1.1.1`）必须比双数字再低一级。
   - **绝对红线**：严禁出现子序号（如 7.4）的级别高于或等于父序号（如 7）的情况！
5. **无编号章节对齐**：像“前言”、“附录”这种没有数字编号的独立章节，应与 `1`、`2` 等顶级大纲保持同级。英文翻译标题可与对应的中文标题保持同级，或统一降级。
6. **层级限制**：最高使用到三级标题（###），如果遇到更深层级（如 1.1.1.1），也统一归入三级。

【处理逻辑示例】
如果遇到复杂的混合编号，请基于全局逻辑判断：
通常 "1" 是 `#`，则 "1.1" 是 `##`， "1.1.1" 是 `###`。
通常 "一、" 是 `#`，则 "(一)" 是 `##`， "1." 是 `###`。

【输出要求】
最终的修复结果必须且只能放在 ```json 和 ``` 之间。"""

USER_PROMPT_TEMPLATE = "请解析并修复以下文档的标题骨架：\n\n{json_string}"


class HierarchyRestorer:
    """LLM 层级还原器（使用 Qwen3-8B）"""

    def __init__(self):
        self.base_url = settings.VLLM_BASE_URL
        self.model = settings.VLLM_MODEL_NAME
        self.timeout = settings.VLLM_TIMEOUT

    def restore(self, markdown: str) -> str:
        """
        对 Markdown 文本执行层级还原

        Args:
            markdown: 原始 Markdown 文本（标题全为 #）

        Returns:
            还原层级后的 Markdown 文本
        """
        # Step 1: 提取标题骨架
        titles = self._extract_titles(markdown)
        if len(titles) <= 1:
            print(f"[HierarchyRestorer] 标题数量={len(titles)}，无需还原")
            return markdown

        print(f"[HierarchyRestorer] 提取到 {len(titles)} 个标题，开始 LLM 还原")

        # Step 2: 调用 LLM 还原层级
        restored_titles = self._call_llm(titles)
        if restored_titles is None:
            print("[HierarchyRestorer] LLM 还原失败，返回原始 Markdown")
            return markdown

        # Step 3: 按行号替换回原 MD
        result = self._apply_restoration(markdown, titles, restored_titles)
        return result

    def _extract_titles(self, markdown: str) -> List[Dict]:
        """
        从 Markdown 中提取所有一级标题骨架

        Returns:
            [{"line": 12, "text": "# 1 范围"}, ...]
        """
        titles = []
        lines = markdown.split('\n')
        for i, line in enumerate(lines):
            # 匹配以 # 开头的标题行（只匹配一级标题，因为 MinerU 输出全是 #）
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                titles.append({
                    "line": i + 1,  # 1-based 行号
                    "text": line,
                })
        return titles

    def _call_llm(self, titles: List[Dict]) -> Optional[List[Dict]]:
        """
        调用 Qwen3-8B 还原标题层级

        Args:
            titles: 标题骨架列表

        Returns:
            还原后的标题列表，失败返回 None
        """
        json_string = json.dumps(titles, ensure_ascii=False, indent=2)
        user_prompt = USER_PROMPT_TEMPLATE.format(json_string=json_string)

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 8192,
                    "chat_template_kwargs": {"enable_thinking": False}
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            raw_content = data["choices"][0]["message"]["content"]

            # 剔除 Qwen3-8B 的思考过程 <think...>...</think >
            cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', raw_content, flags=re.DOTALL)
            # 处理未闭合的 <think > 标签（响应被截断）
            if '<think' in cleaned:
                cleaned = re.sub(r'<think[^>]*>.*$', '', cleaned, flags=re.DOTALL)
            cleaned = cleaned.strip()

            # 提取 ```json ... ``` 中的 JSON
            match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
            if not match:
                print(f"[HierarchyRestorer] 未找到 JSON 代码块，原始响应:\n{raw_content[:500]}")
                return None

            json_str = match.group(1)
            restored = json.loads(json_str)

            # 验证数量
            if len(restored) != len(titles):
                print(
                    f"[HierarchyRestorer] 数量不匹配: 输入={len(titles)}, 输出={len(restored)}，放弃替换"
                )
                return None

            return restored

        except requests.RequestException as e:
            print(f"[HierarchyRestorer] LLM 请求失败: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[HierarchyRestorer] LLM 响应解析失败: {e}")
            return None

    def _apply_restoration(
        self,
        markdown: str,
        original_titles: List[Dict],
        restored_titles: List[Dict],
    ) -> str:
        """
        按行号将还原后的标题替换回原 Markdown

        Args:
            markdown: 原始 Markdown
            original_titles: 原始标题列表
            restored_titles: LLM 还原后的标题列表

        Returns:
            替换后的 Markdown
        """
        lines = markdown.split('\n')

        # 构建行号 → 还原后标题的映射
        restored_map = {}
        for item in restored_titles:
            line_num = item.get("line")
            if line_num is not None:
                restored_map[line_num] = item["text"]

        replaced_count = 0
        for orig, restored in zip(original_titles, restored_titles):
            line_num = orig["line"]
            if line_num in restored_map:
                old_text = orig["text"]
                new_text = restored["text"]

                # 安全校验：只允许 # 数量变化，不允许文字内容变化
                old_body = re.sub(r'^#+\s*', '', old_text)
                new_body = re.sub(r'^#+\s*', '', new_text)

                if old_body != new_body:
                    print(
                        f"[HierarchyRestorer] [WARN] 行{line_num}文字被修改，跳过: "
                        f"原文='{old_body}' → 新文='{new_body}'"
                    )
                    continue

                # 0-based 索引
                lines[line_num - 1] = new_text
                replaced_count += 1

        print(f"[HierarchyRestorer] 替换完成: {replaced_count}/{len(original_titles)} 个标题")
        return '\n'.join(lines)
