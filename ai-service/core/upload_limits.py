"""
文件上传限制配置 - 基于 Token 上下文
"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class FileUploadConfig(BaseModel):
    """文件上传配置"""

    # ========== Token 上下文配置 ==========
    MAX_MODEL_LEN: int = Field(
        default=40960,
        description="vLLM 最大模型长度（tokens）"
    )
    RESERVED_FOR_HISTORY: int = Field(
        default=5000,
        description="为历史对话预留的 tokens"
    )
    RESERVED_FOR_OUTPUT: int = Field(
        default=5000,
        description="为模型输出预留的 tokens"
    )
    RESERVED_FOR_QUESTION: int = Field(
        default=1000,
        description="为用户问题预留的 tokens"
    )

    @property
    def AVAILABLE_FOR_DOCUMENTS(self) -> int:
        """可用于文档内容的 tokens"""
        return (
            self.MAX_MODEL_LEN
            - self.RESERVED_FOR_HISTORY
            - self.RESERVED_FOR_OUTPUT
            - self.RESERVED_FOR_QUESTION
        )  # 约 30K tokens

    # ========== 文件大小限制 ==========
    MAX_FILE_SIZE: int = Field(
        default=50 * 1024 * 1024,  # 50 MB（从 10MB 增加）
        description="单个文件最大大小（字节）"
    )

    # ========== 文件数量限制 ==========
    MAX_FILES_PER_UPLOAD: int = Field(
        default=5,  # 从 3 个增加到 5 个
        description="单次上传最大文件数量"
    )

    # ========== Token 估算配置 ==========
    # 不同文件类型的 token 密度（tokens per byte）
    # 注意：
    # - .docx/.xlsx/.pptx 是 ZIP 压缩格式，包含大量结构信息
    # - .pdf 可能包含扫描图像（图片型）或纯文本（电子版）
    TOKEN_DENSITY: Dict[str, float] = Field(
        default={
            ".txt": 0.5,      # 纯文本：1 字节 ≈ 0.5 token（UTF-8 编码，中文字符）
            ".md": 0.5,       # Markdown：同纯文本
            ".pdf": 0.01,     # PDF: 保守估算（可能是扫描图片或电子版）
                            #      配合更大的单文件限制，实际超限时会在 prompt 截断
            ".docx": 0.025,   # Word: ZIP 压缩 + XML 结构，实际文本内容远小于文件大小
            ".xlsx": 0.015,   # Excel: ZIP 压缩 + 表格结构，内容最紧凑
            ".xls": 0.015,
            ".pptx": 0.005,   # PowerPoint: ZIP 压缩，通常包含大量图片/视频，文本密度很低
        },
        description="不同文件类型的 token 密度"
    )

    MAX_TOKENS_PER_FILE: int = Field(
        default=150000,  # 150K tokens（从 100K 增加，约 300,000 字）
        description="单个文件最大 tokens（实际超限会在 prompt 阶段智能截断）"
    )

    # ========== 智能处理选项 ==========
    ENABLE_SOFT_LIMIT: bool = Field(
        default=True,
        description="启用软限制（超出时警告但允许处理）"
    )

    WARN_THRESHOLD: float = Field(
        default=0.8,  # 80% 时警告
        description="警告阈值（占总预算的比例）"
    )

    # ========== 支持的文件格式 ==========
    ALLOWED_EXTENSIONS: List[str] = Field(
        default=[".pdf", ".docx", ".xlsx", ".pptx", ".xls", ".txt", ".md"],
        description="允许上传的文件扩展名"
    )

    def estimate_tokens(self, file_size: int, file_ext: str) -> int:
        """
        估算文件的 token 数量

        Args:
            file_size: 文件大小（字节）
            file_ext: 文件扩展名

        Returns:
            估算的 token 数量
        """
        density = self.TOKEN_DENSITY.get(file_ext.lower(), 0.5)
        estimated_tokens = int(file_size * density)

        # 考虑格式化开销（Markdown、XML 等标记）
        overhead = 1.2  # 增加 20% 的开销

        return int(estimated_tokens * overhead)

    def can_upload_file(
        self,
        file_size: int,
        file_ext: str,
        current_total_tokens: int = 0
    ) -> tuple[bool, bool, str]:
        """
        检查是否可以上传文件

        Returns:
            (can_upload, should_warn, message)
            - can_upload: 是否允许上传
            - should_warn: 是否需要警告
            - message: 提示消息
        """
        # 检查 1: 文件格式
        if file_ext.lower() not in self.ALLOWED_EXTENSIONS:
            # 特殊提示：.doc/.ppt 旧格式
            if file_ext.lower() in ['.doc', '.ppt']:
                hint = (
                    f"不支持的旧格式: {file_ext}。请转换为新版格式："
                    f"\n  - .ppt → .pptx（在 PowerPoint 中'另存为 .pptx'）"
                    f"\n  - .doc → .docx（在 Word 中'另存为 .docx'）"
                    f"\n支持的格式: {', '.join(self.ALLOWED_EXTENSIONS)}"
                )
                return False, False, hint
            return False, False, f"不支持的文件格式: {file_ext}，支持: {', '.join(self.ALLOWED_EXTENSIONS)}"

        # 检查 2: 文件大小（硬限制）
        if file_size > self.MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            return False, False, f"文件过大: {size_mb:.1f}MB（最大 {self.MAX_FILE_SIZE / (1024 * 1024):.0f}MB）"

        # 检查 3: Token 预算（软限制 + 智能处理）
        estimated_tokens = self.estimate_tokens(file_size, file_ext)
        total_tokens = current_total_tokens + estimated_tokens
        budget_ratio = total_tokens / self.AVAILABLE_FOR_DOCUMENTS

        # 超出很多，但允许处理（PPTX/PDF 等可能包含大量图片，估算虚高）
        # 超出 4 倍才拒绝（从 2 倍放宽）
        if estimated_tokens > self.MAX_TOKENS_PER_FILE * 4:
            return False, False, f"文件过大: 约 {estimated_tokens:,} tokens（建议 {self.MAX_TOKENS_PER_FILE:,} tokens，约 {self.MAX_TOKENS_PER_FILE / 0.5:,} 字）"

        # 接近或略微超出预算，允许但警告
        if budget_ratio > 1.2:  # 超出 20%
            return True, True, f"文档内容较多: 约 {estimated_tokens:,} tokens，系统将智能处理"

        # 在预算内
        if budget_ratio > self.WARN_THRESHOLD:  # 超出 80%
            return True, True, f"文档较大: 约 {estimated_tokens:,} tokens（剩余 {self.AVAILABLE_FOR_DOCUMENTS - current_total_tokens:,} tokens）"

        return True, False, ""

    def get_upload_summary(self) -> Dict:
        """获取上传配置摘要（用于前端显示）"""
        return {
            "max_file_size_mb": self.MAX_FILE_SIZE / (1024 * 1024),
            "max_files": self.MAX_FILES_PER_UPLOAD,
            "allowed_extensions": self.ALLOWED_EXTENSIONS,
            "max_tokens_per_file": self.MAX_TOKENS_PER_FILE,
            "max_tokens_per_file_words": self.MAX_TOKENS_PER_FILE * 2,  # 约 50,000 字
            "available_tokens": self.AVAILABLE_FOR_DOCUMENTS,
            "available_tokens_words": self.AVAILABLE_FOR_DOCUMENTS * 2,  # 约 60,000 字
            "model_max_tokens": self.MAX_MODEL_LEN,
            "soft_limit_enabled": self.ENABLE_SOFT_LIMIT,
        }


# 全局配置实例
upload_config = FileUploadConfig()
