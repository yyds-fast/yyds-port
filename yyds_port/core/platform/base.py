"""跨平台端口探测器抽象基类与工厂。"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from yyds_port.core.models import ProcessInfo, Protocol


class BaseScanner(ABC):
    """端口探测器基类接口。"""

    @abstractmethod
    def find_occupant(self, port: int, proto: Protocol = Protocol.TCP) -> Optional[ProcessInfo]:
        """查找指定端口和协议的占用进程详情。若未被占用返回 None。"""
        raise NotImplementedError

    @abstractmethod
    def list_all_occupants(
        self, proto: Optional[Protocol] = None
    ) -> List[Tuple[int, ProcessInfo]]:
        """列出当前机器上所有正在监听的端口及占用进程。返回按端口排序的列表。"""
        raise NotImplementedError


_scanner_instance: Optional[BaseScanner] = None


def get_default_scanner() -> BaseScanner:
    """获取当前操作系统对应的默认端口探测器单例。"""
    global _scanner_instance
    if _scanner_instance is not None:
        return _scanner_instance

    platform_name = sys.platform
    if platform_name.startswith("linux"):
        from yyds_port.core.platform.linux import LinuxScanner
        _scanner_instance = LinuxScanner()
    elif platform_name == "darwin":
        from yyds_port.core.platform.darwin import DarwinScanner
        _scanner_instance = DarwinScanner()
    elif platform_name in ("win32", "cygwin"):
        from yyds_port.core.platform.windows import WindowsScanner
        _scanner_instance = WindowsScanner()
    else:
        # 降级到通用 POSIX 扫描器
        from yyds_port.core.platform.darwin import DarwinScanner
        _scanner_instance = DarwinScanner()

    return _scanner_instance
