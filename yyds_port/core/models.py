"""yyds-port 核心强类型数据结构与异常定义。"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Protocol(str, Enum):
    """网络传输层协议枚举。"""

    TCP = "tcp"
    UDP = "udp"

    @classmethod
    def from_str(cls, val: str | Protocol) -> Protocol:
        """从字符串或枚举对象规范化协议。"""
        if isinstance(val, cls):
            return val
        s = str(val).strip().lower()
        if s == "udp":
            return cls.UDP
        return cls.TCP

    def __str__(self) -> str:
        return self.value


class PortError(Exception):
    """yyds-port 基础异常类。"""


class PortOccupiedError(PortError):
    """端口已被占用异常。"""

    def __init__(self, port: int, occupant: Optional[ProcessInfo] = None, message: str = ""):
        self.port = port
        self.occupant = occupant
        msg = message or f"Port {port} is already occupied"
        if occupant and occupant.pid:
            msg += f" by PID {occupant.pid} ({occupant.name})"
        super().__init__(msg)


class PortWaitTimeoutError(PortError):
    """等待端口就绪或关闭超时异常。"""

    def __init__(self, port: int, host: str, timeout: float, target_state: str = "open"):
        self.port = port
        self.host = host
        self.timeout = timeout
        self.target_state = target_state
        super().__init__(
            f"Timed out after {timeout:.1f}s waiting for {host}:{port} to become {target_state}"
        )


class ProtectedPortError(PortError):
    """尝试操作受系统保护的安全端口异常。"""

    def __init__(self, port: int, message: str = ""):
        self.port = port
        super().__init__(
            message or f"Port {port} is in safety protected whitelist. Operation aborted."
        )


@dataclass
class ProcessInfo:
    """监听端口的进程详情。"""

    pid: Optional[int]
    name: str = ""
    cmdline: List[str] = field(default_factory=list)
    listen_address: str = ""
    proto: Protocol = Protocol.TCP
    user: Optional[str] = None
    cwd: Optional[str] = None
    inode: Optional[int] = None
    permission_denied: bool = False

    @property
    def cmdline_str(self) -> str:
        """完整命令行字符串。"""
        if not self.cmdline:
            return self.name or ""
        return " ".join(shlex.quote(arg) for arg in self.cmdline)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于 JSON 输出）。"""
        return {
            "pid": self.pid,
            "name": self.name,
            "cmdline": self.cmdline,
            "cmdline_str": self.cmdline_str,
            "listen_address": self.listen_address,
            "proto": self.proto.value,
            "user": self.user,
            "cwd": self.cwd,
            "inode": self.inode,
            "permission_denied": self.permission_denied,
        }
