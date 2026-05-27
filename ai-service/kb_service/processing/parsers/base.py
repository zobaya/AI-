"""
解析器基类 - 定义所有解析器的统一接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ImageInfo:
    """图片信息"""
    filename: str              # 图片文件名
    minio_url: str             # MinIO 中的 URL
    content_type: str          # MIME 类型
    size: int = 0              # 文件大小（字节）


@dataclass
class ParseResult:
    """
    解析结果统一格式

    所有解析器都必须返回此格式
    """
    success: bool              # 是否成功
    markdown: str = ""         # Markdown 文本内容
    images: List[ImageInfo] = field(default_factory=list)  # 提取的图片列表
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据
    error: str = ""            # 错误信息（如果失败）

    # 以下字段用于特定场景（可选）
    md_path: Optional[str] = None  # MinIO 中 MD 文件的路径（PDF 使用）
    file_name: str = ""        # 原始文件名

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "success": self.success,
            "markdown": self.markdown,
            "images": [img.__dict__ for img in self.images],
            "metadata": self.metadata,
            "error": self.error,
            "md_path": self.md_path,
            "file_name": self.file_name,
        }


class BaseParser(ABC):
    """
    解析器基类

    所有解析器必须继承此类并实现 parse() 方法
    """

    @abstractmethod
    def parse(
        self,
        file_data: bytes,
        file_name: str,
        kb_id: str = None,
        doc_id: str = None
    ) -> ParseResult:
        """
        解析文件为 Markdown

        Args:
            file_data: 文件字节数据
            file_name: 文件名（含扩展名）
            kb_id: 知识库 ID（可选）
            doc_id: 文档 ID（可选）

        Returns:
            ParseResult: 统一格式的解析结果
        """
        pass

    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """
        返回支持的文件扩展名列表

        Examples:
            return [".docx", ".doc"]
        """
        pass

    def is_supported(self, file_ext: str) -> bool:
        """检查是否支持该文件扩展名"""
        return file_ext.lower() in self.supported_extensions()
