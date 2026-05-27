"""
VLM (Vision Language Model) 图片描述生成工具

使用 Qwen2.5-VL-7B-Instruct 模型生成图片内容描述
"""
import requests
import logging
from typing import Optional
from core.config import settings

logger = logging.getLogger(__name__)


# 默认提示词
DEFAULT_CAPTION_PROMPT = "请详细描述这张图片的内容，包括物体、场景、文字、颜色等关键信息。"


async def generate_image_caption(
    image_url: str,
    prompt: str = DEFAULT_CAPTION_PROMPT,
    max_tokens: int = 300
) -> Optional[str]:
    """
    使用 VLM 生成图片描述

    Args:
        image_url: 图片的 MinIO URL（需要 VLM 服务能访问）
        prompt: 图片描述提示词
        max_tokens: 最大生成 token 数

    Returns:
        图片描述文本，如果生成失败则返回 None

    降级策略:
        - VLM 服务不可用 → 返回 None
        - 超时 → 返回 None
        - 返回空内容 → 返回 None
        - 其他错误 → 返回 None
    """
    try:
        # 构建 VLM API 请求（OpenAI 兼容格式）
        vlm_api_url = f"{settings.VLLM_VLM_BASE_URL}/v1/chat/completions"

        payload = {
            "model": settings.VLLM_VLM_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }

        headers = {
            "Content-Type": "application/json; charset=UTF-8"
        }

        logger.info(f"[VLM] Calling VLM service: {vlm_api_url}")
        logger.info(f"[VLM] Image URL: {image_url}")

        # 调用 VLM API（设置超时）
        response = requests.post(
            vlm_api_url,
            json=payload,
            headers=headers,
            timeout=30  # 30 秒超时
        )

        response.raise_for_status()
        data = response.json()

        # 解析响应（OpenAI 格式）
        if "choices" in data and len(data["choices"]) > 0:
            caption = data["choices"][0]["message"]["content"].strip()

            if caption:
                logger.info(f"[VLM] Caption generated successfully: {caption[:100]}...")
                return caption
            else:
                logger.warning("[VLM] VLM returned empty caption")
                return None
        else:
            logger.warning(f"[VLM] Unexpected VLM response format: {data.keys()}")
            return None

    except requests.exceptions.Timeout:
        logger.warning(f"[VLM] Request timeout after 30 seconds")
        return None

    except requests.exceptions.ConnectionError as e:
        logger.warning(f"[VLM] Connection error: {str(e)}")
        return None

    except requests.exceptions.HTTPError as e:
        logger.warning(f"[VLM] HTTP error: {e.response.status_code} - {str(e)}")
        return None

    except Exception as e:
        logger.warning(f"[VLM] Unexpected error: {str(e)}")
        return None


def generate_image_caption_sync(
    image_url: str,
    prompt: str = DEFAULT_CAPTION_PROMPT,
    max_tokens: int = 300
) -> Optional[str]:
    """
    同步版本的图片描述生成（用于在非异步上下文中调用）

    Args:
        image_url: 图片的 MinIO URL
        prompt: 图片描述提示词
        max_tokens: 最大生成 token 数

    Returns:
        图片描述文本，如果生成失败则返回 None
    """
    try:
        import asyncio
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 如果循环已运行，直接运行协程
        if loop.is_running():
            # 在已运行的循环中创建任务
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    generate_image_caption(image_url, prompt, max_tokens)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                generate_image_caption(image_url, prompt, max_tokens)
            )

    except Exception as e:
        logger.error(f"[VLM] Sync caption generation failed: {str(e)}")
        return None
