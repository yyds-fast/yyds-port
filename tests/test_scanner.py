"""单元测试：端口探测器与进程信息获取。"""

import os
import socket
from yyds_port import Port, Protocol
from yyds_port.core.platform.base import get_default_scanner


def test_scanner_find_occupant_current_process():
    port = Port.find_free(start=36001, end=37000)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(1)

    try:
        p = Port(port)
        occ = p.occupant()
        assert occ is not None
        # 当前进程监听的 socket，应能正确匹配到当前进程的 PID
        assert occ.pid == os.getpid()
        assert "python" in occ.name.lower()
        assert occ.listen_address.endswith(str(port))
    finally:
        s.close()


def test_scanner_list_all():
    scanner = get_default_scanner()
    all_occupants = scanner.list_all_occupants()
    assert isinstance(all_occupants, list)
    # 系统上一定存在至少一个监听端口 (如 SSH/DNS 等)
    assert len(all_occupants) > 0


def test_port_ls():
    items = Port.ls(proto="tcp")
    assert isinstance(items, list)
    for p, info in items:
        assert isinstance(p, Port)
        assert info.proto == Protocol.TCP
