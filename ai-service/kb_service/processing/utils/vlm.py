"""🔍 VLM 视觉模型 - 使用 Qwen2.5-VL-7B-Instruct 进行图像理解和文本提取"""
from typing import Optional
import base64
import requests
import re
import json
from core.config import settings


def _image_to_base64(image_data: bytes) -> str:
    """
    将图片数据转换为base64编码
    
    Args:
        image_data: 图片数据（字节）
        
    Returns:
        base64编码的字符串
    """
    return base64.b64encode(image_data).decode('utf-8')


def _call_vlm(image_data: bytes, prompt: str, max_tokens: int = 2048) -> str:
    """
    调用 vLLM 视觉模型（使用 VLM 专用配置）

    Args:
        image_data: 图片数据（字节）
        prompt: 提示词
        max_tokens: 最大生成token数

    Returns:
        模型生成的文本
    """
    try:
        # 将图片转换为base64
        image_base64 = _image_to_base64(image_data)

        # 构建请求 - 使用 VLM 专用配置
        payload = {
            "model": settings.VLLM_VLM_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1,  # 低温度保证输出稳定
            "stream": False
        }

        # 调用 vLLM VLM API
        response = requests.post(
            settings.VLLM_VLM_BASE_URL + "/v1/chat/completions",
            json=payload,
            timeout=60  # VLM 处理图片需要更长时间
        )
        response.raise_for_status()

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        return content.strip()

    except Exception as e:
        raise Exception(f"调用VLM失败: {str(e)}")


def extract_text_from_image(image_data: bytes) -> str:
    """
    从图片中提取文本（使用 VLM OCR）
    
    Args:
        image_data: 图片数据（字节）
        
    Returns:
        提取的文本
    """
    prompt = """请识别图片中的所有文字内容，按原文输出。
要求：
1. 保持原文的格式和换行
2. 按从上到下、从左到右的顺序输出
3. 只输出识别到的文字，不要添加任何解释或描述
4. 如果图片中没有文字，回复"图片中未检测到文字内容" """
    
    try:
        text = _call_vlm(image_data, prompt)
        return text if text else "图片中未检测到文字内容"
    except Exception as e:
        return f"文字识别失败: {str(e)}"


def analyze_image_content(image_data: bytes, custom_prompt: Optional[str] = None) -> str:
    """
    分析图片内容（通用接口）
    
    Args:
        image_data: 图片数据（字节）
        custom_prompt: 自定义提示词，如果为None则使用默认提示
        
    Returns:
        分析结果
    """
    if custom_prompt is None:
        custom_prompt = "请详细描述这张图片的内容，包括主要对象、场景、文字等信息。"
    
    try:
        return _call_vlm(image_data, custom_prompt)
    except Exception as e:
        return f"图片分析失败: {str(e)}"


def understand_document_image(
    image_data: bytes,
    doc_title: str = "",
    surrounding_text: str = "",
    max_length: int = 100
) -> dict:
    """
    理解文档中的图片（结合文档上下文）

    专门用于处理文档中的图片，理解图片在文档中的含义和作用，
    生成短标题和详细描述。

    Args:
        image_data: 图片数据（字节）
        doc_title: 文档标题，提供背景信息
        surrounding_text: 图片周围的文字上下文（前后150字符）
        max_length: 标题的最大长度，默认100字符

    Returns:
        dict: {
            "short_title": "简洁的标题（适合作为 alt 文本）",
            "detailed_description": "详细的图片解析说明"
        }
    """
    # 构建上下文感知的提示词
    prompt_parts = []

    # 添加文档背景
    if doc_title:
        prompt_parts.append(f"## 文档背景\n文档标题：《{doc_title}》\n")

    # 添加周围上下文
    if surrounding_text:
        prompt_parts.append(f"## 图片上下文\n图片周围的文字内容：\n{surrounding_text}\n")

    # 添加任务指令
    prompt_parts.append("""## 任务
请作为一个专业的数据分析师和文档工程师，分析这张图片在文档中的作用和核心内容。

【重要】你只需要输出一个JSON对象，不要有任何其他文字说明、markdown标记或解释！

JSON格式要求：
{
  "short_title": "简短标题（不超过20字）",
  "detailed_description": "详细描述（100-150字，包含业务关键字，适合RAG检索）"
}

内容要求：
1. short_title：极其简短的图片标题，作为alt文本
2. detailed_description：
   - 描述图表的核心数据、走势、结论或关键文字
   - 包含丰富的业务关键字（如：温度、电阻率、合金材料、曲线等）
   - 长度控制在100-150字
   - 不要有换行符，用一句话概括

示例：
{
  "short_title": "电阻温度系数曲线",
  "detailed_description": "图表展示三种合金材料(I、II、III)的电阻温度系数随温度变化规律。横轴为温度(℃)，纵轴为电阻温度系数Ct。曲线I呈线性上升，曲线II先降后升，曲线III平缓增长，用于选材时参考材料的温度稳定性。"
}

现在请直接输出JSON（不要包含```json或其他标记）：""")

    prompt = "\n".join(prompt_parts)

    try:
        response = _call_vlm(image_data, prompt, max_tokens=1024)

        if not response:
            return {
                "short_title": "文档图片",
                "detailed_description": "💡 **图片解析**：无法提取图片内容"
            }

        print(f"    [DEBUG] VLM raw response: {response[:200]}...")

        # 尝试解析 JSON
        try:
            # 🛡️ 健壮性处理：清洗 VLM 输出，提取 JSON
            # VLM 有时会输出 ```json {...} ```，用正则安全提取
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                print(f"    [DEBUG] JSON parsed successfully")
            else:
                # 如果没匹配到，尝试直接解析
                result = json.loads(response)
                print(f"    [DEBUG] Direct JSON parse successful")

            # 兜底字段验证
            short_title = result.get("short_title", "文档图片").strip()
            detailed_description = result.get("detailed_description", "图片内容暂无详细描述").strip()

            # 移除解析中的物理换行符，防止破坏 <br> 绑定策略
            detailed_description = detailed_description.replace('\n', ' ').replace('\r', ' ')

            # 清理短标题
            short_title = short_title.replace('\n', ' ').replace('\r', ' ')
            short_title = ' '.join(short_title.split())

            # 截断过长的标题
            if len(short_title) > max_length:
                short_title = short_title[:max_length-3] + "..."

            print(f"    [DEBUG] Final result: short_title='{short_title}', desc_len={len(detailed_description)}")

            return {
                "short_title": short_title,
                "detailed_description": detailed_description
            }

        except (json.JSONDecodeError, ValueError) as e:
            # JSON 解析失败，使用文本解析作为后备
            print(f"    [WARN] JSON parse failed: {e}")
            print(f"    [WARN] Response was: {response}")

            # 尝试从旧格式中提取内容
            # 旧格式示例："**图片说明：**这是一张关于..."
            if "**图片说明**：" in response or "**图片说明**：" in response:
                # 提取说明内容
                lines = response.split('\n')
                short_title = "文档图片"
                desc_parts = []

                for line in lines:
                    line = line.strip()
                    if line.startswith("**图片说明**：") or line.startswith("**图片说明**："):
                        # 提取说明后的内容
                        desc = line.split("：", 1)[1] if "：" in line else ""
                        if desc:
                            desc_parts.append(desc)
                    elif line.startswith(("1.", "2.", "3.", "4.")):
                        # 提取列表项内容
                        if "**" in line:
                            parts = line.split("**")
                            for i, part in enumerate(parts):
                                if i % 2 == 1 and "：" in part:  # 奇数索引是加粗内容
                                    content = part.split("：", 1)[1] if "：" in part else part
                                    desc_parts.append(content.strip())

                if desc_parts:
                    detailed_desc = " ".join(desc_parts)[:200]
                else:
                    detailed_desc = response[:200]

                return {
                    "short_title": short_title[:max_length],
                    "detailed_description": detailed_desc.replace('\n', ' ').replace('\r', ' ')
                }

            # 完全fallback：使用原始响应
            short_title = "文档图片"
            detailed_desc = response[:200] if len(response) > 200 else response

            return {
                "short_title": short_title[:max_length],
                "detailed_description": detailed_desc.replace('\n', ' ').replace('\r', ' ')
            }

    except Exception as e:
        return {
            "short_title": "文档图片",
            "detailed_description": f"💡 **图片解析失败**：{str(e)}"
        }
