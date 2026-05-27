"""
文件解析工具 - 使用本地 ToolManager 和 Extractor

从 MinIO 下载文件 → 调用对应 Extractor → 返回提取的文本。
"""
import logging
import traceback
from typing import Optional

from langchain_core.callbacks.manager import adispatch_custom_event

from core.object_store import object_store
from src.harness.subgraphs.file_parse.tool import ToolManager
from src.harness.subgraphs.file_parse.extractors.pdf_extractor import PDFExtractionTool
from src.harness.subgraphs.file_parse.extractors.word_extractor import WordExtractionTool
from src.harness.subgraphs.file_parse.extractors.excel_extractor import ExcelExtractionTool
from src.harness.subgraphs.file_parse.extractors.text_extractor import TextExtractionTool
from src.harness.subgraphs.file_parse.extractors.ppt_extractor import PPTExtractionTool

logger = logging.getLogger(__name__)

# 单例 ToolManager
_tool_manager: Optional[ToolManager] = None


def _get_tool_manager() -> ToolManager:
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = ToolManager()
        _tool_manager.register_tool(PDFExtractionTool())
        _tool_manager.register_tool(WordExtractionTool())
        _tool_manager.register_tool(ExcelExtractionTool())
        _tool_manager.register_tool(TextExtractionTool())
        _tool_manager.register_tool(PPTExtractionTool())
    return _tool_manager


async def file_parse(file_path: str, display_name: str = None, config=None) -> str:
    """
    解析文件，返回提取的文本内容。

    Args:
        file_path: MinIO 文件路径（如 knowledge-base/xxx.pdf）
        display_name: 展示用文件名（原始文件名，如 工作汇报.docx）
        config: LangGraph config（用于发送进度事件）

    Returns:
        格式化的文本内容（供 LLM 阅读）
    """

    async def _progress(message: str):
        """发送进度事件（如果 config 可用）"""
        if config:
            try:
                await adispatch_custom_event(
                    "progress",
                    {"node": "file_parse", "message": message},
                    config=config,
                )
            except Exception:
                pass

    try:
        filename = display_name or (file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path)

        # 从 MinIO 获取文件内容
        await _progress(f"📥 正在下载文件「{filename}」...")
        content = object_store.get_object(file_path)
        await _progress(f"✅ 文件下载完成（{len(content)} 字节）")

        # 根据扩展名选择提取器
        ext_to_tool = {
            ".pdf": "pdf_extractor",
            ".docx": "word_extractor",
            ".xlsx": "excel_extractor",
            ".xls": "excel_extractor",
            ".pptx": "ppt_extractor",
            ".txt": "text_extractor",
            ".md": "text_extractor",
        }

        tool_name = next(
            (v for k, v in ext_to_tool.items() if filename.lower().endswith(k)),
            None,
        )

        if not tool_name:
            return f"不支持的文件类型：{filename}。支持的格式：.pdf, .docx, .xlsx, .pptx, .txt"

        # 执行提取
        await _progress(f"📄 正在解析「{filename}」...")
        tm = _get_tool_manager()
        result = tm.execute_tool(tool_name, file_content=content, file_name=filename)

        if not result.get("success"):
            return f"文件解析失败：{result.get('error', '未知错误')}"

        docs = result.get("documents", [])
        if not docs:
            return f"文件「{filename}」解析成功，但未提取到文本内容。"

        await _progress(f"✅ 解析完成，提取到 {len(docs)} 个片段")

        # 格式化为 LLM 可读的文本
        parts = [f"文件「{filename}」解析结果（共 {len(docs)} 个片段）：\n"]

        for i, doc in enumerate(docs, 1):
            text = doc.get("text", doc.get("content", doc.get("page_content", "")))
            if text:
                parts.append(f"--- 片段 {i} ---")
                parts.append(text)
                parts.append("")

        return "\n".join(parts)

    except Exception as e:
        logger.error(f"[file_parse] Error: {e}\n{traceback.format_exc()}")
        return f"文件解析失败：{str(e)}"
