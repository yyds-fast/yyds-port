"""终端视觉渲染引擎（基于 Rich 打造现代化高质感终端卡片与表格）。"""

from __future__ import annotations

import sys
from typing import Any, List, Tuple

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _RICH_AVAILABLE = True

    console = Console()
except ImportError:
    _RICH_AVAILABLE = False
    console = None  # type: ignore


def print_card(title: str, fields: List[Tuple[str, str]], width: int = 65) -> None:
    """使用 Rich 渲染高颜值圆角信息卡片。"""
    if _RICH_AVAILABLE:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="left", style="bold yellow")
        grid.add_column(justify="left", style="white")

        for label, val in fields:
            val_style = "white"
            if label.lower() in ("port", "status"):
                val_style = "bold green"
            elif label.lower() == "pid":
                val_style = "bold yellow" if val.isdigit() else "bold red"
            elif label.lower() == "user" and val == "root":
                val_style = "bold magenta"
            elif label.lower() == "note":
                val_style = "dim yellow"

            grid.add_row(f"{label}:", f"[{val_style}]{val}[/{val_style}]")

        panel = Panel(
            grid,
            title=f"[bold cyan] {title} [/bold cyan]",
            title_align="left",
            box=box.ROUNDED,
            border_style="cyan",
            expand=False,
            padding=(0, 2),
        )
        console.print(panel)
    else:
        # 降级纯文本输出
        print(f"=== {title} ===")
        for label, val in fields:
            print(f"{label}: {val}")


def print_table(headers: List[str], rows: List[List[Any]]) -> None:
    """使用 Rich 渲染自适应圆角全景端口看板表格。"""
    if not rows:
        if _RICH_AVAILABLE:
            console.print("[dim]No active ports found.[/dim]")
        else:
            print("No active ports found.")
        return

    if _RICH_AVAILABLE:
        table = Table(
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="dim",
            row_styles=["none", "dim"],
            show_header=True,
            show_lines=False,
        )

        for h in headers:
            justify = "right" if h in ("Port", "PID") else ("center" if h == "Proto" else "left")
            style = "bold green" if h == "Port" else ("bold blue" if h == "Proto" else None)
            table.add_column(h, justify=justify, style=style)

        for row in rows:
            formatted_cells = []
            for idx, val in enumerate(row):
                header = headers[idx]
                s = str(val)
                if header == "PID":
                    s = f"[bold yellow]{s}[/bold yellow]" if s.isdigit() else f"[dim]{s}[/dim]"
                elif header == "Process":
                    s = f"[bold white]{s}[/bold white]" if s not in ("-", "<permission denied>") else f"[dim red]{s}[/dim red]"
                elif header == "User":
                    s = f"[magenta]{s}[/magenta]" if s == "root" else f"[white]{s}[/white]"
                elif header == "Address":
                    s = f"[cyan]{s}[/cyan]"
                formatted_cells.append(s)
            table.add_row(*formatted_cells)

        console.print(table)
    else:
        # 降级制表输出
        col_widths = [len(h) for h in headers]
        for row in rows:
            for idx, val in enumerate(row):
                col_widths[idx] = max(col_widths[idx], len(str(val)))
        header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        print(header_line)
        print("-" * len(header_line))
        for row in rows:
            print("  ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)))


def print_success(msg: str) -> None:
    """打印成功状态信息。"""
    if _RICH_AVAILABLE:
        console.print(f"[bold green]✔[/bold green] {msg}")
    else:
        print(f"[✓] {msg}")


def print_error(msg: str) -> None:
    """打印错误状态信息。"""
    if _RICH_AVAILABLE:
        console.print(f"[bold red]✘[/bold red] {msg}")
    else:
        print(f"[✗] {msg}")


def print_info(msg: str) -> None:
    """打印通用提示信息。"""
    if _RICH_AVAILABLE:
        console.print(f"[bold cyan]●[/bold cyan] {msg}")
    else:
        print(f"[*] {msg}")


def print_warning(msg: str) -> None:
    """打印警告信息。"""
    if _RICH_AVAILABLE:
        console.print(f"[bold yellow]▲[/bold yellow] {msg}")
    else:
        print(f"[!] {msg}")


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
