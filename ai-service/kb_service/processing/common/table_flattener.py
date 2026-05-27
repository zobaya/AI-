"""
HTML 表格转换器 - 通过 LLM 将 HTML <table> 转为 Markdown 表格

处理流程：
  1. 扫描 Markdown 中的所有 <table>...</table> 块
  2. 逐个发送给 LLM 进行 HTML → Markdown 表格转换
  3. 处理 rowspan/colspan 等复杂合并单元格
  4. 替换原文中的 HTML 表格为 Markdown 表格
"""
import re
import logging
import requests
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)

# SYSTEM_PROMPT = (
#     "你是一个专业的数据结构化转换工具。你的任务是将包含复杂合并单元格（rowspan/colspan）的 HTML 表格，“无损且严格对齐”地转换为标准的纯 Markdown 表格。\n"
#     "【强制平铺与排版规则】：\n"
#     "1. 强制标准结构：输出必须是合法的 Markdown 表格。第一行为表头，第二行必须是格式分隔符（如 `|---|---|---|`），此后为数据行。\n"
#     "2. 处理表头跨列：若存在多级表头，将父子级用短横线“-”连接为一层。\n"
#     "3. 处理横向跨列（colspan）【最高警报】：遇到跨列单元格，**绝对禁止将同一文本在同一行内重复复制**！必须将文字仅放在对应范围的第一个格子里，其余被跨越的单元格必须用真正的“空白”补齐。示例：如果“部门”跨了3列，必须输出为 `| 部门 | | |`，以此保证每一行的管道符 `|` 数量绝对一致。\n"
#     "4. 处理纵向跨行（rowspan）：遇到跨行单元格，必须在其跨越的每一行对应位置重复填写该数据。注意：仅限 rowspan 导致的合并需向下复制。若 HTML 源码中本身就是不同的多行数据，必须如实输出，严禁无故复制整行数据。\n"
#     "5. 格式要求：只允许输出表格文本本身，每行必须以 `|` 开头和结尾。绝对禁止包含任何开场白、解释说明，严禁使用 ``` 或 ```markdown 语法包裹。"
# )

SYSTEM_PROMPT = (
    "你是一个专业的数据结构化转换工具。你的任务是将包含复杂合并单元格（rowspan/colspan）的 HTML 表格，“无损且严格对齐”地转换为标准的纯 Markdown 表格。\n"
    "【强制平铺与排版规则】：\n"
    "1. 强制标准结构：输出必须是合法的 Markdown 表格。第一行为表头，第二行必须是格式分隔符（如 `|---|---|---|`），此后为数据行。\n"
    "2. 精准处理多级表头（表头降维）：最终输出只能有**一行** Markdown 表头。如果原始 HTML 有多行表头：\n"
    "   - 垂直父子映射：对于横向跨列（colspan）的父级表头，必须将其文本向下透传，与它覆盖的正下方的子表头用短横线“-”组合。\n"
    "   - 独立跨行表头：对于纵向跨行（rowspan）的表头，直接作为该列的最终表头。**绝对禁止将同一行内互不相关的独立表头横向拼接在一起！**\n"
    "3. 处理横向跨列（colspan）数据【最高警报】：遇到跨列单元格，**绝对禁止将同一文本在同一行内重复复制**！必须将文字仅放在对应范围的第一个格子里，其余被跨越的单元格必须用真正的“空白”补齐。示例：如果“部门”跨了3列，必须输出为 `| 部门 | | |`，以此保证每一行的管道符 `|` 数量绝对一致。\n"
    "4. 处理纵向跨行（rowspan）数据：遇到跨行单元格，必须在其跨越的每一行对应位置重复填写该数据。注意：仅限 rowspan 导致的合并需向下复制。若 HTML 源码中本身就是不同的多行数据，必须如实输出，严禁无故复制整行数据。\n"
    "5. 格式要求：只允许输出表格文本本身，每行必须以 `|` 开头和结尾。绝对禁止包含任何开场白、解释说明，严禁使用 ``` 或 ```markdown 语法包裹。"
)

class TableFlattener:
    """HTML 表格转换器：通过 LLM 将 <table> 转为 Markdown 表格"""

    def flatten(self, markdown: str) -> str:
        """
        扫描 Markdown 中的所有 <table>...</table>，逐个通过 LLM 转为 Markdown 表格

        Args:
            markdown: 原始 Markdown 文本

        Returns:
            HTML 表格已被替换为 Markdown 表格的文本
        """
        pattern = re.compile(r'<table\b[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)

        tables = pattern.findall(markdown)
        total = len(tables)
        if total == 0:
            return markdown

        logger.info(f"[TableFlattener] 发现 {total} 个 HTML 表格，开始 LLM 转换...")

        processed = 0

        def replace_table(match):
            nonlocal processed
            html_table = match.group(0)
            processed += 1
            logger.info(f"[TableFlattener] [{processed}/{total}] 正在转换表格...")

            md_table = self._convert_with_llm(html_table)
            if md_table != html_table:
                logger.info(f"[TableFlattener] [{processed}/{total}] 转换完成")
            else:
                logger.warning(f"[TableFlattener] [{processed}/{total}] 转换失败，保留原 HTML")

            return f"\n{md_table}\n"

        result = pattern.sub(replace_table, markdown)
        return result

    def _convert_with_llm(self, html_table: str) -> str:
        """
        调用 vLLM 将 HTML 表格转为 Markdown 表格

        Args:
            html_table: HTML 表格字符串

        Returns:
            Markdown 表格字符串，失败时返回原始 HTML
        """
        payload = {
            "model": settings.VLLM_MODEL_NAME,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": html_table}
            ],
            "temperature": 0.1,
            "max_tokens": 8192,
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }

        try:
            response = requests.post(
                settings.VLLM_CHAT_URL,
                json=payload,
                timeout=settings.VLLM_TIMEOUT,
            )

            if response.status_code != 200:
                logger.error(
                    f"[TableFlattener] LLM 请求失败 HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
                return html_table

            result = response.json()
            choices = result.get("choices", [])
            if not choices:
                logger.warning("[TableFlattener] LLM 返回空 choices，保留原 HTML")
                return html_table

            content = (choices[0].get("message", {}).get("content") or "").strip()
            if not content:
                logger.warning("[TableFlattener] LLM 返回空内容，保留原 HTML")
                return html_table

            # 清理代码块包裹
            md_table = self._strip_code_blocks(content)

            # 后处理：去除连续重复行（LLM 可能把同一行复制多遍）
            md_table = self._deduplicate_rows(md_table)

            return md_table

        except requests.exceptions.RequestException as e:
            logger.error(f"[TableFlattener] 网络请求失败: {e}")
            return html_table
        except Exception as e:
            logger.error(f"[TableFlattener] 解析 LLM 响应失败: {e}")
            return html_table

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        """去除 LLM 输出可能带的 ```markdown ... ``` 包裹"""
        code_block = "`" * 3
        for prefix in [f"{code_block}markdown", code_block]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        if text.endswith(code_block):
            text = text[:-len(code_block)].strip()
        return text

    @staticmethod
    def _deduplicate_rows(md_table: str) -> str:
        """
        去除 Markdown 表格中连续重复的数据行

        LLM 处理 rowspan 时可能错误地将同一行复制多遍，
        此方法检测并去除连续出现的重复数据行。
        """
        lines = md_table.split('\n')
        result = []
        prev_line = None
        removed = 0

        for line in lines:
            stripped = line.strip()
            # 分隔行 (|---|---|) 保留
            if stripped and all(c in '|-: ' for c in stripped):
                result.append(line)
                prev_line = None
                continue
            # 数据行：与上一行完全相同则跳过
            if stripped and stripped == prev_line:
                removed += 1
                continue
            result.append(line)
            prev_line = stripped

        if removed > 0:
            logger.info(f"[TableFlattener] 去除了 {removed} 个连续重复行")

        return '\n'.join(result)
