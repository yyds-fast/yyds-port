"""单元测试：端口分配器与预留上下文。"""

import socket
import pytest
from yyds_port import Port
from yyds_port.core.allocator import find_free_port, find_free_range


def test_find_free_single():
    port = find_free_port(start=32000, end=33000)
    assert 32000 <= port <= 33000

    # 验证随机分配 (start=0)
    kernel_port = find_free_port(start=0)
    assert 1024 <= kernel_port <= 65535


def test_find_free_range():
    ports = find_free_range(count=3, start=33001, end=34000)
    assert len(ports) == 3
    assert ports[1] == ports[0] + 1
    assert ports[2] == ports[1] + 1


def test_find_free_invalid_range():
    with pytest.raises(ValueError):
        find_free_port(start=5000, end=4000)


def test_reserve_port_collaborative():
    with Port.reserve(start=34001, end=35000) as p:
        assert isinstance(p, Port)
        # 在上下文内可以正常被我们使用
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", p))
        s.listen(1)
        s.close()


def test_reserve_port_pass_fd():
    with Port.reserve(start=35001, end=36000, pass_fd=True) as (p, sock):
        assert isinstance(p, Port)
        assert sock.fileno() > 0
        # 此时端口已经被该 socket 监听
        assert p.is_open() is True


def test_lock_dir_user_isolation():
    from yyds_port.core.allocator import _get_lock_dir
    lock_dir = _get_lock_dir()
    assert lock_dir.exists()
    # 路径应包含 yyds_port_locks
    assert "yyds_port_locks" in str(lock_dir)

