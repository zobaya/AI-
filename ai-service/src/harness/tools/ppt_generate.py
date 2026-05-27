"""
PPT 生成工具

根据用户需求生成 PPT 演示文稿，上传至 MinIO，
回调 Django 创建 GeneratedFile 记录，返回下载信息。
"""

import json
import logging
from uuid import uuid4

import httpx

from .base import BaseTool
from .ppt_renderer import build_slide_plan, render_presentation
from .ppt_themes import THEMES, DEFAULT_THEME, THEME_NAMES
from core.config import settings

logger = logging.getLogger(__name__)


class PPTGenerateTool(BaseTool):
    """PPT 演示文稿生成工具"""

    name = "ppt_generate"
    description = "根据用户需求生成 PPT 演示文稿"
    group = "generate"

    def get_schema(self) -> dict:
        """返回 OpenAI Function Calling 格式的 JSON Schema"""
        theme_names = ", ".join(THEME_NAMES)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "根据用户需求生成 PPT 演示文稿。"
                    "支持多种主题风格，包含标题页、目录、内容页、结尾页等布局。"
                    "返回生成的 PPT 文件下载信息。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "演示文稿的主题或标题",
                        },
                        "slides": {
                            "type": "array",
                            "description": (
                                "每页幻灯片的详细内容，由你根据用户需求规划。"
                                "每项包含 title（标题）和 bullets（要点列表，3-5 条）。"
                                "工具会自动添加标题页、目录页和结尾页，"
                                "你只需提供中间的内容页。"
                                "请确保内容具体、有实质信息，不要写空泛的占位文字。"
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "该页幻灯片的标题",
                                    },
                                    "bullets": {
                                        "type": "array",
                                        "description": "该页的要点列表（3-5条），每条应有实质内容",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["title", "bullets"],
                            },
                        },
                        "slide_count": {
                            "type": "integer",
                            "description": "内容页数量（不含自动添加的标题页/目录/结尾），默认 5 页（范围 3-15）",
                            "default": 5,
                        },
                        "theme": {
                            "type": "string",
                            "description": f"主题风格，可选值：{theme_names}，默认 {DEFAULT_THEME}",
                            "default": DEFAULT_THEME,
                            "enum": THEME_NAMES,
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(self, **kwargs) -> str:
        """
        执行 PPT 生成流程：
        1. 使用 LLM 传入的 slides 或自动生成结构计划
        2. 渲染为 .pptx 文件
        3. 上传至 MinIO
        4. 回调 Django 创建 GeneratedFile 记录
        5. 返回包含 file_id 的下载标记
        """
        topic = kwargs.get("topic", "演示文稿")
        slides_input = kwargs.get("slides", [])
        slide_count = kwargs.get("slide_count", 5)
        theme_name = kwargs.get("theme", DEFAULT_THEME)
        config = kwargs.get("config")

        # 参数校验
        if theme_name not in THEMES:
            theme_name = DEFAULT_THEME

        try:
            # 1. 生成结构计划
            plan = build_slide_plan(
                topic=topic,
                slide_count=slide_count,
                slides=slides_input,
            )

            # 2. 渲染 PPT
            ppt_bytes = render_presentation(plan, theme_name)

            # 3. 上传至 MinIO
            file_id_uuid = uuid4().hex
            file_name = f"{topic}.pptx"
            object_path = f"{file_id_uuid}.pptx"

            from core.object_store import object_store
            from core.config import settings

            minio_path = object_store.put_object(
                object_name=object_path,
                data=ppt_bytes,
                content_type=(
                    "application/vnd.openxmlformats-officedocument"
                    ".presentationml.presentation"
                ),
                bucket=settings.MINIO_GENERATED_BUCKET,
            )

            # 4. 回调 Django 创建 GeneratedFile 记录
            file_record_id = await self._create_file_record(
                file_name=file_name,
                minio_path=minio_path,
                file_size=len(ppt_bytes),
                slide_count=plan["slide_count"],
                theme=theme_name,
                config=config,
            )

            # 5. 返回结果
            theme_display = THEMES[theme_name]["name"]
            file_size = len(ppt_bytes)

            file_info = json.dumps(
                {
                    "file_id": file_record_id,
                    "file_name": file_name,
                    "file_size": file_size,
                    "slide_count": plan["slide_count"],
                    "theme": theme_display,
                },
                ensure_ascii=False,
            )

            return (
                f"PPT 演示文稿已成功生成！\n\n"
                f"**文件信息：**\n"
                f"- 文件名：{file_name}\n"
                f"- 页数：{plan['slide_count']} 页\n"
                f"- 主题：{theme_display}\n"
                f"- 大小：{file_size / 1024:.1f} KB\n\n"
                f"用户可以通过下方下载卡片获取文件。\n\n"
                f"<!--PPT_FILE:{file_info}-->"
            )

        except Exception as e:
            logger.error(f"[PPTGenerateTool] 生成失败: {e}")
            return f"PPT 生成失败：{e}"

    async def _create_file_record(
        self,
        file_name: str,
        minio_path: str,
        file_size: int,
        slide_count: int,
        theme: str,
        config: dict | None,
    ) -> int | None:
        """回调 Django 创建 GeneratedFile 记录，返回记录 ID"""
        base_url = getattr(settings, "DJANGO_API_BASE_URL", "http://localhost:8000")
        service_token = getattr(settings, "SERVICE_AUTH_TOKEN", None)

        if not service_token:
            logger.warning("[PPTGenerateTool] SERVICE_AUTH_TOKEN 未配置，跳过文件记录")
            return None

        # 从 config 中提取 user_id 和 conversation_id
        user_id = None
        conversation_id = None
        if config:
            configurable = config.get("configurable", {})
            user_id = configurable.get("user_id")
            conversation_id = configurable.get("conversation_id")

        if not user_id:
            logger.warning("[PPTGenerateTool] 无法获取 user_id，跳过文件记录")
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{base_url}/api/chat/files/create/",
                    json={
                        "user_id": user_id,
                        "file_name": file_name,
                        "minio_path": minio_path,
                        "file_size": file_size,
                        "file_type": "pptx",
                        "slide_count": slide_count,
                        "theme": theme,
                        "conversation_id": conversation_id,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Service {service_token}",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                record_id = data.get("id")
                logger.info(f"[PPTGenerateTool] 文件记录已创建: id={record_id}")
                return record_id
        except Exception as e:
            logger.error(f"[PPTGenerateTool] 创建文件记录失败: {e}")
            return None
