"""
PPT 主题配色定义

5 种内置主题，每种包含颜色、字体、背景等视觉参数。
用于 ppt_renderer.py 渲染幻灯片时应用统一风格。
"""

from pptx.util import Pt, Inches
from pptx.dml.color import RGBColor


# 幻灯片基础尺寸（EMU）
SLIDE_WIDTH_16_9 = Inches(13.333)
SLIDE_HEIGHT_16_9 = Inches(7.5)

# 页面元素边距
MARGIN_LEFT = Inches(0.8)
MARGIN_RIGHT = Inches(0.8)
MARGIN_TOP = Inches(0.6)
MARGIN_BOTTOM = Inches(0.6)

# 内容区域宽度
CONTENT_WIDTH = SLIDE_WIDTH_16_9 - MARGIN_LEFT - MARGIN_RIGHT


def _theme(
    name: str,
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
    accent: tuple[int, int, int],
    bg_start: tuple[int, int, int],
    bg_end: tuple[int, int, int],
    title_color: tuple[int, int, int],
    body_color: tuple[int, int, int],
    header_bg: tuple[int, int, int],
    header_text_color: tuple[int, int, int],
    title_size: int = 32,
    body_size: int = 18,
    subtitle_size: int = 20,
) -> dict:
    """构建主题字典"""
    return {
        "name": name,
        "primary": RGBColor(*primary),
        "secondary": RGBColor(*secondary),
        "accent": RGBColor(*accent),
        "bg_start": RGBColor(*bg_start),
        "bg_end": RGBColor(*bg_end),
        "title_color": RGBColor(*title_color),
        "body_color": RGBColor(*body_color),
        "header_bg": RGBColor(*header_bg),
        "header_text_color": RGBColor(*header_text_color),
        "title_size": Pt(title_size),
        "body_size": Pt(body_size),
        "subtitle_size": Pt(subtitle_size),
    }


# ========== 5 种内置主题 ==========

THEMES: dict[str, dict] = {
    "business_blue": _theme(
        name="商务蓝",
        primary=(0x1A, 0x56, 0xDB),
        secondary=(0x0D, 0x2F, 0x6B),
        accent=(0x4D, 0xA8, 0xFF),
        bg_start=(0xF0, 0xF4, 0xFF),
        bg_end=(0xFF, 0xFF, 0xFF),
        title_color=(0x0D, 0x2F, 0x6B),
        body_color=(0x33, 0x3D, 0x4D),
        header_bg=(0x1A, 0x56, 0xDB),
        header_text_color=(0xFF, 0xFF, 0xFF),
    ),
    "dark_tech": _theme(
        name="深色科技",
        primary=(0x00, 0xD4, 0xFF),
        secondary=(0x0A, 0x0A, 0x1A),
        accent=(0x7C, 0x3A, 0xED),
        bg_start=(0x0A, 0x0A, 0x1A),
        bg_end=(0x12, 0x12, 0x2A),
        title_color=(0xFF, 0xFF, 0xFF),
        body_color=(0xC0, 0xC8, 0xD8),
        header_bg=(0x14, 0x14, 0x30),
        header_text_color=(0x00, 0xD4, 0xFF),
        title_size=34,
        body_size=18,
        subtitle_size=20,
    ),
    "minimal_white": _theme(
        name="极简白",
        primary=(0x22, 0x22, 0x22),
        secondary=(0x66, 0x66, 0x66),
        accent=(0xE8, 0x3E, 0x3E),
        bg_start=(0xFF, 0xFF, 0xFF),
        bg_end=(0xFA, 0xFA, 0xFA),
        title_color=(0x11, 0x11, 0x11),
        body_color=(0x44, 0x44, 0x44),
        header_bg=(0x22, 0x22, 0x22),
        header_text_color=(0xFF, 0xFF, 0xFF),
        title_size=34,
        body_size=17,
        subtitle_size=22,
    ),
    "academic_green": _theme(
        name="学术绿",
        primary=(0x16, 0x7E, 0x56),
        secondary=(0x0A, 0x4A, 0x32),
        accent=(0x2E, 0xCC, 0x71),
        bg_start=(0xF0, 0xFA, 0xF4),
        bg_end=(0xFF, 0xFF, 0xFF),
        title_color=(0x0A, 0x4A, 0x32),
        body_color=(0x33, 0x3D, 0x4D),
        header_bg=(0x16, 0x7E, 0x56),
        header_text_color=(0xFF, 0xFF, 0xFF),
    ),
    "warm": _theme(
        name="暖色调",
        primary=(0xE8, 0x6B, 0x2C),
        secondary=(0x9C, 0x3D, 0x0E),
        accent=(0xFF, 0xA0, 0x5C),
        bg_start=(0xFF, 0xF8, 0xF0),
        bg_end=(0xFF, 0xFF, 0xFF),
        title_color=(0x6B, 0x2D, 0x0A),
        body_color=(0x44, 0x3D, 0x33),
        header_bg=(0xE8, 0x6B, 0x2C),
        header_text_color=(0xFF, 0xFF, 0xFF),
    ),
}

DEFAULT_THEME = "business_blue"
THEME_NAMES = list(THEMES.keys())
