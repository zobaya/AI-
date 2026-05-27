"""
解析器模块 - 将各种文件格式解析为 Markdown

支持的格式：
- DOCX: Word 文档
- PDF: PDF 文档
- XLSX: Excel 表格
- TXT: 纯文本
"""
from kb_service.processing.parsers.base import BaseParser, ParseResult
from kb_service.processing.parsers.registry import get_parser, PARSER_REGISTRY

__all__ = [
    "BaseParser",
    "ParseResult",
    "get_parser",
    "PARSER_REGISTRY",
]
