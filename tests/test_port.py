"""单元测试：Port 实体类核心功能。"""

import socket
import pytest
from yyds_port import Port, Protocol


def test_port_validation():
    p = Port(8080)
    assert int(p) == 8080
    assert p.proto == Protocol.TCP
    assert repr(p) == "Port(8080, proto='tcp')"
    assert str(p) == "8080"

    with pytest.raises(ValueError):
        Port(0)

    with pytest.raises(ValueError):
        Port(70000)


def test_port_int_compatibility():
    p = Port(3000)
    assert p + 1 == 3001
    assert p - 1 == 2999
    assert p * 2 == 6000
    assert p == 3000

    # 作为元组传给 socket
    addr = ("127.0.0.1", p)
    assert addr[1] == 3000


def test_port_is_free_and_is_open():
    free_port = Port.find_free(start=28000, end=29000)
    assert free_port.is_free() is True
    assert free_port.is_open() is False

    # 启动监听后
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", free_port))
    s.listen(1)

    try:
        assert free_port.is_free() is False
        assert free_port.is_open() is True
    finally:
        s.close()

    assert free_port.is_free() is True


def test_port_wait_open_and_closed():
    p = Port.find_free(start=29001, end=29999)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", p))
    s.listen(1)

    p.wait_open(timeout=2.0)
    assert p.is_open() is True

    s.close()
    p.wait_closed(timeout=2.0)
    assert p.is_free() is True


@pytest.mark.asyncio
async def test_port_async_wait_open_and_closed():
    p = Port.find_free(start=30000, end=31000)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", p))
    s.listen(1)

    await p.async_wait_open(timeout=2.0)
    assert p.is_open() is True

    s.close()
    await p.async_wait_closed(timeout=2.0)
    assert p.is_free() is True
