"""MinerU 文档解析处理器 - 智能提取文档结构"""
import os
import base64
import requests
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from core.config import settings
from core.object_store import object_store


@dataclass
class HeaderInfo:
    """标题信息"""
    title: str              # 标题文本
    level: int              # 标题级别 (1-6)
    line_number: int        # 在文档中的行号
    raw_line: str           # 原始行内容

# 强制使用 API 模式（不使用本地 MinerU）
LOCAL_MINERU_AVAILABLE = False


class MinerUProcessor:
    """MinerU 文档解析处理器"""

    _initialized = False  # 类变量，跟踪是否已初始化

    def __init__(self):
        """初始化 MinerU 处理器"""
        self.api_url = settings.MINERU_API_URL
        self.api_timeout = settings.MINERU_API_TIMEOUT  # 从配置读取超时时间
        self.use_local = False  # 强制使用 API 模式

        # 只打印一次初始化信息
        if not MinerUProcessor._initialized:
            MinerUProcessor._initialized = True
            print(f" MinerU 处理器初始化完成")
            print(f"   API 地址: {self.api_url}")
            print(f"   超时时间: {self.api_timeout} 秒")
            print(f"   模式: API 调用")

    def _call_mineru_api(self, file_path: str, kb_id: str = None, doc_id: str = None) -> Optional[Dict]:
        """
        调用 MinerU API 解析文档（简单模式）

        基于 rag_minio_ingestion.py 的实现方式
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                print(f"[ERROR] 文件不存在: {file_path}")
                return None

            filename = file_path_obj.name
            file_stem = file_path_obj.stem

            print(f" 调用 MinerU API 解析文档: {filename}")

            # 准备请求
            payload = {
                "return_md": True,
                "return_images": True,
                "backend": "hybrid-auto-engine"
            }

            with open(file_path, "rb") as f:
                files = {"files": (filename, f, "application/pdf")}

                response = requests.post(
                    self.api_url,
                    files=files,
                    data=payload,
                    timeout=self.api_timeout
                )

            if response.status_code != 200:
                print(f"[ERROR] API 请求失败: {response.status_code} - {response.text}")
                return None

            result_json = response.json()

            # 提取属于这个文件的数据块
            result_data = result_json.get("results", {}).get(file_stem, {})

            markdown_text = result_data.get("md_content", "")
            images_dict = result_data.get("images", {})

            if not markdown_text:
                print("[WARN] 警告: 从返回结果中没有提取到 Markdown 文本")
                return None

            print(f"   [OK] API 解析成功，文本: {len(markdown_text)} 字符，图片: {len(images_dict)} 张")
            return {'markdown': markdown_text, 'text': markdown_text, 'images': images_dict}

        except Exception as e:
            print(f"[ERROR] MinerU API 调用出错: {e}")
            import traceback
            traceback.print_exc()
            return None

    def parse_and_store(
        self,
        file_path: str,
        kb_id: str,
        doc_id: str,
        doc_name: str
    ) -> Dict:
        """
        解析文档并存储到 MinIO

        Args:
            file_path: 文件路径（可以是本地路径或 MinIO 路径）
            kb_id: 知识库 ID
            doc_id: 文档 ID
            doc_name: 文档名称（用于命名 md 文件）

        Returns:
            {
                "success": bool,
                "md_path": str,  # MinIO 中 md 文件的路径
                "images_count": int,
                "error": str (如果失败)
            }
        """
        temp_file = None
        try:
            print(f" 开始解析文档: {doc_name}")

            # 如果是 MinIO 路径，先下载到本地
            actual_file_path = file_path
            if not os.path.exists(file_path):
                print(f"    从 MinIO 下载文件...")
                try:
                    file_data = object_store.get_object(file_path)
                    suffix = os.path.splitext(file_path)[1]
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    temp_file.write(file_data)
                    temp_file.close()
                    actual_file_path = temp_file.name
                    print(f"   [OK] 已下载到: {actual_file_path}")
                except Exception as e:
                    print(f"   [ERROR] MinIO 下载失败: {e}")
                    return {
                        "success": False,
                        "error": f"MinIO 下载失败: {e}"
                    }

            # 1. 调用 MinerU API 解析
            api_result = self._call_mineru_api(actual_file_path, kb_id, doc_id)

            if not api_result:
                return {
                    "success": False,
                    "error": "MinerU API 解析失败"
                }

            markdown_content = api_result.get('markdown', '')
            images_dict = api_result.get('images', {})

            if not markdown_content:
                return {
                    "success": False,
                    "error": "MinerU 未返回 Markdown 内容"
                }

            # 2. 上传图片到 MinIO
            print(f"   [IMG]  开始上传 {len(images_dict)} 张图片到 MinIO...")
            uploaded_count = 0

            for img_filename, img_base64_raw in images_dict.items():
                try:
                    # 清洗 Base64 前缀
                    if "," in img_base64_raw:
                        img_base64_clean = img_base64_raw.split(",", 1)[1]
                    else:
                        img_base64_clean = img_base64_raw

                    # 解码为图片字节
                    img_bytes = base64.b64decode(img_base64_clean)

                    # 确定图片格式
                    img_ext = os.path.splitext(img_filename)[1].lower().strip('.')
                    content_type_map = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "bmp": "image/bmp",
                        "webp": "image/webp"
                    }
                    content_type = content_type_map.get(img_ext, "application/octet-stream")

                    # MinIO 路径: {kb_id}/{doc_id}/images/{filename}
                    object_name = f"{kb_id}/{doc_id}/images/{img_filename}"

                    minio_url = object_store.put_object(
                        object_name=object_name,
                        data=img_bytes,
                        content_type=content_type
                    )

                    if minio_url:
                        # 替换 Markdown 中的图片路径
                        # MinerU 生成的 md 里图片格式是: ![](images/xxx.jpg)
                        old_img_syntax = f"images/{img_filename}"
                        markdown_content = markdown_content.replace(old_img_syntax, minio_url)
                        uploaded_count += 1
                        print(f"      [OK] {img_filename[:30]}... → MinIO")

                except Exception as e:
                    print(f"      [WARN]  上传失败 {img_filename}: {e}")

            print(f"   [OK] 图片上传完成: {uploaded_count}/{len(images_dict)}")

            # 3. 上传 Markdown 到 MinIO
            md_filename = f"{doc_name}.md"
            md_object_name = f"{kb_id}/{doc_id}/{md_filename}"

            md_bytes = markdown_content.encode('utf-8')
            object_store.put_object(
                object_name=md_object_name,
                data=md_bytes,
                content_type="text/markdown"
            )

            md_path = f"source-documents/{md_object_name}"
            print(f"   [OK] Markdown 已保存: {md_path}")

            print(f"[SUCCESS] 文档解析完成！")
            print(f"   MD 文件: {md_path}")
            print(f"   图片数量: {uploaded_count}")

            return {
                "success": True,
                "md_path": md_path,
                "images_count": uploaded_count
            }

        except Exception as e:
            error_msg = f"文档解析出错: {e}"
            print(f"[ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": error_msg
            }
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                    print(f"     已清理临时文件")
                except:
                    pass

    def is_supported_file(self, file_path: str) -> bool:
        """检查文件是否支持 MinerU 解析"""
        supported_extensions = ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.txt', '.md']
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in supported_extensions

    def _extract_headers_from_markdown(self, markdown_content: str) -> List:
        """
        从 Markdown 内容中提取标题信息（智能推断层级）

        支持：
        1. 标准 Markdown 标题层级 (# ## ###)
        2. 从标题编号推断层级 (如 "1 范围", "1.1 概述", "1.1.2 背景")

        Args:
            markdown_content: Markdown 文本内容

        Returns:
            List[HeaderInfo]: 标题信息列表（包含 section_id 和 parent_id）
        """
        import re

        headers = []
        lines = markdown_content.split('\n')

        # 用于追踪每个层级的最新标题（构建父子关系）
        level_stack = {}  # {level: section_id}
        section_counter = {}  # {level: counter}
        global_section_counter = [0]  # 全局计数器，用于没有编号的标题

        def infer_level_from_number(title: str) -> int:
            """
            从标题编号推断层级

            Examples:
                "1 范围" → 1
                "1.1 概述" → 2
                "1.1.2 背景" → 3
                "前言" → 1 (默认)
            """
            # 匹配开头的数字编号 (如 1, 1.1, 1.1.2)
            match = re.match(r'^(\d+(?:\.\d+)*)\s', title)
            if match:
                number_str = match.group(1)
                # 计算点号数量 + 1 = 层级
                dot_count = number_str.count('.')
                return dot_count + 1
            return 1  # 默认一级

        def get_section_id_from_title(title: str) -> str:
            """从标题中提取编号作为 section_id"""
            match = re.match(r'^(\d+(?:\.\d+)*)\s', title)
            if match:
                return match.group(1)
            return None

        for line_number, line in enumerate(lines, start=1):
            # 匹配 Markdown 标题格式 (# ## ### 等)
            stripped = line.strip()
            if not stripped.startswith('#'):
                continue

            # 计算 Markdown 标题级别（# 的数量）
            markdown_level = 0
            for char in stripped:
                if char == '#':
                    markdown_level += 1
                else:
                    break

            # 提取标题文本（去掉 # 和空格）
            title = stripped[markdown_level:].strip()

            if not title or markdown_level > 6:
                continue

            # 智能推断实际层级：优先使用编号，其次使用 Markdown 层级
            inferred_level = infer_level_from_number(title)

            # 如果 Markdown 明确使用了多级标题（##），则用 Markdown 层级
            # 如果所有标题都是 #，则用编号推断层级
            if markdown_level == 1:
                actual_level = inferred_level
            else:
                # 如果 Markdown 有明确的层级标记，信任它
                actual_level = markdown_level

            # 生成或提取 section_id
            section_id = get_section_id_from_title(title)
            if not section_id:
                # 没有编号，使用全局计数器生成唯一的 section_id
                global_section_counter[0] += 1
                section_id = f"section_{global_section_counter[0]}"

            # 获取父级 ID
            parent_id = level_stack.get(actual_level - 1) if actual_level > 1 else None

            # 创建 HeaderInfo
            header_info = HeaderInfo(
                title=title,
                level=actual_level,
                line_number=line_number,
                raw_line=line
            )

            # 动态添加层级属性
            header_info.section_id = section_id
            header_info.parent_id = parent_id

            headers.append(header_info)

            # 更新层级栈
            level_stack[actual_level] = section_id

            # 清除下级栈
            for l in range(actual_level + 1, 7):
                if l in level_stack:
                    del level_stack[l]

        return headers


# 全局实例
mineru_processor = MinerUProcessor()
