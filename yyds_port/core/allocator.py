"""端口智能分配、连续区间查找与独占预留上下文管理器。"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from yyds_port.core.models import PortOccupiedError, Protocol


def _is_port_available(port: int, host: str = "127.0.0.1", proto: Protocol = Protocol.TCP) -> bool:
    """内部探测端口是否可成功绑定并处于完全可用状态。"""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock_type = socket.SOCK_STREAM if proto == Protocol.TCP else socket.SOCK_DGRAM

    try:
        with socket.socket(family, sock_type) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            if proto == Protocol.TCP:
                s.listen(1)
            return True
    except (OSError, socket.error):
        return False


def find_free_port(
    start: int = 1024,
    end: int = 65535,
    host: str = "127.0.0.1",
    proto: Protocol = Protocol.TCP,
) -> int:
    """
    寻找一个空闲可用端口。
    若 start=0，直接让操作系统内核分配随机空闲端口。
    """
    if start == 0:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock_type = socket.SOCK_STREAM if proto == Protocol.TCP else socket.SOCK_DGRAM
        with socket.socket(family, sock_type) as s:
            s.bind((host, 0))
            return s.getsockname()[1]

    if start > end:
        raise ValueError(f"start port ({start}) cannot be greater than end port ({end})")

    for port in range(start, end + 1):
        if _is_port_available(port, host=host, proto=proto):
            return port

    raise PortOccupiedError(start, message=f"No free {proto.value} port available in range {start}-{end}")


def find_free_range(
    count: int,
    start: int = 1024,
    end: int = 65535,
    host: str = "127.0.0.1",
    proto: Protocol = Protocol.TCP,
) -> List[int]:
    """
    查找连续 count 个可用端口（适用于分布式集群、微服务多端口矩阵等场景）。
    """
    if count <= 0:
        return []
    if start + count - 1 > end:
        raise ValueError(f"Port range too small for {count} contiguous ports")

    current_streak: List[int] = []
    for port in range(start, end + 1):
        if _is_port_available(port, host=host, proto=proto):
            current_streak.append(port)
            if len(current_streak) == count:
                return current_streak
        else:
            current_streak.clear()

    raise PortOccupiedError(
        start,
        message=f"Could not find {count} contiguous free ports in range {start}-{end}",
    )


def _get_lock_dir() -> Path:
    """
    获取协同排他锁根目录。
    1. 优先使用 XDG_RUNTIME_DIR (基于 tmpfs 纯内存文件系统，原生用户隔离，零磁盘 I/O 磨损)；
    2. 回退到包含当前用户 UID 的临时目录，100% 杜绝多租户/CI 多用户并发时的 PermissionError 权限污染。
    """
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg and os.path.isdir(xdg) and os.access(xdg, os.W_OK):
        lock_dir = Path(xdg) / "yyds_port_locks"
    else:
        uid = os.getuid() if hasattr(os, "getuid") else "shared"
        lock_dir = Path(tempfile.gettempdir()) / f"yyds_port_locks_{uid}"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir


class CollaborativeFileLock:
    """跨进程协作文件锁（基于系统内存临时目录与 fcntl/msvcrt 互斥锁定）。"""

    def __init__(self, port: int):
        self.port = port
        self.lock_dir = _get_lock_dir()
        self.lock_file = self.lock_dir / f"port_{port}.lock"
        self._fd: Optional[int] = None

    def acquire(self, blocking: bool = True) -> bool:
        """尝试获取锁。"""
        try:
            self._fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o644)
            if sys.platform in ("win32", "cygwin"):
                import msvcrt
                mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
                msvcrt.locking(self._fd, mode, 1)
            else:
                import fcntl
                flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(self._fd, flags)
            return True
        except (OSError, IOError):
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            return False

    def release(self) -> None:
        """释放锁并清理文件描述符。"""
        if self._fd is not None:
            try:
                if sys.platform in ("win32", "cygwin"):
                    import msvcrt
                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(self._fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


@contextlib.contextmanager
def reserve_port(
    start: int = 1024,
    end: int = 65535,
    host: str = "127.0.0.1",
    proto: Protocol = Protocol.TCP,
    collaborative: bool = True,
    pass_fd: bool = False,
) -> Generator[int | Tuple[int, socket.socket], None, None]:
    """
    独占预留端口上下文管理器。
    - collaborative=True (默认): 在本地临时目录持有进程级排他文件锁，确保多进程测试（如 pytest -n auto）不争抢。
    - pass_fd=True: 保持套接字处于 open 状态，yield (port, socket)，适用于支持从已绑定 socket 继承的子进程服务。
    """
    if pass_fd:
        # FD 模式：直接创建、绑定并保持 socket
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock_type = socket.SOCK_STREAM if proto == Protocol.TCP else socket.SOCK_DGRAM
        s = socket.socket(family, sock_type)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 找到可用端口
            allocated_port = -1
            for p in range(start, end + 1):
                try:
                    s.bind((host, p))
                    allocated_port = p
                    break
                except OSError:
                    continue

            if allocated_port == -1:
                raise PortOccupiedError(start, message=f"No free port in range {start}-{end}")

            if proto == Protocol.TCP:
                s.listen(1)

            yield allocated_port, s
        finally:
            s.close()
        return

    # 协作文件锁模式
    lock: Optional[CollaborativeFileLock] = None
    selected_port = -1

    for p in range(start, end + 1):
        if not _is_port_available(p, host=host, proto=proto):
            continue

        if collaborative:
            candidate_lock = CollaborativeFileLock(p)
            if candidate_lock.acquire(blocking=False):
                lock = candidate_lock
                selected_port = p
                break
        else:
            selected_port = p
            break

    if selected_port == -1:
        raise PortOccupiedError(start, message=f"No free port could be reserved in range {start}-{end}")

    try:
        yield selected_port
    finally:
        if lock is not None:
            lock.release()
