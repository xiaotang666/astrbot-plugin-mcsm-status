"""
MCSM 状态面板图片渲染器
将 MCSManager 服务器实例状态渲染为可视化面板图片
支持自定义背景图
"""

import os
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Optional
from datetime import datetime


# ──────────────────────────────────────────────
#  配色方案（暗色主题）
# ──────────────────────────────────────────────

class Theme:
    """暗色主题配色"""
    BG          = (15, 15, 22)       # 画布背景（无自定义背景时使用）
    CARD_BG     = (25, 25, 38)       # 卡片背景
    CARD_BORDER = (42, 42, 60)       # 卡片边框
    HEADER_TOP  = (30, 30, 48)       # 头部渐变顶部
    HEADER_BOT  = (20, 20, 33)       # 头部渐变底部
    TEXT         = (235, 235, 242)    # 主文本
    TEXT_2       = (155, 155, 172)    # 次要文本
    TEXT_3       = (100, 100, 118)    # 暗淡文本
    GREEN        = (72, 200, 115)     # 运行中
    YELLOW       = (250, 195, 55)     # 过渡状态
    RED          = (245, 75, 75)      # 已停止
    BAR_BG       = (38, 38, 52)      # 进度条背景
    CPU_CLR      = (245, 135, 45)    # CPU 进度条颜色
    MEM_CLR      = (70, 170, 250)    # 内存进度条颜色
    DIVIDER      = (45, 45, 62)      # 分隔线
    ACCENT       = (72, 200, 115)    # 顶部强调色条


# 状态码 → 颜色 / 文本
STATUS_COLOR = {
    -1: Theme.TEXT_3,
    0: Theme.RED,
    1: Theme.YELLOW,
    2: Theme.YELLOW,
    3: Theme.GREEN,
}
STATUS_TEXT = {
    -1: "未知",
    0: "已停止",
    1: "停止中",
    2: "启动中",
    3: "运行中",
}


# ──────────────────────────────────────────────
#  工具函数
# ──────────────────────────────────────────────

def _find_cjk_font(size: int) -> ImageFont.FreeTypeFont:
    """按优先级查找支持中文的字体文件"""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    for name in ["NotoSansCJK", "WenQuanYi Zen Hei", "SimHei", "Microsoft YaHei"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _format_bytes(n) -> str:
    """将字节数格式化为人类可读大小"""
    if not n or n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    val = float(n)
    while val >= 1024 and idx < len(units) - 1:
        val /= 1024
        idx += 1
    return f"{val:.1f} {units[idx]}" if idx > 0 else f"{int(val)} B"


def _format_uptime(seconds: int) -> str:
    """将秒数格式化为可读时长"""
    if not seconds or seconds <= 0:
        return "-"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d > 0:
        parts.append(f"{d}天")
    if h > 0:
        parts.append(f"{h}时")
    if m > 0 or not parts:
        parts.append(f"{m}分")
    return " ".join(parts)


def _text_width(draw: ImageDraw.Draw, text: str, font) -> int:
    """测量文本渲染后的像素宽度"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_gradient(draw: ImageDraw.Draw, x1: int, y1: int, x2: int, y2: int,
                   top: tuple, bottom: tuple):
    """绘制垂直线性渐变矩形"""
    for y in range(y1, y2):
        ratio = (y - y1) / max(1, y2 - y1 - 1)
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(x1, y), (x2, y)], fill=(r, g, b))


def _draw_bar(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
              ratio: float, color: tuple, bg_color: tuple = Theme.BAR_BG, radius: int = 3):
    """绘制圆角进度条"""
    ratio = max(0.0, min(1.0, ratio))
    draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=bg_color)
    if ratio > 0.005:
        filled_w = max(radius * 2, int(w * ratio))
        draw.rounded_rectangle((x, y, x + filled_w, y + h), radius=radius, fill=color)


# ──────────────────────────────────────────────
#  主渲染函数
# ──────────────────────────────────────────────

def render_dashboard(
    instances: List[Dict[str, Any]],
    title: str = "MCSManager 服务器状态",
    background: Optional[Image.Image] = None,
) -> Image.Image:
    """
    将实例状态列表渲染为面板图片。

    参数:
        instances: 实例数据列表
        title: 面板标题文字
        background: 自定义背景图 (PIL.Image)，可选
    返回:
        PIL.Image.Image 对象
    """

    CANVAS_W  = 680
    PAD       = 20
    HEADER_H  = 72
    CARD_PAD  = 14
    BAR_INDENT = 8
    CARD_GAP  = 8
    LINE_H    = 22

    CARD_W    = CANVAS_W - PAD * 2
    CONTENT_X = CARD_PAD + BAR_INDENT + 4
    CONTENT_W = CARD_W - CONTENT_X - CARD_PAD

    font_title = _find_cjk_font(20)
    font_name  = _find_cjk_font(16)
    font_text  = _find_cjk_font(13)
    font_small = _find_cjk_font(12)
    font_tiny  = _find_cjk_font(11)

    def _card_height(inst: dict) -> int:
        if inst.get("status") == 3:
            return CARD_PAD + LINE_H * 5 + CARD_PAD
        return CARD_PAD + LINE_H * 2 + CARD_PAD

    card_heights = [_card_height(inst) for inst in instances]
    total_cards_h = sum(card_heights) + CARD_GAP * max(0, len(instances) - 1)
    canvas_h = HEADER_H + PAD + total_cards_h + PAD

    # ── 画布创建（支持自定义背景图） ──
    if background is not None:
        bg_img = background.convert("RGBA").resize(
            (CANVAS_W, canvas_h), Image.LANCZOS
        )
        dark_overlay = Image.new("RGBA", (CANVAS_W, canvas_h), (0, 0, 0, 150))
        composited = Image.alpha_composite(bg_img, dark_overlay)
        canvas = composited.convert("RGB")
    else:
        canvas = Image.new("RGB", (CANVAS_W, canvas_h), Theme.BG)

    draw = ImageDraw.Draw(canvas)

    # ── 头部区域 ──
    _draw_gradient(draw, 0, 0, CANVAS_W, HEADER_H, Theme.HEADER_TOP, Theme.HEADER_BOT)
    draw.rectangle((0, 0, CANVAS_W, 2), fill=Theme.ACCENT)
    draw.text((PAD, 16), title, fill=Theme.TEXT, font=font_title)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draw.text((PAD, 44), timestamp, fill=Theme.TEXT_3, font=font_small)

    running_count = sum(1 for i in instances if i.get("status") == 3)
    count_label = f"{running_count}/{len(instances)} 运行中"
    cw = _text_width(draw, count_label, font_small)
    draw.text((CANVAS_W - PAD - cw, 16), count_label, fill=Theme.GREEN, font=font_small)

    total_players = sum(
        (len(i.get("player_names", [])) or i.get("player_count", 0))
        for i in instances if i.get("status") == 3
    )
    if total_players > 0:
        tp_label = f"总在线: {total_players} 人"
        tw = _text_width(draw, tp_label, font_small)
        draw.text((CANVAS_W - PAD - tw, 38), tp_label, fill=Theme.TEXT_2, font=font_small)

    draw.line([(PAD, HEADER_H - 1), (CANVAS_W - PAD, HEADER_H - 1)],
              fill=Theme.DIVIDER, width=1)

    # ── 实例卡片 ──
    cursor_y = HEADER_H + PAD

    for idx, inst in enumerate(instances):
        card_h = card_heights[idx]
        card_x = PAD

        draw.rounded_rectangle(
            (card_x, cursor_y, card_x + CARD_W, cursor_y + card_h),
            radius=8, fill=Theme.CARD_BG, outline=Theme.CARD_BORDER, width=1
        )

        status = inst.get("status", -1)
        s_color = STATUS_COLOR.get(status, Theme.TEXT_3)
        draw.rectangle(
            (card_x + 1, cursor_y + 6, card_x + 4, cursor_y + card_h - 6),
            fill=s_color
        )

        cx = card_x + CONTENT_X
        cy = cursor_y + CARD_PAD

        # 第 1 行: 名称 + 状态
        name = inst.get("name", "未知")
        port = inst.get("port", "")
        name_display = name + (f"  :{port}" if port else "")
        draw.text((cx, cy), name_display, fill=Theme.TEXT, font=font_name)

        status_label = STATUS_TEXT.get(status, "未知")
        dot_label = f"● {status_label}"
        dw = _text_width(draw, dot_label, font_text)
        draw.text((card_x + CARD_W - CARD_PAD - dw, cy + 2),
                   dot_label, fill=s_color, font=font_text)
        cy += LINE_H

        if status == 3:
            # 第 2 行: 玩家
            pc = inst.get("player_count", 0)
            mp = inst.get("max_players", "?")
            pnames = inst.get("player_names", [])
            player_line = f"玩家 {pc}/{mp}"
            if pnames:
                names_str = ", ".join(pnames[:8])
                if len(pnames) > 8:
                    names_str += f" +{len(pnames) - 8}"
                player_line += f"  {names_str}"
            max_text_w = CONTENT_W - 10
            while _text_width(draw, player_line, font_text) > max_text_w and len(player_line) > 20:
                player_line = player_line[:len(player_line) - 4] + "..."
            draw.text((cx, cy), player_line, fill=Theme.TEXT_2, font=font_text)
            cy += LINE_H

            # 第 3 行: CPU
            cpu = inst.get("cpu", 0) or 0
            draw.text((cx, cy), "CPU", fill=Theme.TEXT_2, font=font_text)
            draw.text((cx + 32, cy), f"{cpu:.1f}%", fill=Theme.CPU_CLR, font=font_text)
            _draw_bar(draw, cx + 80, cy + 4, CONTENT_W - 80, 10, cpu / 100.0, Theme.CPU_CLR)
            cy += LINE_H

            # 第 4 行: 内存
            mem = inst.get("memory", 0) or 0
            max_mem = inst.get("max_memory", 0) or 0
            draw.text((cx, cy), "内存", fill=Theme.TEXT_2, font=font_text)
            mem_str = _format_bytes(mem)
            mem_label = mem_str
            mem_ratio = 0.0
            if max_mem > 0:
                if max_mem < 10000:
                    mem_label = f"{mem_str} / {int(max_mem)} MB"
                    max_bytes = max_mem * 1024 * 1024
                    mem_ratio = mem / max_bytes if max_bytes > 0 else 0
                else:
                    mem_label = f"{mem_str} / {_format_bytes(max_mem)}"
                    mem_ratio = mem / max_mem if max_mem > 0 else 0
            draw.text((cx + 35, cy), mem_label, fill=Theme.MEM_CLR, font=font_text)
            mem_text_end = cx + 35 + _text_width(draw, mem_label, font_text) + 12
            mem_bar_w = max(0, card_x + CARD_W - CARD_PAD - mem_text_end)
            if mem_bar_w >= 30:
                _draw_bar(draw, mem_text_end, cy + 4, mem_bar_w, 10, mem_ratio, Theme.MEM_CLR)
            cy += LINE_H

            # 第 5 行: 运行时长
            uptime = inst.get("uptime", 0) or 0
            draw.text((cx, cy), f"运行 {_format_uptime(uptime)}",
                       fill=Theme.TEXT_3, font=font_text)
            daemon = inst.get("daemon", "")
            if daemon:
                dw = _text_width(draw, daemon, font_tiny)
                draw.text((card_x + CARD_W - CARD_PAD - dw, cy + 1),
                           daemon, fill=Theme.TEXT_3, font=font_tiny)
        else:
            daemon = inst.get("daemon", "")
            if daemon:
                draw.text((cx, cy), f"节点: {daemon}",
                           fill=Theme.TEXT_3, font=font_text)

        cursor_y += card_h + CARD_GAP

    return canvas