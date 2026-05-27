"""
混合转换器：MarkItDown 文本 + Mammoth 图片 + MinIO + VLM

用于将 Word 文档转换为 Markdown，同时：
1. 使用 MarkItDown 保留表格格式
2. 使用 Mammoth 提取高质量图片
3. 上传图片到 MinIO
4. 调用 VLM 生成图片描述（结合文档上下文）
"""
import os
import re
import base64
import hashlib
from typing import List, Dict, Tuple
from pathlib import Path


class HybridConverter:
    """混合转换器：结合 MarkItDown 和 Mammoth 的优势"""

    def __init__(self):
        """初始化混合转换器"""
        self.vlm_enabled = True  # 是否启用 VLM 图片理解

    def extract_images_from_mammoth(self, word_file: str) -> Tuple[str, List[Dict]]:
        """
        使用 Mammoth 提取完整 Base64 图片

        Args:
            word_file: Word 文档路径

        Returns:
            (markdown_content, images_list)
            - markdown_content: Mammoth 生成的 Markdown 内容（包含 Base64 图片）
            - images_list: 图片列表
              [{
                  'alt': '图片描述',
                  'format': 'jpeg',
                  'bytes': b'...',
                  'size': 12345
              }]
        """
        import mammoth

        print("  [Mammoth] Converting with Mammoth for image extraction...")

        with open(word_file, "rb") as docx_file:
            result = mammoth.convert_to_markdown(docx_file)
            md_content = result.value

        # 提取 Base64 图片
        images = []
        pattern = r'!\[(.*?)\]\((data:image/(jpeg|png|gif|bmp);base64,([A-Za-z0-9+/=]+))\)'

        for match in re.finditer(pattern, md_content):
            alt_text = match.group(1)
            image_format = match.group(3)
            base64_data = match.group(4)

            try:
                image_bytes = base64.b64decode(base64_data)
                images.append({
                    'alt': alt_text,
                    'format': image_format,
                    'bytes': image_bytes,
                    'size': len(image_bytes)
                })
            except Exception as e:
                print(f"    [WARN] Failed to decode image: {e}")
                continue

        print(f"  [Mammoth] Found {len(images)} images ({sum(img['size'] for img in images)/1024:.1f} KB total)")
        return md_content, images

    def get_markitdown_text(self, word_file: str) -> str:
        """
        使用 MarkItDown 获取 Markdown 文本（保留表格格式）

        Args:
            word_file: Word 文档路径

        Returns:
            Markdown 文本
        """
        from markitdown import MarkItDown

        print("  [MarkItDown] Converting with MarkItDown for text structure...")
        md = MarkItDown()
        result = md.convert(word_file)
        md_content = result.text_content

        print(f"  [MarkItDown] Generated {len(md_content):,} chars")
        return md_content

    def upload_image_to_minio(
        self,
        image_bytes: bytes,
        image_format: str,
        kb_id: str,
        doc_id: str
    ) -> str:
        """
        上传图片到 MinIO

        Args:
            image_bytes: 图片字节数据
            image_format: 图片格式（jpeg, png 等）
            kb_id: 知识库 ID
            doc_id: 文档 ID

        Returns:
            MinIO 图片 URL，失败返回 None
        """
        from core.object_store import object_store

        # 生成文件名
        img_hash = hashlib.sha256(image_bytes).hexdigest()
        ext_map = {
            'jpeg': 'jpg',
            'jpg': 'jpg',
            'png': 'png',
            'gif': 'gif',
            'bmp': 'bmp'
        }
        ext = ext_map.get(image_format, 'jpg')
        filename = f"{img_hash}.{ext}"

        # MinIO 路径：{kb_id}/{doc_id}/images/
        object_name = f"{kb_id}/{doc_id}/images/{filename}"

        # 上传
        try:
            minio_url = object_store.put_object(
                object_name=object_name,
                data=image_bytes,
                content_type=f"image/{image_format}"
            )
            print(f"    [OK] Uploaded: {filename[:30]}... ({len(image_bytes)/1024:.1f} KB)")
            return minio_url
        except Exception as e:
            print(f"    [ERROR] Upload failed: {e}")
            return None

    def get_surrounding_context(
        self,
        markdown_text: str,
        image_marker: str,
        window_size: int = 150
    ) -> str:
        """
        获取图片标记前后各 window_size 个字符作为上下文

        Args:
            markdown_text: 完整的 Markdown 文本
            image_marker: 图片标记（如 "![图片](image_url)"）
            window_size: 前后上下文窗口大小（字符数）

        Returns:
            图片周围的上下文文本
        """
        marker_index = markdown_text.find(image_marker)
        if marker_index == -1:
            return "无上下文"

        start_index = max(0, marker_index - window_size)
        end_index = min(len(markdown_text), marker_index + len(image_marker) + window_size)

        # 截取前后文，并清理换行符
        context = markdown_text[start_index:end_index].replace('\n', ' ').strip()
        return context

    def generate_vlm_description(
        self,
        image_bytes: bytes,
        doc_title: str = "",
        surrounding_text: str = ""
    ) -> dict:
        """
        使用 VLM 生成图片描述（结合文档上下文）

        Args:
            image_bytes: 图片数据
            doc_title: 文档标题
            surrounding_text: 图片周围的文字上下文

        Returns:
            dict: {
                "short_title": "短标题",
                "detailed_description": "详细描述"
            }
        """
        from kb_service.processing.utils.vlm import understand_document_image

        if not self.vlm_enabled:
            return {
                "short_title": "文档图片",
                "detailed_description": "💡 **图片解析**：VLM 已禁用"
            }

        try:
            result = understand_document_image(
                image_data=image_bytes,
                doc_title=doc_title,
                surrounding_text=surrounding_text,
                max_length=100
            )

            # 验证返回值格式
            if not isinstance(result, dict):
                print(f"    [WARN] VLM returned unexpected type: {type(result)}")
                return {
                    "short_title": "文档图片",
                    "detailed_description": "💡 **图片解析**：VLM 返回格式错误"
                }

            # 确保有必需的字段
            if "short_title" not in result:
                result["short_title"] = "文档图片"
            if "detailed_description" not in result:
                result["detailed_description"] = "💡 **图片解析**：无详细描述"

            return result

        except Exception as e:
            print(f"    [WARN] VLM failed: {e}")
            return {
                "short_title": "文档图片",
                "detailed_description": f"💡 **图片解析失败**：{str(e)}"
            }

    def replace_images_in_markdown(
        self,
        md_content: str,
        images: List[Dict],
        kb_id: str,
        doc_id: str,
        doc_title: str = ""
    ) -> str:
        """
        替换 Markdown 中的图片标记（极简方案）

        Args:
            md_content: Markdown 内容
            images: 图片列表
            kb_id: 知识库 ID
            doc_id: 文档 ID
            doc_title: 文档标题（用于 VLM 理解上下文）

        Returns:
            替换后的 Markdown 内容
        """
        print("\n[STEP 3] Replacing image markers with MinIO URLs...")

        # 找到所有图片标记并直接替换（极简方案）
        pattern = r'!\[(.*?)\]\((.*?)\)'
        image_index = 0

        for match in re.finditer(pattern, md_content):
            alt_text = match.group(1)
            src = match.group(2)
            full_match = match.group(0)

            # 只处理 Base64 图片
            if not src.startswith('data:image'):
                continue

            # 获取对应的图片数据
            if image_index >= len(images):
                print(f"    [WARN] No image data for index {image_index}")
                image_index += 1
                continue

            img = images[image_index]
            image_index += 1

            # 上传到 MinIO
            print(f"\n  Image {image_index}/{len(images)}:")
            print(f"    Format: {img['format']}, Size: {len(img['bytes'])/1024:.1f} KB")
            print(f"    -> Uploading to MinIO...")

            minio_url = self.upload_image_to_minio(
                img['bytes'],
                img['format'],
                kb_id,
                doc_id
            )

            if not minio_url:
                print(f"    [X] Upload failed, keeping original marker")
                continue

            # 获取周围上下文
            print(f"    -> Extracting surrounding context...")
            surrounding_text = self.get_surrounding_context(md_content, full_match, window_size=150)
            print(f"    -> Context preview: {surrounding_text[:80]}...")

            # 调用 VLM 生成短标题和详细描述
            print(f"    -> Generating VLM description with context...")
            vlm_result = self.generate_vlm_description(
                img['bytes'],
                doc_title=doc_title,
                surrounding_text=surrounding_text
            )

            # 拼接新的 Markdown：![短标题](MinIO_URL)<br>💡 **图文解析**：详细描述
            bound_markdown = (
                f"![{vlm_result['short_title']}]({minio_url})"
                f"<br>💡 **图文解析**：{vlm_result['detailed_description']}"
            )

            # 🌟 极简方案：直接全文替换，限制替换次数为 1
            # 因为我们不依赖坐标了，所以不用担心字符串变长导致偏移
            md_content = md_content.replace(full_match, bound_markdown, 1)

            print(f"    -> Short title: {vlm_result['short_title']}")
            print(f"    [OK] Processed and Replaced")

        # 循环结束后，直接 return md_content
        print(f"\n[STEP 4] All replacements completed")
        print(f"  [OK] Replaced {image_index} images")

        return md_content

    def convert_word_to_markdown(
        self,
        word_file: str,
        kb_id: str,
        doc_id: str,
        doc_title: str = ""
    ) -> str:
        """
        混合处理 Word 文档：
        1. 使用 MarkItDown 获取 Markdown 文本（保留表格格式）
        2. 使用 Mammoth 提取完整 Base64 图片
        3. 上传图片到 MinIO
        4. 调用 VLM 生成描述（结合文档上下文）
        5. 替换图片标记

        Args:
            word_file: Word 文档路径
            kb_id: 知识库 ID
            doc_id: 文档 ID
            doc_title: 文档标题（用于 VLM 理解上下文）

        Returns:
            转换后的 Markdown 文本
        """
        print(f"\n{'='*80}")
        print(f"Hybrid Converter: MarkItDown Text + Mammoth Images + MinIO + VLM")
        print(f"{'='*80}\n")

        print(f"[INPUT] Word: {word_file}")
        print(f"        KB ID: {kb_id}")
        print(f"        Doc ID: {doc_id}")
        if doc_title:
            print(f"        Title: {doc_title}")
        print()

        try:
            # 步骤 1: 使用 MarkItDown 获取文本（保留表格格式）
            print("[STEP 1] Getting Markdown text from MarkItDown...")
            md_content = self.get_markitdown_text(word_file)

            # 步骤 2: 使用 Mammoth 提取完整图片
            print("\n[STEP 2] Extracting images from Mammoth...")
            _, images = self.extract_images_from_mammoth(word_file)

            if not images:
                # 没有图片，直接返回
                print(f"\n[SAVE] No images found, returning MarkItDown content")
                return md_content

            # 步骤 3-5: 替换图片、上传MinIO、生成VLM描述（带上下文）
            md_content = self.replace_images_in_markdown(md_content, images, kb_id, doc_id, doc_title)

            # 统计
            print(f"\n{'='*80}")
            print(f"Processing Complete!")
            print(f"{'='*80}")
            print(f"[STATISTICS]")
            print(f"        Total images: {len(images)}")
            print(f"        Final Markdown size: {len(md_content):,} chars")
            print(f"        Lines: {len(md_content.splitlines()):,}")

            # 统计表格
            table_count = md_content.count('|') // 2  # 粗略估计
            if table_count > 0:
                print(f"        Table markers: ~{table_count}")

            print(f"\n[SUCCESS] Hybrid conversion completed!")
            return md_content

        except Exception as e:
            print(f"\n[ERROR] Failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    def disable_vlm(self):
        """禁用 VLM 图片理解（用于快速测试或降级）"""
        self.vlm_enabled = False
        print("[HybridConverter] VLM disabled")

    def enable_vlm(self):
        """启用 VLM 图片理解"""
        self.vlm_enabled = True
        print("[HybridConverter] VLM enabled")
