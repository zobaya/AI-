"""
DOCX 解析器 - 将 Word 文档解析为 Markdown
"""
import os
import tempfile
from typing import List
from kb_service.processing.parsers.base import BaseParser, ParseResult, ImageInfo


class DOCXParser(BaseParser):
    """
    DOCX 解析器

    使用 hybrid_converter 将 DOCX 转换为 Markdown
    """

    def supported_extensions(self) -> List[str]:
        return [".docx"]

    def parse(
        self,
        file_data: bytes,
        file_name: str,
        kb_id: str = None,
        doc_id: str = None
    ) -> ParseResult:
        """
        解析 DOCX 文件为 Markdown

        Args:
            file_data: 文件字节数据
            file_name: 文件名
            kb_id: 知识库 ID
            doc_id: 文档 ID

        Returns:
            ParseResult: 解析结果
        """
        try:
            # 保存临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
                tmp_file.write(file_data)
                tmp_file_path = tmp_file.name

            # 使用 HybridConverter（MarkItDown + Mammoth + VLM）
            from kb_service.processing.common.hybrid_converter import HybridConverter

            converter = HybridConverter()
            markdown_text = converter.convert_word_to_markdown(
                tmp_file_path,
                kb_id=kb_id,
                doc_id=doc_id,
                doc_title=file_name
            )

            # 清理临时文件
            os.unlink(tmp_file_path)

            return ParseResult(
                success=True,
                markdown=markdown_text,
                images=[],
                metadata={
                    "file_name": file_name,
                    "kb_id": kb_id,
                    "doc_id": doc_id
                },
                file_name=file_name
            )

        except Exception as e:
            return ParseResult(
                success=False,
                error=f"DOCX 解析失败: {str(e)}"
            )
