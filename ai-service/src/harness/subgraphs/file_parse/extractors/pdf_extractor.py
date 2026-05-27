"""
PDF 文档提取工具 - 优先使用 MinerU API，降级使用 PyPDF
"""
import os
import re
import logging
import tempfile
import requests
from typing import Dict, Any
from abc import ABC
from langchain_community.document_loaders import PyPDFLoader
from core.config import settings

logger = logging.getLogger(__name__)


class PDFExtractionTool(ABC):
    """PDF 提取工具 - 优先使用 MinerU API（支持扫描件 OCR），降级使用 PyPDF"""

    name: str = "pdf_extractor"
    description: str = "PDF 文件提取工具，支持扫描件 OCR 解析（MinerU API）"

    def __init__(self):
        # 从配置读取 MinerU API 地址
        self.mineru_api_url = settings.MINERU_API_URL
        self.mineru_timeout = 300  # QA Service 场景使用较短超时
        logger.info(f"[PDF] MinerU API: {self.mineru_api_url}")

    def is_pdf_file(self, file_name: str) -> bool:
        """检查是否为 PDF 文件"""
        if not file_name:
            return False
        return file_name.lower().endswith(".pdf")

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        执行 PDF 提取

        策略：
        1. 优先使用 MinerU API（支持扫描件 OCR）
        2. MinerU 失败时降级到 PyPDF（仅支持文本 PDF）
        """
        file_content = kwargs.get("file_content")
        file_name = kwargs.get("file_name", "")

        try:
            # 验证文件类型
            if not self.is_pdf_file(file_name):
                return {
                    "success": False,
                    "error": f"不支持的文件类型，仅支持 PDF 文件。当前文件: {file_name}"
                }

            logger.info(f"[PDF] 开始解析: {file_name}")
            logger.info(f"[PDF] 文件大小: {len(file_content)} 字节")

            # 策略1: 优先使用 MinerU API
            result = self._try_mineru_parser(file_content, file_name)
            if result["success"]:
                logger.info(f"[PDF] ✅ MinerU 解析成功")
                return result

            # 策略2: 降级到 PyPDF
            logger.warning(f"[PDF] ⚠️ MinerU 失败，降级到 PyPDF")
            result = self._try_pypdf_parser(file_content, file_name)
            if result["success"]:
                logger.info(f"[PDF] ✅ PyPDF 解析成功（降级方案）")
            return result

        except Exception as e:
            error_msg = f"PDF 文件处理失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "documents": []
            }

    def _try_mineru_parser(self, file_content: bytes, file_name: str) -> Dict[str, Any]:
        """
        策略1: 使用 MinerU API 解析 PDF（支持扫描件 OCR）

        返回：
            {
                "success": bool,
                "documents": [{"page_content": str, "metadata": dict}],
                "error": str (如果失败)
            }
        """
        temp_file = None
        try:
            # 1. 保存临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_file.write(file_content)
            temp_file.close()

            logger.info(f"[PDF] [MinerU] 调用 API: {self.mineru_api_url}")

            # 2. 调用 MinerU API
            file_stem = os.path.splitext(file_name)[0]
            payload = {
                "return_md": True,
                "return_images": False,  # 不需要图片
                "backend": "hybrid-auto-engine"
            }

            with open(temp_file.name, "rb") as f:
                files = {"files": (file_name, f, "application/pdf")}
                response = requests.post(
                    self.mineru_api_url,
                    files=files,
                    data=payload,
                    timeout=self.mineru_timeout
                )

            # 3. 检查响应
            if response.status_code != 200:
                error_msg = f"API 返回错误: {response.status_code} - {response.text[:200]}"
                logger.warning(f"[PDF] [MinerU] ❌ {error_msg}")
                return {"success": False, "error": error_msg}

            # 4. 解析响应
            result_json = response.json()
            result_data = result_json.get("results", {}).get(file_stem, {})
            markdown_text = result_data.get("md_content", "")

            if not markdown_text:
                error_msg = "API 未返回 Markdown 内容"
                logger.warning(f"[PDF] [MinerU] ❌ {error_msg}")
                return {"success": False, "error": error_msg}

            logger.info(f"[PDF] [MinerU] ✅ 解析成功，文本长度: {len(markdown_text)} 字符")

            # 5. 移除图片标记，只保留文本
            cleaned_markdown = self._remove_image_markers(markdown_text)
            logger.info(f"[PDF] [MinerU] 已移除图片标记，清理后长度: {len(cleaned_markdown)} 字符")

            # 6. 返回标准格式
            return {
                "success": True,
                "documents": [{
                    "page_content": cleaned_markdown,
                    "metadata": {
                        "source": file_name,
                        "parser": "mineru"
                    }
                }],
                "document_count": 1
            }

        except requests.exceptions.Timeout:
            error_msg = f"MinerU API 超时（>{self.mineru_timeout}秒）"
            logger.warning(f"[PDF] [MinerU] ⏱️ {error_msg}")
            return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"MinerU 解析出错: {str(e)}"
            logger.warning(f"[PDF] [MinerU] ❌ {error_msg}")
            return {"success": False, "error": error_msg}

        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass

    def _try_pypdf_parser(self, file_content: bytes, file_name: str) -> Dict[str, Any]:
        """
        策略2: 降级使用 PyPDF 解析（仅支持文本 PDF）

        返回：
            {
                "success": bool,
                "documents": [{"page_content": str, "metadata": dict}],
                "error": str (如果失败)
            }
        """
        temp_path = None
        try:
            # 1. 保存临时文件
            temp_path = f"temp_{os.getpid()}.pdf"
            with open(temp_path, "wb") as f:
                f.write(file_content)

            logger.info(f"[PDF] [PyPDF] 开始解析...")

            # 2. 使用 PyPDFLoader 解析
            loader = PyPDFLoader(temp_path)
            documents = loader.load_and_split()

            # 3. 清理临时文件
            os.remove(temp_path)

            if not documents:
                error_msg = "PyPDF 未能提取到任何内容"
                logger.warning(f"[PDF] [PyPDF] ⚠️ {error_msg}")
                return {"success": False, "error": error_msg}

            logger.info(f"[PDF] [PyPDF] ✅ 解析成功，提取 {len(documents)} 个页面")

            # 4. 转换为标准格式
            serialized_documents = []
            for doc in documents:
                serialized_doc = {
                    "page_content": doc.page_content,
                    "metadata": {
                        **doc.metadata,
                        "source": file_name,
                        "parser": "pypdf"
                    }
                }
                serialized_documents.append(serialized_doc)

            return {
                "success": True,
                "documents": serialized_documents,
                "document_count": len(serialized_documents)
            }

        except Exception as e:
            error_msg = f"PyPDF 解析失败: {str(e)}"
            logger.error(f"[PDF] [PyPDF] ❌ {error_msg}")

            # 确保清理临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

            return {
                "success": False,
                "error": error_msg,
                "documents": []
            }

    def _remove_image_markers(self, markdown: str) -> str:
        """
        移除 Markdown 中的图片标记，只保留文本

        Examples:
            输入: "![图1](images/fig1.png) 这是一个图片\n\n# 标题\n内容"
            输出: "# 标题\n内容"
        """
        # 1. 移除标准 Markdown 图片格式 ![alt](url)
        markdown = re.sub(r'!\[.*?\]\(.*?\)', '', markdown, flags=re.DOTALL)

        # 2. 移除多余的空行（超过2个连续换行符替换为2个）
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        # 3. 移除首尾空白
        markdown = markdown.strip()

        return markdown
