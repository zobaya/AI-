"""
公共工具函数 - 用于 kb_service 文档处理
"""
import re
from typing import Dict, List


def extract_title_from_filename(file_name: str) -> str:
    """从文件名提取语义标题"""
    if not file_name:
        return "未命名文档"
    name = re.sub(r'\.[^.]+$', '', file_name)
    name = re.sub(r'\d{4}[-/_]?\d{2}[-/_]?\d{2}', '', name)
    name = re.sub(r'_?[vV]\d+(\.\d+)?', '', name)
    name = re.sub(r'[【\[].*?[】\]]', '', name)
    name = re.sub(r'[_\-]+', ' ', name)
    name = ' '.join(name.split())
    return name if name else "未命名文档"


def metadata_to_header_path(metadata: Dict) -> str:
    """将 LangChain 的 metadata 转换为标题路径字符串

    MarkdownHeaderTextSplitter 返回的键名由 headers_to_split_on 配置决定：
    - headers_to_split_on=[("#", "H1"), ...] → metadata 键为 "H1", "H2", "H3"
    """
    headers = []
    # 尝试 H1/H2/H3 格式（MarkdownHeaderTextSplitter 默认）
    for i in range(1, 4):
        header_key = f"H{i}"
        if header_key in metadata and metadata[header_key]:
            headers.append(metadata[header_key])
    # 如果没有 H1/H2/H3，尝试 Header 1/2/3 格式（兼容旧代码）
    if not headers:
        for i in range(1, 4):
            header_key = f"Header {i}"
            if header_key in metadata and metadata[header_key]:
                headers.append(metadata[header_key])
    return " > ".join(headers) if headers else ""


def get_common_path(paths: List[str]) -> str:
    """计算多个路径的最长公共祖先（LCA）"""
    if not paths:
        return ""
    if len(paths) == 1:
        return paths[0]
    first_parts = paths[0].split(" > ")
    common_parts = []
    for i, part in enumerate(first_parts):
        if all(path.split(" > ")[i] == part for path in paths if len(path.split(" > ")) > i):
            common_parts.append(part)
        else:
            break
    return " > ".join(common_parts)


def detect_modality(text: str) -> str:
    """检测文本块的模态类型"""
    if "\t" in text and text.count("\t") > 3:
        return "table"
    lines = text.strip().split("\n")
    if len(lines) > 2:
        space_separated = sum(1 for line in lines if len(line.split()) > 3)
        if space_separated >= 3:
            return "table"
    return "text"


def clean_markdown_images(markdown_text: str) -> str:
    """清理 Markdown 中的图片标记"""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', markdown_text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()
