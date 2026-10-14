"""单元测试：安全防护与防误杀熔断。"""

import pytest
from yyds_port import Port, ProtectedPortError
from yyds_port.core.safety import (
    check_pid_safety,
    check_port_safety,
    is_pid_alive,
)


def test_protected_port_safety():
    # 22 为 SSH 保护端口
    p = Port(22)
    with pytest.raises(ProtectedPortError):
        p.free()

    # 显式允许时可以通过检查（但通常因权限不足而无法实际 kill 系统 sshd）
    check_port_safety(22, allow_protected=True)


def test_low_pid_safety():
    # PID 1 (init / systemd) 应被坚决拒绝
    with pytest.raises(ValueError):
        check_pid_safety(1)

    with pytest.raises(ValueError):
        check_pid_safety(None)


def test_is_pid_alive():
    import os
    assert is_pid_alive(os.getpid()) is True
    # 极大 PID 通常不存在
    assert is_pid_alive(9999999) is False


def test_zombie_process_handling():
    import os
    import time
    if hasattr(os, "fork"):
        child_pid = os.fork()
        if child_pid == 0:
            # 子进程必须使用 os._exit 避免 pytest SystemExit 捕获
            os._exit(0)
        time.sleep(0.05)
        try:
            # is_pid_alive 应识别僵尸状态或通过非阻塞 waitpid 判定为已退出 (False)
            assert is_pid_alive(child_pid) is False
        finally:
            try:
                os.waitpid(child_pid, os.WNOHANG)
            except OSError:
                pass


