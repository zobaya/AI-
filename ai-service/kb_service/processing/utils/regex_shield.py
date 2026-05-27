# -*- coding: utf-8 -*-
"""
正则保护罩（Regex Shield）- 识别并保护图片等不可分割的原子块
"""
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class AtomicBlock:
    """原子块 - 不可分割的内容单元"""
    start: int              # 在原文中的起始位置
    end: int                # 在原文中的结束位置
    content: str            # 块内容
    block_type: str         # 块类型：'image', 'table', 'code', 'formula'
    metadata: dict = None   # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def overlaps(self, pos: int, length: int) -> bool:
        """
        检查给定范围是否与原子块重叠

        Args:
            pos: 起始位置
            length: 长度

        Returns:
            是否重叠
        """
        block_start = self.start
        block_end = self.end
        cut_start = pos
        cut_end = pos + length

        # 检查是否有重叠
        return not (cut_end <= block_start or cut_start >= block_end)

    def contains(self, pos: int) -> bool:
        """检查位置是否在原子块内"""
        return self.start <= pos < self.end


class RegexShield:
    """
    正则保护罩

    功能：
    1. 识别文档中的原子块（图片、表格、代码块、公式等）
    2. 提供接口查询某个位置是否可以切分
    3. 计算安全的切分点
    """

    def __init__(self):
        # 定义原子块的正则模式
        self.patterns = {
            'image': [
                # Markdown 图片
                r'!\[.*?\]\([^\)]+\)',
                # HTML 图片
                r'<img[^>]*src\s*=\s*[\'"][^\'"]+[\'"][^>]*>',
            ],
            'table': [
                # HTML 表格
                r'<table>.*?</table>',
            ],
            'code': [
                # 代码块（```）
                r'```.*?```',
                # 缩进代码块（4个空格或tab）
                r'^(    |\t).*?(?=\\n\\S|\\n\\n|$)',
            ],
            'formula': [
                # LaTeX 块级公式（$$...$$）- 只保护块级公式
                r'\$\$[^$]+\$\$',
            ],
        }

        self.atomic_blocks: List[AtomicBlock] = []

    def scan_document(self, text: str) -> List[AtomicBlock]:
        """
        扫描文档，识别所有原子块

        Args:
            text: 文档文本

        Returns:
            AtomicBlock 列表，按起始位置排序
        """
        self.atomic_blocks = []

        for block_type, patterns in self.patterns.items():
            for pattern in patterns:
                # 使用 DOTALL 标志，让 . 匹配换行符
                regex = re.compile(pattern, re.DOTALL | re.IGNORECASE)

                for match in regex.finditer(text):
                    # 扩展匹配范围，包含上下文
                    start, end = self._expand_block_boundaries(
                        text, match.start(), match.end(), block_type
                    )

                    atomic_block = AtomicBlock(
                        start=start,
                        end=end,
                        content=text[start:end],
                        block_type=block_type,
                        metadata={
                            'original_match_start': match.start(),
                            'original_match_end': match.end(),
                            'pattern_used': pattern
                        }
                    )
                    self.atomic_blocks.append(atomic_block)

        # 按起始位置排序
        self.atomic_blocks.sort(key=lambda b: b.start)

        # 合并重叠的块
        self.atomic_blocks = self._merge_overlapping_blocks(self.atomic_blocks)

        return self.atomic_blocks

    def _expand_block_boundaries(
        self,
        text: str,
        match_start: int,
        match_end: int,
        block_type: str
    ) -> Tuple[int, int]:
        """
        扩展块边界，包含完整的上下文

        策略：
        - 图片：向前包含标题（如果有），向后包含图注直到空行
        - 表格：包含整个 <table>...</table>
        - 代码块：包含开始和结束标记
        - 公式：包含前后空格

        Args:
            text: 文本
            match_start: 匹配起始位置
            match_end: 匹配结束位置
            block_type: 块类型

        Returns:
            (扩展后的起始位置, 扩展后的结束位置)
        """
        start = match_start
        end = match_end

        if block_type == 'image':
            # 向前：包含可能的标题（图 X）
            lines_before = text[:start].split('\n')
            if lines_before:
                # 检查前一行是否是图注
                last_line = lines_before[-1].strip()
                if last_line and not last_line.startswith('#') and not last_line.startswith('!'):
                    # 可能是图注，包含进来
                    if len(last_line) < 100:  # 图注通常很短
                        start -= len(lines_before[-1]) + 1  # +1 for newline

            # 向后：包含图注和可能的连续图片
            # 使用更精确的方法：直接遍历文本，找到合适的结束位置
            expansion_start = end
            lines_after = text[end:].split('\n')
            included_lines = 0
            previous_was_image = True  # Start with True since we just matched an image

            for i, line in enumerate(lines_after):
                stripped = line.strip()

                # Skip initial empty lines (the newline right after the image)
                if not stripped and included_lines == 0:
                    # Move expansion_start past this empty line
                    expansion_start += len(line) + 1  # +1 for the \n we split on
                    continue

                # 遇到空行，停止
                if not stripped:
                    break

                # 遇到标题，停止
                if stripped.startswith('#'):
                    break

                # 遇到表格，停止
                if '<table>' in stripped.lower():
                    break

                # 遇到代码块，停止
                if stripped.startswith('```'):
                    break

                # 检查是否是图片
                is_image = stripped.startswith('![') or '<img' in stripped.lower()

                if is_image:
                    # 是图片，包含并继续
                    included_lines += 1
                    previous_was_image = True
                    # 更新 end 位置到这一行结束
                    end = expansion_start + len(line) + 1  # +1 for \n
                    expansion_start = end  # Move to next line
                elif previous_was_image:
                    # 前一行是图片，这一行可能是图注
                    # 如果是短文本（< 200 字符），视为图注并包含
                    if len(stripped) < 200:
                        included_lines += 1
                        # 更新 end 位置到这一行结束
                        end = expansion_start + len(line) + 1  # +1 for \n
                        expansion_start = end  # Move to next line
                        # 图注后还可以继续有图片，所以保持 previous_was_image 为 True
                        # 但如果下一行还不是图片，就停止
                        previous_was_image = False
                    else:
                        # 文本太长，不是图注，停止
                        break
                else:
                    # 前一行不是图片，这一行也不是图片，停止
                    break

        elif block_type == 'table':
            # 表格：已经包含完整的 <table>...</table>
            # 向前：包含表格前的说明文字（如"单位为毫米"、"表 1 ..."）
            lines_before = text[:start].split('\n')
            if lines_before:
                # 向后查找，记录应包含的行索引
                lines_to_include = []  # 记录应包含的行索引
                consecutive_short_lines = 0  # 连续短行计数

                for i in range(len(lines_before) - 1, -1, -1):
                    line_stripped = lines_before[i].strip()

                    # 遇到空行，记录并继续
                    if not line_stripped:
                        lines_to_include.append(i)
                        continue

                    # 遇到标题，停止
                    if line_stripped.startswith('#'):
                        break

                    # 如果是短文本（< 100 字符），可能是表格说明
                    if len(line_stripped) < 100:
                        lines_to_include.append(i)
                        consecutive_short_lines += 1
                        # 如果已经包含了2个短行（如"单位为毫米" + "表 1 ..."），停止
                        if consecutive_short_lines >= 2:
                            break
                    else:
                        # 文本太长，停止
                        break

                # 如果找到了表格说明，包含进来
                if lines_to_include:
                    # 计算新的 start 位置：从最早的行开始
                    earliest_line_idx = min(lines_to_include)
                    chars_to_include = 0
                    for i in range(earliest_line_idx, len(lines_before)):
                        chars_to_include += len(lines_before[i]) + 1  # +1 for newline
                    # 确保不会扩展到负数位置
                    if chars_to_include > start:
                        chars_to_include = start
                    start -= chars_to_include

            # 向后：包含可能的说明文字（一行）
            remaining = text[end:]
            first_line_end = remaining.find('\n')
            if first_line_end > 0 and first_line_end < 100:
                description = remaining[:first_line_end].strip()
                if description and not description.startswith('#'):
                    end += first_line_end + 1

        elif block_type == 'code':
            # 代码块：确保包含完整的标记
            # 已由正则处理
            pass

        elif block_type == 'formula':
            # 公式：包含前后空格 + 后续的参数说明（式中：...）
            # 向前
            while start > 0 and text[start - 1] in ' \t':
                start -= 1
            # 向后
            while end < len(text) and text[end] in ' \t':
                end += 1

            # 向后：包含参数说明段落（式中：、其中：、where: 等）
            lines_after = text[end:].split('\n')

            # 跳过空行
            skip_empty = 0
            for i, line in enumerate(lines_after):
                if not line.strip():
                    skip_empty += 1
                else:
                    break

            # 检查下一行是否是参数说明
            if skip_empty < len(lines_after):
                next_line = lines_after[skip_empty].strip()

                # 检查是否是参数说明行
                param_keywords = ['式中：', '式中:', '其中：', 'where:', 'Where:', '参数：', '说明：']
                is_param_desc = any(next_line.startswith(kw) for kw in param_keywords)

                if is_param_desc:
                    # 包含空行和参数说明段落
                    # 查找参数说明段落的结束（通常是遇到空行或下一个标题）
                    param_lines = [lines_after[skip_empty]]  # 参数说明行
                    for j in range(skip_empty + 1, len(lines_after)):
                        param_line = lines_after[j].strip()
                        # 遇到空行、标题、代码块、表格，停止
                        if not param_line or param_line.startswith('#') or param_line.startswith('```') or '<table>' in param_line.lower():
                            break
                        # 如果行很短（< 200 字符），继续认为是参数说明的一部分
                        if len(param_line) < 200:
                            param_lines.append(lines_after[j])
                        else:
                            break

                    # 计算新的结束位置
                    if param_lines:
                        # 包含空行 + 所有参数说明行
                        total_extra = sum(len(lines_after[k]) + 1 for k in range(skip_empty + len(param_lines)))
                        end += total_extra

        return (start, end)

    def _merge_overlapping_blocks(self, blocks: List[AtomicBlock]) -> List[AtomicBlock]:
        """
        合并重叠或相邻的原子块

        Args:
            blocks: 原子块列表（已排序）

        Returns:
            合并后的原子块列表
        """
        if not blocks:
            return []

        merged = [blocks[0]]

        for block in blocks[1:]:
            last = merged[-1]

            # 检查是否重叠或相邻
            if block.start <= last.end:
                # 重叠或相邻，合并
                # 拼接内容：如果新块扩展了边界，则包含新块的内容
                if block.end > last.end:
                    # 计算重叠部分的内容
                    merged_content = last.content
                    # 添加新块中超出 last.end 的部分
                    extra_start = last.end - block.start
                    if extra_start > 0:
                        # 有重叠，只添加非重叠部分
                        extra_content = block.content[extra_start:]
                    else:
                        # 相邻，添加全部内容
                        extra_content = block.content
                    merged_content += extra_content
                else:
                    merged_content = last.content

                merged[-1] = AtomicBlock(
                    start=last.start,
                    end=max(last.end, block.end),
                    content=merged_content,
                    block_type='mixed',
                    metadata={
                        'merged': True,
                        'original_types': [last.block_type, block.block_type]
                    }
                )
            else:
                # 不重叠，添加新块
                merged.append(block)

        return merged

    def can_cut_at(self, position: int) -> bool:
        """
        检查是否可以在指定位置切分

        Args:
            position: 切分位置

        Returns:
            是否可以切分
        """
        for block in self.atomic_blocks:
            if block.contains(position):
                return False
        return True

    def find_safe_cut_points(
        self,
        text: str,
        chunk_size: int,
        overlap: int
    ) -> List[Tuple[int, int]]:
        """
        查找安全的切分点，避开所有原子块

        Args:
            text: 文本
            chunk_size: 目标块大小
            overlap: 重叠大小

        Returns:
            切分点列表 [(start, end), ...]
        """
        if not self.atomic_blocks:
            # 没有原子块，使用默认切分
            return self._default_split(text, chunk_size, overlap)

        cut_points = []
        current_pos = 0

        while current_pos < len(text):
            # 计算理想的切分点
            ideal_end = current_pos + chunk_size

            if ideal_end >= len(text):
                # 到达末尾
                cut_points.append((current_pos, len(text)))
                break

            # 检查理想切分点是否会切割原子块
            safe_end = self._find_safe_end(text, current_pos, ideal_end)

            cut_points.append((current_pos, safe_end))

            # 移动到下一个位置（考虑重叠）
            current_pos = safe_end - overlap

            # 防止死循环
            if current_pos <= 0 or current_pos >= len(text):
                break

        return cut_points

    def _find_safe_end(self, text: str, start: int, ideal_end: int) -> int:
        """
        查找安全的结束位置

        Args:
            text: 文本
            start: 起始位置
            ideal_end: 理想结束位置

        Returns:
            安全的结束位置
        """
        # 检查理想结束位置是否会切割原子块
        for block in self.atomic_blocks:
            if block.overlaps(start, ideal_end - start):
                # 会切割原子块，调整位置
                # 选择：在原子块之前切分
                if block.start > start:
                    # 在原子块之前切分
                    return block.start
                else:
                    # 原子块包含起始位置，在原子块之后切分
                    return min(block.end, len(text))

        # 不会切割原子块，进一步优化：寻找句子边界
        return self._find_sentence_boundary(text, start, ideal_end)

    def _find_sentence_boundary(self, text: str, start: int, ideal_end: int) -> int:
        """
        在理想结束位置附近查找句子边界

        Args:
            text: 文本
            start: 起始位置
            ideal_end: 理想结束位置

        Returns:
            优化后的结束位置
        """
        # 向前查找最近的句子结束符
        delimiters = ['。', '！', '？', '.', '!', '?', '\n\n']

        for delimiter in delimiters:
            last_pos = text.rfind(delimiter, start, ideal_end)
            if last_pos > start:
                return last_pos + 1

        # 没找到句子边界，返回理想位置
        return ideal_end

    def _default_split(self, text: str, chunk_size: int, overlap: int) -> List[Tuple[int, int]]:
        """默认切分（没有原子块）"""
        points = []
        current = 0

        while current < len(text):
            end = min(current + chunk_size, len(text))
            points.append((current, end))
            current = end - overlap

            if current <= 0 or current >= len(text):
                break

        return points

    def get_atomic_blocks_summary(self) -> List[dict]:
        """获取原子块摘要"""
        return [
            {
                'type': block.block_type,
                'start': block.start,
                'end': block.end,
                'length': block.end - block.start,
                'metadata': block.metadata
            }
            for block in self.atomic_blocks
        ]


# 全局实例
regex_shield = RegexShield()
