"""单元测试：模型、枚举与异常类。"""

from yyds_port.core.models import (
    PortOccupiedError,
    PortWaitTimeoutError,
    ProcessInfo,
    ProtectedPortError,
    Protocol,
)


def test_protocol_normalization():
    assert Protocol.from_str("tcp") == Protocol.TCP
    assert Protocol.from_str("TCP") == Protocol.TCP
    assert Protocol.from_str(Protocol.TCP) == Protocol.TCP
    assert Protocol.from_str("udp") == Protocol.UDP
    assert Protocol.from_str("UDP") == Protocol.UDP
    assert str(Protocol.TCP) == "tcp"


def test_process_info_to_dict():
    info = ProcessInfo(
        pid=1234,
        name="test_proc",
        cmdline=["test_proc", "--port", "8000"],
        listen_address="127.0.0.1:8000",
        proto=Protocol.TCP,
        user="test_user",
        cwd="/tmp",
        inode=9999,
        permission_denied=False,
    )

    d = info.to_dict()
    assert d["pid"] == 1234
    assert d["name"] == "test_proc"
    assert "test_proc --port 8000" in d["cmdline_str"]
    assert d["listen_address"] == "127.0.0.1:8000"
    assert d["proto"] == "tcp"
    assert d["user"] == "test_user"


def test_exceptions():
    err1 = PortOccupiedError(8080)
    assert "8080" in str(err1)

    err2 = PortWaitTimeoutError(8080, "localhost", 5.0, "open")
    assert "Timed out" in str(err2)

    err3 = ProtectedPortError(22)
    assert "22" in str(err3)


def test_package_metadata():
    import yyds_port
    assert yyds_port.__title__ == "yyds-port"
    assert yyds_port.__version__ == "1.1.0"
    assert yyds_port.__author__ == "yyds-fast"
    assert yyds_port.__license__ == "MIT"
    assert "yyds-fast/yyds-port" in yyds_port.__url__
    assert bool(yyds_port.__description__)
