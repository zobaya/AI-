"""
TXT 文本提取工具
"""
from typing import Dict, Any, Tuple
import re
import logging
from abc import ABC

logger = logging.getLogger(__name__)


class TextExtractionTool(ABC):
    """简化版文本提取工具，支持TXT和Markdown格式文件处理"""
    name: str = "text_extractor"
    description: str = "文本提取工具，支持TXT和Markdown格式文件的文本提取"

    def __init__(self):
        pass

    def is_txt_file(self, file_name: str) -> bool:
        """检查是否为TXT或Markdown文件"""
        if not file_name:
            return False
        ext = file_name.lower().split('.')[-1]
        return ext in ['txt', 'text', 'md', 'markdown']

    def extract_text_from_txt(self, file_content: bytes) -> Tuple[str, str]:
        """从TXT文件中提取文本（尝试多种编码）"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        for encoding in encodings:
            try:
                return file_content.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        # 所有编码尝试失败时，使用replace模式容错
        return file_content.decode('utf-8', errors='replace'), 'unknown'

    def clean_text(self, text: str) -> str:
        """清理文本（去除多余空白、首尾空格）"""
        return re.sub(r'\s+', ' ', text).strip()

    def run(self, **kwargs) -> Dict[str, Any]:
        """执行文本提取，返回标准格式结果"""
        try:
            file_content = kwargs.get("file_content")
            file_name = kwargs.get("file_name", "")

            # 检查文件类型
            if not self.is_txt_file(file_name):
                return {
                    "success": False,
                    "error": f"不支持的文件类型，仅支持TXT和Markdown文件。当前文件: {file_name}"
                }

            # 处理文件内容类型
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')
            if not isinstance(file_content, bytes):
                return {
                    "success": False,
                    "error": "文件内容必须为bytes或str类型"
                }

            # 提取文本和编码
            original_text, encoding = self.extract_text_from_txt(file_content)
            cleaned_text = self.clean_text(original_text)

            # 分块处理
            chunks = [chunk.strip() for chunk in original_text.split('\n') if chunk.strip()]
            chunk_count = len(chunks) if chunks else 1

            # 生成标准document对象
            document = {
                "page_content": cleaned_text,
                "metadata": {
                    "filename": file_name,
                    "encoding": encoding,
                    "word_count": len(cleaned_text.split()),  # 简单词数统计
                    "character_count": len(cleaned_text),
                    "page": 1  # TXT默认单页
                },
                "txt_specific": {
                    "original_text": original_text,
                    "chunks": chunks,
                    "chunk_count": chunk_count
                }
            }

            # 返回可直接存入state的结果
            return {
                "success": True,
                "documents": [document]  # 统一用列表包裹，与其他工具格式一致
            }

        except Exception as e:
            error_msg = f"文本文件处理失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
