"""macOS (Darwin) 原生端口探测引擎。

使用 lsof -F (机器快速格式) 解析占用进程与监听地址，相比无格式 lsof 提速数倍。
"""

from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional, Tuple

from yyds_port.core.models import ProcessInfo, Protocol
from yyds_port.core.platform.base import BaseScanner


class DarwinScanner(BaseScanner):
    """macOS 优化端口探测引擎。"""

    def __init__(self) -> None:
        self.lsof_bin = shutil.which("lsof")

    def _run_lsof_fast(self, port: Optional[int] = None) -> List[Tuple[int, ProcessInfo]]:
        """执行 lsof -F pcn 解析监听端口与进程。"""
        if not self.lsof_bin:
            return []

        cmd = [self.lsof_bin, "-nP", "-sTCP:LISTEN"]
        if port is not None:
            cmd.append(f"-iTCP:{port}")
        else:
            cmd.append("-iTCP")
        cmd.append("-Fpcn")

        results: List[Tuple[int, ProcessInfo]] = []
        try:
            output = subprocess.check_output(cmd, text=True, errors="replace", stderr=subprocess.DEVNULL)
            current_pid: Optional[int] = None
            current_cmd: str = ""

            for line in output.splitlines():
                if not line:
                    continue
                tag, val = line[0], line[1:]
                if tag == "p":
                    try:
                        current_pid = int(val)
                    except ValueError:
                        current_pid = None
                elif tag == "c":
                    current_cmd = val
                elif tag == "n":
                    # n127.0.0.1:8000 or n*:8000
                    if ":" in val:
                        addr_str = val
                        port_str = val.rsplit(":", 1)[1]
                        try:
                            port_num = int(port_str)
                        except ValueError:
                            continue

                        info = ProcessInfo(
                            pid=current_pid,
                            name=current_cmd,
                            cmdline=[current_cmd] if current_cmd else [],
                            listen_address=addr_str,
                            proto=Protocol.TCP,
                            permission_denied=False,
                        )
                        results.append((port_num, info))
        except (subprocess.CalledProcessError, OSError):
            pass

        return results

    def find_occupant(self, port: int, proto: Protocol = Protocol.TCP) -> Optional[ProcessInfo]:
        """查找指定端口在 macOS 下的占用进程。"""
        if proto != Protocol.TCP:
            # UDP 尝试 lsof -nP -iUDP:<port>
            if not self.lsof_bin:
                return None
            try:
                cmd = [self.lsof_bin, "-nP", f"-iUDP:{port}", "-Fpcn"]
                out = subprocess.check_output(cmd, text=True, errors="replace", stderr=subprocess.DEVNULL)
                pid = None
                name = ""
                addr = f"0.0.0.0:{port}"
                for line in out.splitlines():
                    if line.startswith("p"):
                        pid = int(line[1:])
                    elif line.startswith("c"):
                        name = line[1:]
                    elif line.startswith("n"):
                        addr = line[1:]
                if pid:
                    return ProcessInfo(pid=pid, name=name, cmdline=[name], listen_address=addr, proto=Protocol.UDP)
            except Exception:
                pass
            return None

        items = self._run_lsof_fast(port=port)
        if items:
            return items[0][1]
        return None

    def list_all_occupants(
        self, proto: Optional[Protocol] = None
    ) -> List[Tuple[int, ProcessInfo]]:
        """全量列出 macOS 当前正在监听的端口。"""
        items = self._run_lsof_fast(port=None)
        items.sort(key=lambda x: x[0])
        return items
