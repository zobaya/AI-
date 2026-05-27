"""
PDF 解析器 - 使用 MinerU 将 PDF 解析为 Markdown
"""
import os
import base64
import tempfile
from typing import List
from kb_service.processing.parsers.base import BaseParser, ParseResult, ImageInfo
from core.object_store import object_store


class PDFParser(BaseParser):
    """
    PDF 解析器

    使用 MinerU API 将 PDF 转换为 Markdown，提取图片上传到 MinIO
    """

    def supported_extensions(self) -> List[str]:
        return [".pdf"]

    def parse(
        self,
        file_data: bytes,
        file_name: str,
        kb_id: str = None,
        doc_id: str = None
    ) -> ParseResult:
        """
        解析 PDF 文件为 Markdown

        Args:
            file_data: 文件字节数据
            file_name: 文件名
            kb_id: 知识库 ID
            doc_id: 文档 ID

        Returns:
            ParseResult: 解析结果
        """
        tmp_file_path = None
        try:
            print(f"[PDFParser] 开始解析: {file_name}")

            # 1. 保存到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(file_data)
                tmp_file_path = tmp_file.name

            # 2. 调用 MinerU API 获取 markdown + images
            from kb_service.processing.common.mineru_processor import MinerUProcessor

            processor = MinerUProcessor()
            api_result = processor._call_mineru_api(tmp_file_path, kb_id, doc_id)

            if not api_result:
                return ParseResult(
                    success=False,
                    error="MinerU API 解析失败"
                )

            markdown_content = api_result.get("markdown", "")
            images_dict = api_result.get("images", {})

            if not markdown_content:
                return ParseResult(
                    success=False,
                    error="MinerU 未返回 Markdown 内容"
                )

            print(f"[PDFParser] API 解析成功: {len(markdown_content)} 字符, {len(images_dict)} 张图片")

            # 3. 上传图片到 MinIO，替换 MD 中的图片引用
            image_infos = []
            if images_dict and kb_id and doc_id:
                image_infos = self._upload_images(
                    markdown_content, images_dict, kb_id, doc_id
                )
                # 用上传后的 URL 替换 markdown 中的图片引用
                markdown_content = self._replace_image_refs(
                    markdown_content, image_infos
                )

            print(f"[PDFParser] 解析完成: {len(markdown_content)} 字符, {len(image_infos)} 张图片已上传")

            return ParseResult(
                success=True,
                markdown=markdown_content,
                images=image_infos,
                metadata={
                    "file_name": file_name,
                    "kb_id": kb_id,
                    "doc_id": doc_id,
                    "images_count": len(image_infos),
                },
                file_name=file_name,
            )

        except Exception as e:
            return ParseResult(
                success=False,
                error=f"PDF 解析失败: {str(e)}"
            )
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                except OSError:
                    pass

    def _upload_images(
        self,
        markdown_content: str,
        images_dict: dict,
        kb_id: str,
        doc_id: str,
    ) -> List[ImageInfo]:
        """
        将图片上传到 MinIO

        Args:
            markdown_content: Markdown 文本（用于日志）
            images_dict: MinerU 返回的图片字典 {filename: base64_data}
            kb_id: 知识库 ID
            doc_id: 文档 ID

        Returns:
            上传成功的 ImageInfo 列表
        """
        image_infos = []
        for img_filename, img_base64_raw in images_dict.items():
            try:
                # 清洗 Base64 前缀
                if "," in img_base64_raw:
                    img_base64_clean = img_base64_raw.split(",", 1)[1]
                else:
                    img_base64_clean = img_base64_raw

                img_bytes = base64.b64decode(img_base64_clean)

                # 确定图片格式
                img_ext = os.path.splitext(img_filename)[1].lower().strip(".")
                content_type_map = {
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "gif": "image/gif",
                    "bmp": "image/bmp",
                    "webp": "image/webp",
                }
                content_type = content_type_map.get(img_ext, "application/octet-stream")

                # MinIO 路径: {kb_id}/{doc_id}/images/{filename}
                object_name = f"{kb_id}/{doc_id}/images/{img_filename}"

                minio_url = object_store.put_object(
                    object_name=object_name,
                    data=img_bytes,
                    content_type=content_type,
                )

                if minio_url:
                    image_infos.append(ImageInfo(
                        filename=img_filename,
                        minio_url=minio_url,
                        content_type=content_type,
                        size=len(img_bytes),
                    ))

            except Exception as e:
                print(f"[PDFParser] [WARN] 图片上传失败 {img_filename}: {e}")

        return image_infos

    def _replace_image_refs(
        self,
        markdown_content: str,
        image_infos: List[ImageInfo],
    ) -> str:
        """
        替换 Markdown 中的图片引用为 MinIO URL

        MinerU 生成的图片引用格式: ![](images/xxx.jpg)

        Args:
            markdown_content: 原始 Markdown 文本
            image_infos: 上传成功的图片信息列表

        Returns:
            替换后的 Markdown 文本
        """
        for img_info in image_infos:
            old_ref = f"images/{img_info.filename}"
            markdown_content = markdown_content.replace(old_ref, img_info.minio_url)
        return markdown_content
