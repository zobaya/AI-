"""
Excel 文档提取工具 - 使用 LangChain 的 UnstructuredExcelLoader
"""
import os
import logging
from typing import Literal, Dict, Any
from abc import ABC
from langchain_community.document_loaders import UnstructuredExcelLoader

logger = logging.getLogger(__name__)


class ExcelExtractionTool(ABC):
    """Excel 提取工具，支持表格内容提取"""
    name: str = "excel_extractor"
    description: str = "Excel 文件提取工具，支持提取 Excel 中的表格内容，支持 .xlsx 和 .xls 格式"

    def __init__(self):
        pass

    def is_excel_file(self, file_name: str) -> bool:
        """检查是否为 Excel 文件"""
        if not file_name:
            return False
        ext = file_name.lower().split('.')[-1]
        return ext in ['xlsx', 'xls']

    def run(self, **kwargs) -> Dict[str, Any]:
        """执行 Excel 提取"""
        file_content = kwargs.get("file_content")
        file_name = kwargs.get("file_name", "")
        mode: Literal["single", "elements"] = kwargs.get("mode", "single")
        sheet_name = kwargs.get("sheet_name")
        temp_path = None

        try:
            # 验证文件类型
            if not self.is_excel_file(file_name):
                return {
                    "success": False,
                    "error": f"不支持的文件类型，仅支持 .xlsx 或 .xls 文件。当前文件: {file_name}"
                }

            # 临时保存文件内容
            temp_path = f"temp_{os.getpid()}.xlsx"
            with open(temp_path, "wb") as f:
                f.write(file_content)

            # 加载 Excel
            loader = UnstructuredExcelLoader(
                file_path=temp_path,
                sheet_name=sheet_name,
                mode=mode,
                strategy="fast"
            )
            documents = loader.load()

            # 清理临时文件
            os.remove(temp_path)

            # 转换为可序列化格式
            result = {
                "success": True,
                "documents": [
                    {
                        "page_content": doc.page_content,
                        "metadata": doc.metadata
                    } for doc in documents
                ]
            }
            return result

        except Exception as e:
            error_msg = f"Excel 文件处理失败: {str(e)}"
            logger.error(error_msg)

            # 确保清理临时文件
            try:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass

            return {
                "success": False,
                "error": error_msg
            }
