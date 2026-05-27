"""
解析器注册表 - 根据文件扩展名路由到对应的解析器
"""
from kb_service.processing.parsers.base import BaseParser
from kb_service.processing.parsers.docx_parser import DOCXParser
from kb_service.processing.parsers.pdf_parser import PDFParser

# 解析器注册表
PARSER_REGISTRY = {}

# 注册内置解析器
for ext in DOCXParser().supported_extensions():
    PARSER_REGISTRY[ext] = DOCXParser

for ext in PDFParser().supported_extensions():
    PARSER_REGISTRY[ext] = PDFParser

print(f"[ParserRegistry] Initialized with supported formats: {list(PARSER_REGISTRY.keys())}")


def get_parser(file_ext: str) -> BaseParser:
    """
    根据文件扩展名获取对应的解析器实例

    Args:
        file_ext: 文件扩展名（如 ".docx"）

    Returns:
        BaseParser: 解析器实例

    Raises:
        ValueError: 不支持的文件格式
    """
    file_ext = file_ext.lower()
    parser_class = PARSER_REGISTRY.get(file_ext)

    if not parser_class:
        supported = ", ".join(PARSER_REGISTRY.keys())
        raise ValueError(
            f"Unsupported file format: {file_ext}. "
            f"Supported formats: {supported}"
        )

    return parser_class()


def list_supported_formats() -> list:
    """返回所有支持的文件格式列表"""
    return sorted(PARSER_REGISTRY.keys())
