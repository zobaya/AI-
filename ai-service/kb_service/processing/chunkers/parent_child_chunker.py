"""
父子分块器：使用 LangChain 标准组件进行父子分块
（从 common/ 迁移）
"""
import json
import re
from typing import List, Dict

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from kb_service.processing.chunkers.base import BaseChunker
from kb_service.processing.utils.utils import (
    metadata_to_header_path,
    get_common_path,
    extract_title_from_filename
)


class ParentChildChunker(BaseChunker):
    """父子分块器：LangChain 标准组件 + 碎片合并算法"""

    def __init__(
        self,
        small_file_threshold: int = 2000,
        parent_chunk_size: int = 2000,
        parent_chunk_overlap: int = 200,
        child_chunk_size: int = 350,
        child_chunk_overlap: int = 50,
        fragment_min_size: int = 500
    ):
        self.small_file_threshold = small_file_threshold
        self.parent_chunk_size = parent_chunk_size
        self.parent_chunk_overlap = parent_chunk_overlap
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap
        self.fragment_min_size = fragment_min_size

        self.headers_to_split_on = [
            ("#", "H1"),
            ("##", "H2"),
            ("###", "H3"),
        ]

        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on
        )

    @staticmethod
    def _segment_content(content: str) -> List[Dict]:
        """
        将内容按行拆分为 TextSegment 和 TableSegment 交替列表。

        返回: [{"type": "text", "content": "..."}, {"type": "table", "content": "..."}, ...]
        """
        lines = content.split('\n')
        segments = []
        current_type = "text"
        current_lines = []

        for line in lines:
            stripped = line.strip()
            is_table_row = stripped.startswith('|') and stripped.endswith('|')
            is_table_delim = bool(re.match(r'^\|[\s\-:]+\|$', stripped))

            row_type = "table" if (is_table_row or is_table_delim) else "text"

            if row_type != current_type:
                if current_lines:
                    segments.append({"type": current_type, "content": '\n'.join(current_lines)})
                current_type = row_type
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            segments.append({"type": current_type, "content": '\n'.join(current_lines)})

        return segments

    @staticmethod
    def split_markdown_table(table_text: str, target_size: int) -> List[str]:
        """
        按行拆分 Markdown 表格，每个子表格保留表头。
        表格 overlap 固定为 0（行级拆分不需要字符重叠）。

        Args:
            table_text: 完整的 Markdown 表格文本
            target_size: 目标字符数上限

        Returns:
            拆分后的 Markdown 表格列表（每个都带表头）
        """
        lines = [l for l in table_text.strip().split('\n') if l.strip()]
        if len(lines) < 3:
            return [table_text]

        # 提取表头块（第1行表头 + 第2行分隔线）
        header_block = f"{lines[0]}\n{lines[1]}"
        header_len = len(header_block) + 1  # +1 for newline

        # 小表格不拆
        if len(table_text) <= target_size:
            return [table_text]

        # 按行累加，拆分数据行
        data_rows = lines[2:]
        chunks = []
        current_rows = []
        current_len = header_len

        for row in data_rows:
            row_len = len(row) + 1
            if current_rows and (current_len + row_len > target_size):
                chunk = header_block + '\n' + '\n'.join(current_rows)
                chunks.append(chunk)
                current_rows = []
                current_len = header_len
            current_rows.append(row)
            current_len += row_len

        if current_rows:
            chunk = header_block + '\n' + '\n'.join(current_rows)
            chunks.append(chunk)

        return chunks if chunks else [table_text]

    def table_aware_split(self, content: str, target_size: int, overlap: int = 0) -> List[str]:
        """
        表格感知切分入口：处理纯文本 / 纯表格 / 混合内容。

        - 纯文本 → RecursiveCharacterTextSplitter
        - 纯表格 → split_markdown_table（按行拆分，带表头，overlap=0）
        - 混合内容 → 分段后分别处理，按原始顺序合并
        """
        segments = self._segment_content(content)

        # 没有表格段 → 走原有逻辑
        has_table = any(s["type"] == "table" for s in segments)
        if not has_table:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=target_size,
                chunk_overlap=overlap,
                length_function=len,
                separators=["\n", "。", "！", "？", "，", " ", ""]
            )
            return splitter.split_text(content)

        # 纯表格 → 走表格拆分
        all_table = all(s["type"] == "table" for s in segments)
        if all_table:
            return self.split_markdown_table(content, target_size)

        # 混合内容 → 每段分别处理，然后按顺序合并
        all_sub_chunks = []
        for seg in segments:
            if seg["type"] == "table":
                sub = self.split_markdown_table(seg["content"], target_size)
            else:
                if not seg["content"].strip():
                    continue
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=target_size,
                    chunk_overlap=overlap,
                    length_function=len,
                    separators=["\n", "。", "！", "？", "，", " ", ""]
                )
                sub = splitter.split_text(seg["content"])
            all_sub_chunks.extend(sub)

        return all_sub_chunks if all_sub_chunks else [content]

    def get_parent_header_path(self, header_path: str) -> str:
        """获取父级路径（去掉最后一级标题）"""
        if " > " in header_path:
            parts = header_path.split(" > ")
            return " > ".join(parts[:-1])
        return ""

    def get_lost_sub_title(self, current_path: str, reference_path: str) -> str:
        """提取当前路径相对于参考路径"新增"的部分"""
        if not current_path:
            return None
        if not reference_path:
            return current_path
        curr_parts = current_path.split(" > ")
        ref_parts = reference_path.split(" > ")
        for i, (c, r) in enumerate(zip(curr_parts, ref_parts)):
            if c != r:
                return " > ".join(curr_parts[i:])
        if len(curr_parts) > len(ref_parts):
            return " > ".join(curr_parts[len(ref_parts):])
        return None

    def merge_fragments_by_path(self, md_docs: List[Document]) -> List[Dict]:
        """
        碎片合并逻辑：只合并相邻的碎片，保留文档原始阅读顺序

        核心原则：
        1. 只合并相邻的碎片，不跨过正常块合并
        2. 健康大块（>= fragment_min_size）直接输出，触发 Flush
        3. 合并后不能超过 MAX_TARGET_SIZE（parent_chunk_size * 1.5）
        4. 合并时使用 LCA（最长公共祖先）作为全局路径，子标题用 **粗体** 注入

        Args:
            md_docs: MarkdownHeaderTextSplitter 切分后的文档列表

        Returns:
            List of merged chunks with metadata
        """
        MAX_TARGET_SIZE = self.parent_chunk_size * 1.5  # 超大块阻断阈值
        min_size = self.fragment_min_size

        print(f"\n[碎片合并] 碎片阈值: {min_size} 字符, 目标大小: {self.parent_chunk_size} 字符")
        print(f"          超大块阻断: {MAX_TARGET_SIZE:.0f} 字符")

        # Step 1: 分析所有块，记录位置信息
        all_blocks = []
        current_position = 0

        for doc in md_docs:
            header_path = metadata_to_header_path(doc.metadata)
            content_len = len(doc.page_content)

            all_blocks.append({
                "doc": doc,
                "header_path": header_path,
                "content_len": content_len,
                "is_fragment": content_len < min_size,
                "position": current_position
            })

            current_position += content_len

        print(f"  块总数: {len(all_blocks)}")

        # Step 2: 按位置顺序处理，只合并相邻的碎片
        merged_chunks = []
        raw_blocks_history = []  # 追踪每次 flush 的原始块，用于反向合并

        # 当前缓冲区（用于合并相邻的碎片）
        current_buffer = []  # 存储 [block1, block2, ...]
        buffer_len = 0
        buffer_start_position = 0
        buffer_paths = []

        def flush_buffer():
            """将当前缓冲区的内容作为一个块输出"""
            nonlocal current_buffer, buffer_len, buffer_start_position, buffer_paths

            if not current_buffer:
                return

            # ========== 步骤 0: 保存原始块快照（用于反向合并） ==========
            raw_blocks_snapshot = current_buffer.copy()  # 深拷贝原始块列表
            raw_blocks_history.append(raw_blocks_snapshot)

            # ========== 步骤 1: 计算所有碎片的公共父路径（LCA） ==========
            all_paths = [block["header_path"] for block in current_buffer]
            common_path = get_common_path(all_paths)

            # ========== 步骤 2: 合并内容，注入被剥离的子标题 ==========
            merged_content = []
            last_injected_title = None  # 记录上次注入的标题，避免重复

            for block in current_buffer:
                # 提取当前块相对于公共路径的独有子标题
                lost_sub_title = self.get_lost_sub_title(block["header_path"], common_path)

                # 决定是否注入标题（避免重复注入相同的标题）
                should_inject = False
                if lost_sub_title:
                    if lost_sub_title != last_injected_title:
                        should_inject = True
                        last_injected_title = lost_sub_title

                if should_inject:
                    # 用粗体注入标题：**子标题**
                    part_text = f"**{lost_sub_title}**\n\n{block['doc'].page_content}"
                else:
                    part_text = block['doc'].page_content

                merged_content.append(part_text)

            # ========== 步骤 3: 合并所有部分 ==========
            final_content = "\n\n".join(merged_content)

            # ========== 步骤 4: 收集 metadata（使用第一个块的 metadata） ==========
            merged_metadata = {}
            for block in current_buffer:
                for key, value in block["doc"].metadata.items():
                    if key not in merged_metadata:
                        merged_metadata[key] = value

            # ========== 步骤 5: 构建结果块 ==========
            result_chunk = {
                "content": final_content,
                "header_path": common_path,  # ✅ 使用 LCA 作为全局路径
                "metadata": merged_metadata,
                "is_merged": len(current_buffer) > 1,
                "original_count": len(current_buffer),
                "original_paths": all_paths,  # 保留原始路径用于调试
                "position": buffer_start_position
            }

            merged_chunks.append(result_chunk)

            if len(current_buffer) > 1:
                print(f"      [MERGE] 合并 {len(current_buffer)} 个碎片 -> {common_path} ({buffer_len} 字符)")
                for path in all_paths:
                    print(f"         - {path}")
            else:
                print(f"      [OK] 单块: {common_path} ({buffer_len} 字符)")

            # 清空缓冲区
            current_buffer = []
            buffer_len = 0
            buffer_paths = []
            buffer_start_position = 0

        # 遍历所有块
        for block in all_blocks:
            content = block["doc"].page_content
            content_len = block["content_len"]
            is_fragment = block["is_fragment"]

            if not is_fragment:
                # ========== 健康大块：尝试与缓冲区的碎片合并 ==========
                if current_buffer:
                    # 优先检查：碎片是否应该向后合并到前一个已输出的父块？
                    backward_merged = False
                    if merged_chunks and raw_blocks_history:
                        last_output_chunk = merged_chunks[-1]
                        last_path = last_output_chunk["header_path"]
                        last_output_len = len(last_output_chunk["content"])

                        # 判断缓冲区碎片是否是前一个块的"子节点"（路径前缀匹配）
                        all_are_children = all(
                            p.startswith(last_path + " > ") if last_path else False
                            for p in buffer_paths
                        )

                        if all_are_children and (last_output_len + buffer_len <= MAX_TARGET_SIZE):
                            # 向后合并：碎片回归到父块
                            print(f"      [BACK-MERGE] 碎片向后合并到父块: {last_path}")
                            print(f"         碎片路径: {buffer_paths}")
                            print(f"         父块: {last_output_len} 字符, 碎片: {buffer_len} 字符")

                            # 1. 弹出上一个已输出块
                            merged_chunks.pop()
                            # 2. 弹出对应的原始块快照
                            last_raw_blocks = raw_blocks_history.pop()

                            # 3. 将原始块插入到当前缓冲区开头
                            for raw_block in reversed(last_raw_blocks):
                                current_buffer.insert(0, raw_block)

                            # 4. 重新计算缓冲区长度和路径
                            buffer_len += last_output_len
                            buffer_start_position = last_output_chunk["position"]
                            buffer_paths = [b["header_path"] for b in current_buffer]

                            print(f"         → 缓冲区重组: {len(current_buffer)} 个原始块, 总计 {buffer_len} 字符")

                            # 5. Flush 合并后的缓冲区
                            flush_buffer()
                            backward_merged = True

                    if not backward_merged:
                        # 常规逻辑：检查碎片是否可以向前合并到当前健康块
                        if buffer_len + content_len <= MAX_TARGET_SIZE:
                            # 可以合并：将健康块加入缓冲区，然后 flush
                            current_buffer.append(block)
                            buffer_len += content_len
                            buffer_paths.append(block["header_path"])
                            flush_buffer()
                        else:
                            # 不能合并：先 flush 碎片，再独立输出健康块
                            flush_buffer()
                            merged_chunks.append({
                                "content": content,
                                "header_path": block["header_path"],
                                "metadata": block["doc"].metadata,
                                "is_merged": False,
                                "original_count": 1,
                                "position": block["position"]
                            })
                            raw_blocks_history.append([block])  # 记录原始块
                            print(f"      [OK] 健康大块: {block['header_path']} ({content_len} 字符)")

                    # 无论哪种合并，当前健康块在 backward_merge 时已被跳过
                    # backward_merge 后需要独立输出当前健康块
                    if backward_merged:
                        merged_chunks.append({
                            "content": content,
                            "header_path": block["header_path"],
                            "metadata": block["doc"].metadata,
                            "is_merged": False,
                            "original_count": 1,
                            "position": block["position"]
                        })
                        raw_blocks_history.append([block])  # 记录原始块
                        print(f"      [OK] 健康大块: {block['header_path']} ({content_len} 字符)")
                else:
                    # 缓冲区为空，直接输出健康块
                    merged_chunks.append({
                        "content": content,
                        "header_path": block["header_path"],
                        "metadata": block["doc"].metadata,
                        "is_merged": False,
                        "original_count": 1,
                        "position": block["position"]
                    })
                    raw_blocks_history.append([block])  # 记录原始块，供后续向后合并使用
                    print(f"      [OK] 健康大块: {block['header_path']} ({content_len} 字符)")

            else:
                # ========== 碎片：尝试合并到缓冲区 ==========
                # 检查合并后是否会超过超大块阈值
                if buffer_len + content_len > MAX_TARGET_SIZE:
                    # 超大块阻断：即使当前缓冲区也是碎片，也必须 Flush
                    print(f"      [BLOCK] 超大块阻断: {buffer_len} + {content_len} = {buffer_len + content_len:.0f} > {MAX_TARGET_SIZE:.0f}")
                    flush_buffer()

                # 将当前碎片添加到缓冲区
                if not current_buffer:
                    buffer_start_position = block["position"]

                current_buffer.append(block)
                buffer_len += content_len
                buffer_paths.append(block["header_path"])

        # 最后 Flush 缓冲区
        # 检查是否是孤立的小碎片，尝试与前一个健康块合并
        if (current_buffer and
            len(current_buffer) == 1 and
            buffer_len < min_size and
            merged_chunks):

            last_output_chunk = merged_chunks[-1]
            last_output_len = len(last_output_chunk["content"])

            # 检查与前一个块合并后是否超过阈值
            if last_output_len + buffer_len <= MAX_TARGET_SIZE:
                # 原始块反向合并：使用未处理的原始数据重新计算
                print(f"      [MERGE尾巴] 原始块反向合并")
                print(f"         碎片: {buffer_paths[0]} ({buffer_len} 字符)")
                print(f"         前块: {last_output_chunk['header_path']} ({last_output_len} 字符)")

                # 1. 丢弃已生成的格式化数据（已处理块）
                merged_chunks.pop()

                # 2. 提取并丢弃对应的原始块快照
                last_raw_blocks = raw_blocks_history.pop()
                print(f"         → 从历史记录提取 {len(last_raw_blocks)} 个原始块")

                # 3. 原始块与当前碎片进行纯净拼接
                # 将前一个块的所有原始块添加到当前缓冲区开头
                for raw_block in reversed(last_raw_blocks):
                    current_buffer.insert(0, raw_block)

                # 4. 重新计算缓冲区长度和路径列表
                buffer_len += last_output_len
                buffer_start_position = last_output_chunk["position"]

                # 重建 buffer_paths：从所有原始块的 header_path 中提取
                new_buffer_paths = [block["header_path"] for block in current_buffer]
                buffer_paths = new_buffer_paths

                print(f"         → 缓冲区重组: {len(current_buffer)} 个原始块, 总计 {buffer_len} 字符")

        flush_buffer()

        # Step 3: 检查是否有超大块需要切分
        print(f"\n  [切分检查] 阈值: {MAX_TARGET_SIZE:.0f} 字符")
        final_chunks = []

        for chunk in merged_chunks:
            content_len = len(chunk["content"])

            if content_len > MAX_TARGET_SIZE:
                # 需要切分（表格感知）
                print(f"    [切分] 超大块 ({content_len:.0f} 字符) 需要切分")

                sub_contents = self.table_aware_split(
                    chunk["content"], self.parent_chunk_size, self.parent_chunk_overlap
                )

                for i, sub_content in enumerate(sub_contents):
                    final_chunks.append({
                        "content": sub_content,
                        "header_path": chunk["header_path"],
                        "metadata": chunk["metadata"],
                        "is_merged": chunk["is_merged"],
                        "original_count": chunk["original_count"],
                        "split_index": i,
                        "position": chunk["position"]
                    })
                print(f"      → 切分成 {len(sub_contents)} 个块")
            else:
                final_chunks.append(chunk)

        # Step 4: 同路径相邻块聚合
        # 将 header_path 相同的相邻小块合并为一个父块，直到接近 MAX_TARGET_SIZE
        print(f"\n  [聚合前] 父块数量: {len(final_chunks)}")
        aggregated = []
        i = 0
        while i < len(final_chunks):
            current = final_chunks[i]
            merged_content = current["content"]
            merged_count = 1

            # 向后扫描同路径的相邻块
            j = i + 1
            while j < len(final_chunks):
                next_chunk = final_chunks[j]
                if next_chunk["header_path"] != current["header_path"]:
                    break  # 路径不同，停止
                if len(merged_content) + len(next_chunk["content"]) > MAX_TARGET_SIZE:
                    break  # 合并后超过阈值，停止
                merged_content += "\n\n" + next_chunk["content"]
                merged_count += 1
                j += 1

            if merged_count > 1:
                print(f"    [聚合] {current['header_path']}: 合并 {merged_count} 个同路径块 -> {len(merged_content)} 字符")

            aggregated.append({
                "content": merged_content,
                "header_path": current["header_path"],
                "metadata": current["metadata"],
                "is_merged": current.get("is_merged", False),
                "original_count": merged_count,
                "position": current["position"]
            })
            i = j

        final_chunks = aggregated
        print(f"\n  合并后父块数量: {len(final_chunks)}")
        return final_chunks

    def _preserve_orphan_headers(self, markdown: str) -> str:
        """
        预处理：为没有正文的"孤标题"补充其标题文字作为内容

        MarkdownHeaderTextSplitter 只把标题作为 metadata，不保留在 content 中。
        如果一个标题后面没有正文就遇到了下一个同级或更高级标题，
        那么这个标题的内容就会变成空字符串，导致信息丢失。

        解决方案：检测"标题后紧跟空行+下一标题"的模式，
        在孤标题下方插入标题文字本身作为保底内容。

        例:
            ### 7.4 钢丝盘应规整...

            ## 8 直条钢丝长度

        变为:
            ### 7.4 钢丝盘应规整...

            钢丝盘应规整...

            ## 8 直条钢丝长度
        """
        lines = markdown.split('\n')
        result = []
        i = 0
        patched = 0

        while i < len(lines):
            result.append(lines[i])

            # 检测标题行
            header_match = re.match(r'^(#{1,6})\s+(.+)$', lines[i])
            if header_match:
                header_level = len(header_match.group(1))
                header_text = header_match.group(2).strip()

                # 向前看：跳过空行，看下一行是否是同级或更高级标题
                j = i + 1
                while j < len(lines) and lines[j].strip() == '':
                    j += 1

                # 如果下一个非空行是同级或更高级标题（或文件结尾），则为孤标题
                is_orphan = False
                if j >= len(lines):
                    # 标题是文件最后一行
                    is_orphan = True
                elif j > i + 1:
                    # 中间有空行，检查下一行
                    next_line_match = re.match(r'^(#{1,6})\s+', lines[j])
                    if next_line_match:
                        next_level = len(next_line_match.group(1))
                        if next_level <= header_level:
                            is_orphan = True
                    # 下一行不是标题但有空行间隔，不算孤标题

                if is_orphan:
                    # 插入标题文字作为保底内容
                    result.append('')
                    result.append(header_text)
                    patched += 1

            i += 1

        if patched > 0:
            print(f"[ParentChildChunker] 补充了 {patched} 个孤标题的内容")

        return '\n'.join(result)

    def extract_header_from_text(self, markdown_text: str, file_name: str) -> str:
        """从文本中提取标题"""
        first_heading_match = re.search(r'^#\s+(.+)$', markdown_text, re.MULTILINE)
        if first_heading_match:
            return first_heading_match.group(1).strip()
        second_heading_match = re.search(r'^##\s+(.+)$', markdown_text, re.MULTILINE)
        if second_heading_match:
            doc_title = extract_title_from_filename(file_name)
            return doc_title + " > " + second_heading_match.group(1).strip()
        doc_title = extract_title_from_filename(file_name)
        if doc_title:
            return doc_title
        first_line = markdown_text.split('\n')[0].strip()
        if first_line:
            return first_line[:50] + ("..." if len(first_line) > 50 else "")
        return "无标题文档"

    def process_small_document(self, markdown_text: str, doc_id: str, file_name: str) -> List[Dict]:
        """处理小文档"""
        doc_title = extract_title_from_filename(file_name)
        header_path = self.extract_header_from_text(markdown_text, file_name)

        parent_id = f"{doc_id}_P_000"

        # 构建父块
        parent_es_doc = {
            "content": markdown_text,
            "headers": self._format_headers([header_path]),
            "metadata": {
                "doc_id": doc_id,
                "chunk_id": parent_id,
                "parent_id": None,  # 父块没有 parent_id
                "chunk_level": 1,
                "chunk_length": len(markdown_text),
                "file_name": file_name,
                "kb_id": None,
                "department": None,
                "category_l1": None,
                "category_l2": None,
                "is_active": True,
                "upload_time": None,
                "update_time": None,
                "delete_time": None,
            }
        }

        # 子块切分（表格感知）
        child_docs = self.table_aware_split(
            markdown_text, self.child_chunk_size, self.child_chunk_overlap
        )
        temp_documents = [parent_es_doc]

        for k, child_content in enumerate(child_docs):
            child_id = f"{parent_id}_C_{k:03d}"
            child_es_doc = {
                "content": child_content,
                "headers": self._format_headers([header_path]),
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_id": child_id,
                    "parent_id": parent_id,
                    "chunk_level": 2,
                    "chunk_length": len(child_content),
                    "file_name": file_name,
                    "kb_id": None,
                    "department": None,
                    "category_l1": None,
                    "category_l2": None,
                    "is_active": True,
                    "upload_time": None,
                    "update_time": None,
                    "delete_time": None,
                }
            }
            temp_documents.append(child_es_doc)

        return temp_documents

    def chunk(self, markdown: str, doc_id: str, file_name: str) -> List[Dict]:
        """主入口：将 Markdown 分块"""
        print(f"[DEBUG ParentChildChunker] Called with:")
        print(f"  doc_id: {repr(doc_id)}")
        print(f"  file_name: {repr(file_name)}")
        print(f"  Input markdown preview (first 200 chars):")
        print(f"    {repr(markdown[:200])}")
        print(f"[DEBUG] Has # header: {'#' in markdown[:500]}")

        if len(markdown) < self.small_file_threshold:
            return self.process_small_document(markdown, doc_id, file_name)

        doc_title = extract_title_from_filename(file_name)
        print(f"[DEBUG] Extracted doc_title: {repr(doc_title)}")

        # 检查是否有标题
        has_heading = bool(re.search(r'^#\s+', markdown, re.MULTILINE))
        if not has_heading:
            markdown = f"# {doc_title}\n\n" + markdown

        # 预处理：为没有正文的"孤标题"补充内容，防止 MarkdownHeaderTextSplitter 丢失
        markdown = self._preserve_orphan_headers(markdown)

        # 按标题切分
        md_docs = self.markdown_splitter.split_text(markdown)

        print(f"[DEBUG] markdown_splitter returned {len(md_docs)} docs")
        for i, doc in enumerate(md_docs[:3]):  # Show first 3
            print(f"[DEBUG] Doc {i} metadata: {doc.metadata}")
            print(f"[DEBUG] Doc {i} content preview: {repr(doc.page_content[:100])}")

        parent_chunks = self.merge_fragments_by_path(md_docs)

        # 生成父子块
        temp_documents = []
        parent_idx = 0

        for parent_chunk in parent_chunks:
            header_path = parent_chunk["header_path"]
            if not header_path:
                header_path = doc_title
            content = parent_chunk["content"]

            parent_id = f"{doc_id}_P_{parent_idx:03d}"
            parent_idx += 1

            # 父块
            parent_es_doc = {
                "content": content,
                "headers": self._format_headers([header_path]),
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_id": parent_id,
                    "parent_id": None,  # 父块没有 parent_id
                    "chunk_level": 1,
                    "chunk_length": len(content),
                    "file_name": file_name,
                    "kb_id": None,
                    "department": None,
                    "category_l1": None,
                    "category_l2": None,
                    "is_active": True,
                    "upload_time": None,
                    "update_time": None,
                    "delete_time": None,
                }
            }

            temp_documents.append(parent_es_doc)

            # 子块（表格感知）
            child_docs = self.table_aware_split(
                content, self.child_chunk_size, self.child_chunk_overlap
            )
            for k, child_content in enumerate(child_docs):
                child_id = f"{parent_id}_C_{k:03d}"
                child_es_doc = {
                    "content": child_content,
                    "headers": self._format_headers([header_path]),
                    "metadata": {
                        "doc_id": doc_id,
                        "chunk_id": child_id,
                        "parent_id": parent_id,
                        "chunk_level": 2,
                        "chunk_length": len(child_content),
                        "file_name": file_name,
                        "kb_id": None,
                        "department": None,
                        "category_l1": None,
                        "category_l2": None,
                        "is_active": True,
                        "upload_time": None,
                        "update_time": None,
                        "delete_time": None,
                    }
                }
                temp_documents.append(child_es_doc)

        return temp_documents
