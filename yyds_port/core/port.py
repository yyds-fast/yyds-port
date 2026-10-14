"""Port 核心实体对象类与对外统一门面。"""

from __future__ import annotations

import contextlib
import socket
from typing import Callable, Generator, List, Optional, Tuple, Union

from yyds_port.async_api.wait import (
    async_wait_for_closed,
    async_wait_for_open,
    probe_tcp_connection,
    wait_for_closed,
    wait_for_open,
)
from yyds_port.core.allocator import (
    _is_port_available,
    find_free_port,
    find_free_range,
    reserve_port,
)
from yyds_port.core.models import ProcessInfo, Protocol
from yyds_port.core.platform.base import get_default_scanner
from yyds_port.core.safety import check_pid_safety, check_port_safety, terminate_pid


class Port(int):
    """
    Port 现代化端口实体类。

    继承自 Python 原生 `int`，既具备完整的整数兼容性（可直接作为端口传给 socket.bind、requests、uvicorn 等），
    又内建了端口探测、占用诊断、就绪轮询、智能避让与安全优雅释放等生产级能力。
    """

    _proto: Protocol

    def __new__(cls, value: int, proto: Union[str, Protocol] = Protocol.TCP) -> Port:
        port_num = int(value)
        if not (1 <= port_num <= 65535):
            raise ValueError(f"Port number must be between 1 and 65535, got: {port_num}")

        instance = super().__new__(cls, port_num)
        instance._proto = Protocol.from_str(proto)
        return instance

    @property
    def proto(self) -> Protocol:
        """端口对应的网络协议 (TCP / UDP)。"""
        return self._proto

    def __repr__(self) -> str:
        return f"Port({int(self)}, proto={self._proto.value!r})"

    def __str__(self) -> str:
        return str(int(self))

    # ==========================
    # 状态与诊断能力
    # ==========================

    def is_free(self, host: str = "127.0.0.1") -> bool:
        """检查该端口当前是否完全空闲可绑定（没有任何服务正在监听）。"""
        return _is_port_available(int(self), host=host, proto=self._proto)

    def is_open(self, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
        """检查该端口当前是否有服务在正常监听（能完成 TCP 握手）。"""
        if self._proto == Protocol.UDP:
            # UDP 无法通过简单握手确认，判断 occupant 状态
            return self.occupant() is not None
        return probe_tcp_connection(host, int(self), timeout=timeout)

    def occupant(self) -> Optional[ProcessInfo]:
        """查询当前正在占用该端口的进程详情。若未被占用返回 None。"""
        scanner = get_default_scanner()
        return scanner.find_occupant(int(self), proto=self._proto)

    # ==========================
    # 进程安全治理与端口释放
    # ==========================

    def free(
        self,
        timeout: float = 2.0,
        force: bool = False,
        kill_tree: bool = True,
        allow_protected: bool = False,
    ) -> bool:
        """
        优雅或强力释放当前端口所被占用的进程。
        - timeout: 等待进程优雅退出的秒数（超时未退出将升级为 SIGKILL）。
        - force: 是否直接发送 SIGKILL 强行终止。
        - kill_tree: 是否递归清理整个子进程树（彻底清理 Python/Node 等多进程服务）。
        - allow_protected: 是否允许强杀 SSH/DNS 等系统关键保护端口（默认 False，触发安全熔断保护）。
        返回 True 表示端口已成功释放为可用状态；False 表示未能释放。
        """
        check_port_safety(int(self), allow_protected=allow_protected)

        occ = self.occupant()
        if occ is None or occ.pid is None:
            # 若已无占用进程或端口本身已空闲
            return self.is_free()

        check_pid_safety(occ.pid)

        # 执行带有防漂移校验与级联清理的终止操作
        terminated = terminate_pid(
            occ.pid,
            timeout=timeout,
            force=force,
            kill_tree=kill_tree,
        )

        return terminated and self.is_free()

    # ==========================
    # 服务就绪等待
    # ==========================

    def wait_open(
        self,
        host: str = "127.0.0.1",
        timeout: float = 10.0,
        initial_interval: float = 0.05,
        max_interval: float = 0.5,
        backoff: float = 1.3,
        check_fn: Optional[Callable[[socket.socket], bool]] = None,
    ) -> Port:
        """
        同步阻塞等待端口开放（可连接）。
        若在 timeout 内未开放，抛出 PortWaitTimeoutError。
        成功就绪时返回 self。
        """
        wait_for_open(
            port=int(self),
            host=host,
            timeout=timeout,
            initial_interval=initial_interval,
            max_interval=max_interval,
            backoff=backoff,
            check_fn=check_fn,
        )
        return self

    def wait_closed(
        self,
        host: str = "127.0.0.1",
        timeout: float = 10.0,
        interval: float = 0.1,
    ) -> Port:
        """同步阻塞等待端口关闭释放。成功时返回 self。"""
        wait_for_closed(port=int(self), host=host, timeout=timeout, interval=interval)
        return self

    async def async_wait_open(
        self,
        host: str = "127.0.0.1",
        timeout: float = 10.0,
        initial_interval: float = 0.05,
        max_interval: float = 0.5,
        backoff: float = 1.3,
    ) -> Port:
        """原生 asyncio 异步等待端口就绪开放。成功时返回 self。"""
        await async_wait_for_open(
            port=int(self),
            host=host,
            timeout=timeout,
            initial_interval=initial_interval,
            max_interval=max_interval,
            backoff=backoff,
        )
        return self

    async def async_wait_closed(
        self,
        host: str = "127.0.0.1",
        timeout: float = 10.0,
        interval: float = 0.1,
    ) -> Port:
        """原生 asyncio 异步等待端口关闭。成功时返回 self。"""
        await async_wait_for_closed(port=int(self), host=host, timeout=timeout, interval=interval)
        return self

    # ==========================
    # 动态分配与类级别便捷接口
    # ==========================

    @classmethod
    def find_free(
        cls,
        start: int = 1024,
        end: int = 65535,
        host: str = "127.0.0.1",
        proto: Union[str, Protocol] = Protocol.TCP,
    ) -> Port:
        """寻找一个空闲可用端口并包装为 Port 实例返回。"""
        p_enum = Protocol.from_str(proto)
        free_num = find_free_port(start=start, end=end, host=host, proto=p_enum)
        return cls(free_num, proto=p_enum)

    @classmethod
    def find_free_range(
        cls,
        count: int,
        start: int = 1024,
        end: int = 65535,
        host: str = "127.0.0.1",
        proto: Union[str, Protocol] = Protocol.TCP,
    ) -> List[Port]:
        """批量查找连续 count 个可用端口。"""
        p_enum = Protocol.from_str(proto)
        ports = find_free_range(count=count, start=start, end=end, host=host, proto=p_enum)
        return [cls(p, proto=p_enum) for p in ports]

    @classmethod
    @contextlib.contextmanager
    def reserve(
        cls,
        start: int = 1024,
        end: int = 65535,
        host: str = "127.0.0.1",
        proto: Union[str, Protocol] = Protocol.TCP,
        collaborative: bool = True,
        pass_fd: bool = False,
    ) -> Generator[Port | Tuple[Port, socket.socket], None, None]:
        """独占预留端口上下文管理器（支持协同排他文件锁与 Socket FD 移交）。"""
        p_enum = Protocol.from_str(proto)
        with reserve_port(
            start=start,
            end=end,
            host=host,
            proto=p_enum,
            collaborative=collaborative,
            pass_fd=pass_fd,
        ) as res:
            if pass_fd:
                port_num, sock = res  # type: ignore
                yield cls(port_num, proto=p_enum), sock
            else:
                yield cls(res, proto=p_enum)  # type: ignore

    @classmethod
    def ls(
        cls, proto: Optional[Union[str, Protocol]] = None
    ) -> List[Tuple[Port, ProcessInfo]]:
        """全量列出当前正在监听的所有端口及其占用者详情。"""
        p_enum = Protocol.from_str(proto) if proto is not None else None
        scanner = get_default_scanner()
        raw_list = scanner.list_all_occupants(proto=p_enum)
        return [(cls(p, proto=info.proto), info) for p, info in raw_list]
