"""yyds-port CLI 子命令执行分发逻辑。"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from yyds_port.cli.terminal import (
    Colors,
    render_card,
    render_table,
    send_system_notification,
    style,
)
from yyds_port.core.models import Protocol
from yyds_port.core.port import Port


def cmd_who(port_num: int, proto_str: str = "tcp", as_json: bool = False) -> int:
    """who 子命令：查询谁在监听目标端口。"""
    proto = Protocol.from_str(proto_str)
    p = Port(port_num, proto=proto)
    occ = p.occupant()

    if as_json:
        payload: dict[str, Any] = {
            "port": port_num,
            "proto": proto.value,
            "occupied": occ is not None,
            "occupant": occ.to_dict() if occ else None,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if occ else 1

    if occ is None:
        print(style(f"Port {port_num} ({proto.value.upper()}) is FREE (no occupant).", Colors.GREEN))
        return 1

    if occ.permission_denied:
        fields = [
            ("Port", f"{port_num} ({proto.value.upper()})"),
            ("Status", f"LISTEN ({occ.listen_address})"),
            ("User", occ.user or "root/system"),
            ("PID", "<Permission Denied>"),
            ("Note", "Run with sudo/administrator privileges to inspect PID details"),
        ]
    else:
        fields = [
            ("Port", f"{port_num} ({proto.value.upper()})"),
            ("PID", str(occ.pid)),
            ("Process", occ.name or "<unknown>"),
            ("User", occ.user or "<unknown>"),
            ("Command", occ.cmdline_str or occ.name),
            ("Status", f"LISTEN ({occ.listen_address})"),
            ("CWD", occ.cwd or "<unknown>"),
        ]

    title = f"Port {port_num} Occupant"
    print(render_card(title, fields))
    return 0


def cmd_free(
    port_num: int,
    force: bool = False,
    yes: bool = False,
    allow_protected: bool = False,
) -> int:
    """free 子命令：优雅或强制释放占用端口的进程。"""
    p = Port(port_num)
    occ = p.occupant()

    if occ is None or (occ.pid is None and not occ.permission_denied):
        print(style(f"[✓] Port {port_num} is already free!", Colors.GREEN))
        return 0

    if occ.permission_denied:
        print(style(f"[✗] Port {port_num} is occupied by another user/system. Please run with sudo.", Colors.RED))
        return 2

    # 交互确认
    if not yes:
        proc_desc = f"{occ.name} (PID {occ.pid})"
        prompt = style(f"[?] Process {proc_desc} is listening on port {port_num}. Kill it? [y/N]: ", Colors.YELLOW, bold=True)
        try:
            choice = input(prompt).strip().lower()
            if choice not in ("y", "yes"):
                print(style("[-] Operation cancelled by user.", Colors.DIM))
                return 0
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Operation cancelled.")
            return 1

    print(f"[*] Terminating PID {occ.pid} ({occ.name})...")
    success = p.free(timeout=2.5, force=force, kill_tree=True, allow_protected=allow_protected)

    if success:
        print(style(f"[✓] Successfully freed port {port_num}!", Colors.GREEN, bold=True))
        return 0
    else:
        print(style(f"[✗] Failed to free port {port_num}. Process may still be holding the port.", Colors.RED))
        return 1


def cmd_wait(
    target: str,
    timeout: float = 20.0,
    notify: bool = False,
) -> int:
    """wait 子命令：等待指定端口连通就绪。"""
    host = "127.0.0.1"
    port_str = target

    if ":" in target:
        host, port_str = target.rsplit(":", 1)

    try:
        port_num = int(port_str)
    except ValueError:
        print(style(f"[✗] Invalid port number: {port_str}", Colors.RED))
        return 2

    print(f"[*] Waiting for {host}:{port_num} to become reachable (timeout={timeout:.1f}s)...")
    start_time = time.time()

    try:
        Port(port_num).wait_open(host=host, timeout=timeout)
        elapsed = time.time() - start_time
        print(style(f"[✓] Port {port_num} is OPEN! (connected in {elapsed:.2f}s)", Colors.GREEN, bold=True))

        if notify:
            msg = f"Port {port_num} on {host} is now reachable (in {elapsed:.2f}s)"
            if send_system_notification("Port Ready!", msg):
                print(style("[🔔] Desktop notification dispatched.", Colors.CYAN))
        return 0
    except Exception as e:
        print(style(f"[✗] {e}", Colors.RED))
        return 1


def cmd_find(
    start: int = 1024,
    end: int = 65535,
    count: int = 1,
    as_json: bool = False,
) -> int:
    """find 子命令：查找一个或连续多个空闲端口。"""
    try:
        if count == 1:
            free_p = Port.find_free(start=start, end=end)
            if as_json:
                print(json.dumps({"port": int(free_p)}))
            else:
                print(int(free_p))
        else:
            ports = Port.find_free_range(count=count, start=start, end=end)
            if as_json:
                print(json.dumps({"ports": [int(p) for p in ports]}))
            else:
                print(" ".join(str(int(p)) for p in ports))
        return 0
    except Exception as e:
        print(style(f"[✗] {e}", Colors.RED), file=sys.stderr)
        return 1


def cmd_ls(proto_str: str = "all", as_json: bool = False) -> int:
    """ls 子命令：列出全部正在监听的端口及占用进程看板。"""
    proto_filter = None
    if proto_str.lower() in ("tcp", "udp"):
        proto_filter = Protocol.from_str(proto_str)

    items = Port.ls(proto=proto_filter)

    if as_json:
        data = [
            {
                "port": int(p),
                "proto": info.proto.value,
                "address": info.listen_address,
                "pid": info.pid,
                "process": info.name,
                "user": info.user,
                "permission_denied": info.permission_denied,
            }
            for p, info in items
        ]
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    headers = ["Port", "Proto", "Address", "PID", "Process", "User"]
    rows = []
    for p, info in items:
        pid_display = str(info.pid) if info.pid is not None else "-"
        proc_display = info.name if info.name else "-"
        if info.permission_denied and not info.pid:
            proc_display = "<permission denied>"
        user_display = info.user or "-"

        rows.append([
            int(p),
            info.proto.value.upper(),
            info.listen_address,
            pid_display,
            proc_display,
            user_display,
        ])

    print(render_table(headers, rows))
    return 0
