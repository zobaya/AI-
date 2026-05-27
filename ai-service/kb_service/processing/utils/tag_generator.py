"""
LLM 标签生成工具 - 使用 Qwen2.5-VL-7B-Instruct 为文档块生成标签/关键词

支持为文档内容生成相关标签，提升检索精确度
注意：Qwen2.5-VL-7B-Instruct 是视觉语言模型，无 think 过程，响应更快
"""
import logging
import httpx
import json
import re
from typing import List, Optional, Dict
from core.config import settings

logger = logging.getLogger(__name__)


class TagGenerator:
    """LLM 标签生成器（使用 Qwen2.5-VL-7B-Instruct VLM）"""

    def __init__(self):
        """初始化标签生成器"""
        self.base_url = settings.VLLM_VLM_BASE_URL
        self.model = settings.VLLM_VLM_MODEL_NAME  # 使用 VLM 配置
        self.timeout = settings.VLLM_TIMEOUT
        logger.info(f"TagGenerator 初始化 - 模型: {self.model}")

    async def generate_tags(
        self,
        content: str,
        title: str = "",
        max_tags: int = 5
    ) -> List[str]:
        """
        为文档内容生成标签（使用 Qwen2.5-VL-7B-Instruct VLM）

        Args:
            content: 文档内容
            title: 文档标题（可选）
            max_tags: 最大标签数量

        Returns:
            标签列表
        """
        if not content or not content.strip():
            return []

        # 构建提示词
        prompt = self._build_prompt(content, title, max_tags)

        try:
            # 调用 Qwen2.5-VL-7B-Instruct VLM
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "你是一个专业的文档标签生成助手。你的任务是为文档内容生成简洁、准确的标签/关键词，用于提升检索精确度。"
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,  # 降低温度以获得更确定性的输出
                        "max_tokens": 2048  # VLM 无 think 过程，不需要大 max_tokens
                    }
                )
                response.raise_for_status()
                data = response.json()

                # 解析响应（VLM 无 think 功能，直接解析）
                content_msg = data["choices"][0]["message"]["content"]
                tags = self._parse_vlm_response(content_msg, max_tags)

                logger.info(f"成功生成 {len(tags)} 个标签: {tags}")
                return tags

        except Exception as e:
            logger.warning(f"LLM 标签生成失败: {e}，返回空标签")
            return []

    def _build_prompt(self, content: str, title: str, max_tags: int) -> str:
        """构建提示词"""
        content_preview = content[:500] if len(content) > 500 else content

        prompt = f"""请为以下文档内容生成 {max_tags} 个标签/关键词。

要求：
1. 标签应该简洁、准确，能概括文档内容的核心主题
2. 优先选择领域相关的专业术语
3. 标签用逗号分隔
4. 只返回标签列表，不要有其他说明

"""

        if title:
            prompt += f"文档标题: {title}\n\n"

        prompt += f"""文档内容:
{content_preview}

请生成 {max_tags} 个标签（用逗号分隔）:"""

        return prompt

    def _parse_vlm_response(self, content: str, max_tags: int) -> List[str]:
        """
        解析 VLM 返回的标签（Qwen2.5-VL-7B-Instruct 无 think 功能）

        VLM 返回格式：标签1, 标签2, 标签3

        Args:
            content: VLM 返回的内容
            max_tags: 最大标签数量

        Returns:
            标签列表
        """
        # 清理内容
        content = content.strip()

        # 尝试多种分隔符
        tags = []

        # 方法1: 按逗号分隔（中文逗号和英文逗号）
        for sep in [',', '，', '\n', '、']:
            if sep in content:
                tags = [tag.strip() for tag in content.split(sep)]
                break

        # 如果没有分隔符，尝试按行分割
        if not tags:
            lines = content.split('\n')
            tags = [line.strip() for line in lines if line.strip()]

        # 过滤无效标签
        valid_tags = []
        for tag in tags:
            # 移除序号前缀（如 "1. 标签" 或 "1、标签"）
            tag = re.sub(r'^[\d]+[\.\、]\s*', '', tag)

            # 移除引号
            tag = tag.strip('"\'""''《》【】()（）')

            # 过滤掉太长的或太短的
            if 1 <= len(tag) <= 20:
                # 过滤掉明显不是标签的内容
                if not any(skip_word in tag for skip_word in [
                    '以下是', '标签', '关键词', '生成', '文档', '内容'
                ]):
                    valid_tags.append(tag)

        # 去重
        seen = set()
        unique_tags = []
        for tag in valid_tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        # 限制数量
        tags = unique_tags[:max_tags]

        logger.debug(f"从内容中解析出标签: {tags}")
        return tags

    async def generate_tags_batch(
        self,
        chunks: List[dict],
        max_tags: int = 5
    ) -> List[dict]:
        """
        批量生成标签（为每个 chunk 生成标签）

        Args:
            chunks: 文档块列表
            max_tags: 每个块的最大标签数量

        Returns:
            更新了 chunk_tags 字段的 chunks 列表
        """
        results = []

        for idx, chunk in enumerate(chunks):
            content = chunk.get("content", "")
            title = chunk.get("metadata", {}).get("title", "")

            if content:
                tags = await self.generate_tags(content, title, max_tags)
                chunk["chunk_tags"] = tags  # 使用 chunk_tags 而不是 tags

                if (idx + 1) % 10 == 0:
                    logger.info(f"已处理 {idx + 1}/{len(chunks)} 个块的标签生成")

            results.append(chunk)

        return results

    def generate_tags_sync(
        self,
        content: str,
        title: str = "",
        max_tags: int = 5
    ) -> List[str]:
        """
        同步版本的标签生成（用于非异步环境）

        Args:
            content: 文档内容
            title: 文档标题（可选）
            max_tags: 最大标签数量

        Returns:
            标签列表
        """
        import asyncio
        try:
            # 获取或创建事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(self.generate_tags(content, title, max_tags))
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self.generate_tags(content, title, max_tags))
        except Exception as e:
            logger.warning(f"同步生成标签失败: {e}，返回空标签")
            return []

    def generate_tags_batch_sync(
        self,
        chunks: List[dict],
        max_tags: int = 5
    ) -> List[dict]:
        """
        同步版本的批量标签生成

        Args:
            chunks: 文档块列表
            max_tags: 每个块的最大标签数量

        Returns:
            更新了 chunk_tags 字段的 chunks 列表
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(self.generate_tags_batch(chunks, max_tags))
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self.generate_tags_batch(chunks, max_tags))
        except Exception as e:
            logger.warning(f"同步批量生成标签失败: {e}，返回原始 chunks")
            return chunks


# 全局标签生成器实例
tag_generator = TagGenerator()
