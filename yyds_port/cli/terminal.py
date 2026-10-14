"""终端色彩、纯 ANSI 零依赖表格与通知辅助模块。"""

from __future__ import annotations

import os
import sys
from typing import Any, List, Tuple


def supports_color() -> bool:
    """判断当前终端环境是否支持 ANSI 彩色高亮。"""
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


class Colors:
    """ANSI 颜色样式。"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def style(text: str, color: str = "", bold: bool = False, dim: bool = False) -> str:
    """包装文本样式，若终端不支持彩色则原样返回。"""
    if not supports_color():
        return text
    codes = []
    if bold:
        codes.append(Colors.BOLD)
    if dim:
        codes.append(Colors.DIM)
    if color:
        codes.append(color)
    return "".join(codes) + text + Colors.RESET


def render_card(title: str, fields: List[Tuple[str, str]], width: int = 65) -> str:
    """渲染纯 ANSI 优美终端信息卡片。"""
    lines = []
    # 顶部横线
    title_part = f" {title} "
    top_bar = "╭──" + title_part + "─" * max(0, width - 4 - len(title_part)) + "╮"
    lines.append(style(top_bar, Colors.CYAN, bold=True))

    for label, val in fields:
        # 扣除 ANSI 控制符后的纯文本长度计算
        raw_prefix = f"│  {label + ':':<15} "
        remaining_len = max(0, width - len(raw_prefix) - 1)
        val_str = str(val)
        if len(val_str) > remaining_len:
            val_str = val_str[: remaining_len - 3] + "..."
        line = f"│  {style(label + ':', Colors.YELLOW):<24} {style(val_str, Colors.WHITE):<{remaining_len}}│"
        lines.append(line)

    bottom_bar = "╰" + "─" * (width - 2) + "╯"
    lines.append(style(bottom_bar, Colors.CYAN, bold=True))
    return "\n".join(lines)


def render_table(headers: List[str], rows: List[List[Any]]) -> str:
    """纯标准库紧凑美化表格渲染。"""
    if not rows:
        return style("No active ports found.", Colors.DIM)

    # 计算各列最大宽度
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    # 表头
    header_cells = [
        style(h.ljust(col_widths[i]), Colors.CYAN, bold=True)
        for i, h in enumerate(headers)
    ]
    header_line = "  ".join(header_cells)

    # 分割线
    sep_line = style("─" * (sum(col_widths) + 2 * (len(headers) - 1)), Colors.DIM)

    lines = [header_line, sep_line]

    # 数据行
    for row in rows:
        cells = []
        for i, val in enumerate(row):
            s = str(val).ljust(col_widths[i])
            # 第一列端口高亮
            if i == 0:
                s = style(s, Colors.GREEN, bold=True)
            elif i == 1:
                s = style(s, Colors.BLUE)
            elif i == 3:  # PID
                s = style(s, Colors.YELLOW)
            cells.append(s)
        lines.append("  ".join(cells))

    return "\n".join(lines)


def send_system_notification(title: str, message: str) -> bool:
    """
    智能联动系统桌面通知：
    1. 优先尝试调用同家 `yyds-notify-os` (开箱即用)；
    2. 若未安装则安全忽略并返回 False。
    """
    try:
        from yyds_notify_os import notify
        notify(title=title, message=message, app_name="yyds-port")
        return True
    except ImportError:
        pass

    # 尝试系统级原生备选
    if sys.platform.startswith("linux"):
        import shutil
        import subprocess
        if shutil.which("notify-send"):
            try:
                subprocess.run(
                    ["notify-send", title, message, "-a", "yyds-port"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                pass
    return False
