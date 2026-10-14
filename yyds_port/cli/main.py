"""yyds-port 命令行主入口解析器。"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from yyds_port.__version__ import __version__
from yyds_port.cli.commands import cmd_find, cmd_free, cmd_ls, cmd_wait, cmd_who


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="yyds-port",
        description="yyds-port: 现代化端口管理与诊断工具库 (v" + __version__ + ")",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令 (who, free, wait, find, ls)")

    # who <port>
    p_who = subparsers.add_parser("who", help="诊断谁在占用指定端口")
    p_who.add_argument("port", type=int, help="目标端口号 (1-65535)")
    p_who.add_argument("--proto", choices=["tcp", "udp"], default="tcp", help="协议类型 (默认: tcp)")
    p_who.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # free <port>
    p_free = subparsers.add_parser("free", help="优雅或强制释放占用端口的进程")
    p_free.add_argument("port", type=int, help="目标端口号 (1-65535)")
    p_free.add_argument("-f", "--force", action="store_true", help="直接发送 SIGKILL 强行杀死")
    p_free.add_argument("-y", "--yes", action="store_true", help="跳过确认提示，直接执行")
    p_free.add_argument("--allow-protected", action="store_true", help="允许操作系统受保护端口 (如 22, 53)")

    # wait <target>
    p_wait = subparsers.add_parser("wait", help="阻塞等待目标端口开放就绪")
    p_wait.add_argument("target", help="目标地址与端口 (如 8000 或 127.0.0.1:8000)")
    p_wait.add_argument("-t", "--timeout", type=float, default=20.0, help="最长超时等待秒数 (默认: 20)")
    p_wait.add_argument("--notify", action="store_true", help="就绪时发送系统桌面通知 (联动 yyds-notify-os)")

    # find [port] [end] [--start 1024] [--end 65535]
    p_find = subparsers.add_parser("find", help="寻找空闲可用端口")
    p_find.add_argument(
        "start_pos",
        nargs="?",
        type=int,
        default=None,
        metavar="PORT",
        help="起始端口号 (可选位置参数，例如: yyds-port find 8000)",
    )
    p_find.add_argument(
        "end_pos",
        nargs="?",
        type=int,
        default=None,
        metavar="END",
        help="结束端口号 (可选位置参数，例如: yyds-port find 8000 9000)",
    )
    p_find.add_argument("--start", type=int, default=1024, help="起始端口 (默认: 1024)")
    p_find.add_argument("--end", type=int, default=65535, help="结束端口 (默认: 65535)")
    p_find.add_argument("-c", "--count", type=int, default=1, help="连续可用端口数量 (默认: 1)")
    p_find.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # ls
    p_ls = subparsers.add_parser("ls", help="全景列出所有正在监听的端口及占用进程看板")
    p_ls.add_argument("--proto", choices=["all", "tcp", "udp"], default="all", help="协议过滤 (默认: all)")
    p_ls.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口函数。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "who":
        return cmd_who(args.port, proto_str=args.proto, as_json=args.json)
    elif args.command == "free":
        return cmd_free(
            args.port,
            force=args.force,
            yes=args.yes,
            allow_protected=args.allow_protected,
        )
    elif args.command == "wait":
        return cmd_wait(args.target, timeout=args.timeout, notify=args.notify)
    elif args.command == "find":
        start_val = args.start_pos if args.start_pos is not None else args.start
        end_val = args.end_pos if args.end_pos is not None else args.end
        return cmd_find(start=start_val, end=end_val, count=args.count, as_json=args.json)
    elif args.command == "ls":
        return cmd_ls(proto_str=args.proto, as_json=args.json)


    return 0


if __name__ == "__main__":
    sys.exit(main())
