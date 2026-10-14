"""端口状态探测与服务就绪等待器（支持自适应退避、双栈回退与原生 asyncio 异步等待）。"""

from __future__ import annotations

import asyncio
import socket
import time
from typing import Callable, List, Optional

from yyds_port.core.models import PortWaitTimeoutError


def _resolve_candidate_hosts(host: str) -> List[str]:
    """若指定 localhost 则解析双栈候选地址 (优先 127.0.0.1 回退 ::1)。"""
    if host.lower() == "localhost":
        return ["127.0.0.1", "::1"]
    return [host]


def probe_tcp_connection(
    host: str,
    port: int,
    timeout: float = 0.5,
    check_fn: Optional[Callable[[socket.socket], bool]] = None,
) -> bool:
    """尝试与指定 host:port 建立 TCP 握手连接；支持可选的 check_fn 进行应用层探针检测。"""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(family, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        s.connect((host, port))
        if check_fn is not None:
            try:
                return bool(check_fn(s))
            except Exception:
                return False
        return True
    except (OSError, socket.error):
        return False
    finally:
        # 探活完成后通过 SO_LINGER 发送 RST 快速关闭，严防客户端产生大量 TIME_WAIT 耗尽临时端口
        try:
            import struct
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass



def wait_for_open(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 10.0,
    initial_interval: float = 0.05,
    max_interval: float = 0.5,
    backoff: float = 1.3,
    check_fn: Optional[Callable[[socket.socket], bool]] = None,
) -> bool:
    """
    同步阻塞等待指定端口在指定超时时间内变为开放（OPEN / LISTEN）。
    内置指数退避抖动机制，避免持续重试打满目标服务的连接队列。
    """
    deadline = time.time() + max(timeout, 0.01)
    current_interval = initial_interval
    candidates = _resolve_candidate_hosts(host)

    while time.time() < deadline:
        for candidate in candidates:
            # 单次探针连接超时设为当前轮询间隔或 0.3s
            probe_timeout = min(0.3, max(current_interval, 0.05))
            if probe_tcp_connection(candidate, port, timeout=probe_timeout, check_fn=check_fn):
                return True

        time.sleep(current_interval)
        current_interval = min(current_interval * backoff, max_interval)

    raise PortWaitTimeoutError(port, host, timeout, target_state="open")


def wait_for_closed(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 10.0,
    interval: float = 0.1,
) -> bool:
    """同步阻塞等待指定端口在超时时间内关闭监听（CLOSED / FREE）。"""
    deadline = time.time() + max(timeout, 0.01)
    candidates = _resolve_candidate_hosts(host)

    while time.time() < deadline:
        all_closed = True
        for candidate in candidates:
            if probe_tcp_connection(candidate, port, timeout=0.1):
                all_closed = False
                break
        if all_closed:
            return True
        time.sleep(interval)

    raise PortWaitTimeoutError(port, host, timeout, target_state="closed")


async def async_wait_for_open(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 10.0,
    initial_interval: float = 0.05,
    max_interval: float = 0.5,
    backoff: float = 1.3,
) -> bool:
    """
    原生 asyncio 异步等待端口开放（非阻塞协程）。
    适用于 FastAPI、Aiohttp、Tornado 及现代异步 Python 微服务启动流程。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(timeout, 0.01)
    current_interval = initial_interval
    candidates = _resolve_candidate_hosts(host)

    while loop.time() < deadline:
        for candidate in candidates:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(candidate, port),
                    timeout=min(0.3, max(current_interval, 0.05)),
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (OSError, asyncio.TimeoutError):
                pass

        await asyncio.sleep(current_interval)
        current_interval = min(current_interval * backoff, max_interval)

    raise PortWaitTimeoutError(port, host, timeout, target_state="open")


async def async_wait_for_closed(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 10.0,
    interval: float = 0.1,
) -> bool:
    """原生 asyncio 异步等待端口关闭释放。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(timeout, 0.01)
    candidates = _resolve_candidate_hosts(host)

    while loop.time() < deadline:
        all_closed = True
        for candidate in candidates:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(candidate, port),
                    timeout=0.1,
                )
                writer.close()
                await writer.wait_closed()
                all_closed = False
                break
            except (OSError, asyncio.TimeoutError):
                pass

        if all_closed:
            return True

        await asyncio.sleep(interval)

    raise PortWaitTimeoutError(port, host, timeout, target_state="closed")
