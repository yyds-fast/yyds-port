"""进程安全治理、防误杀熔断与进程树终止模块。"""

from __future__ import annotations

import os
import signal
import sys
import time
from typing import Dict, List, Optional, Set

from yyds_port.core.models import ProtectedPortError


# 默认系统保护端口白名单（SSH、DNS、DHCP、RPC、Docker 守护）
DEFAULT_PROTECTED_PORTS: Set[int] = {
    22,    # SSH
    53,    # DNS
    67,    # DHCP
    68,    # DHCP Client
    111,   # rpcbind
    2375,  # Docker Daemon
    2376,  # Docker Daemon TLS
}

# 最小安全 PID 阈值（禁止终止 <= 100 的系统关键/内核进程）
MIN_SAFE_PID: int = 100


def check_port_safety(port: int, allow_protected: bool = False) -> None:
    """检查目标端口是否处于系统保护熔断名单中。"""
    if not allow_protected and port in DEFAULT_PROTECTED_PORTS:
        raise ProtectedPortError(
            port,
            f"Port {port} is protected by safety whitelist (e.g. SSH/DNS). "
            f"Pass allow_protected=True if you really know what you are doing.",
        )


def check_pid_safety(pid: Optional[int]) -> None:
    """检查 PID 是否安全可终止。"""
    if pid is None:
        raise ValueError("Cannot kill process with null PID (permission denied or not found)")
    if pid <= MIN_SAFE_PID:
        raise ValueError(
            f"Refused to kill low-level system process (PID {pid} <= {MIN_SAFE_PID})"
        )


def is_pid_alive(pid: int) -> bool:
    """
    检查指定 PID 进程当前是否存在且处于活跃状态。
    针对 Linux 增加了对僵尸进程 (Zombie) 的状态识别，避免子进程退出后引发假死轮询。
    """
    # 1. 若为自身直接派生的子进程，先尝试非阻塞回收
    try:
        wpid, _ = os.waitpid(pid, os.WNOHANG)
        if wpid == pid:
            return False
    except (ChildProcessError, OSError):
        pass

    # 2. 信号探测
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    # 3. Linux 边缘状态排查：若已处于 Zombie 或 Dead 状态则视同已退出
    if sys.platform.startswith("linux"):
        stat_path = f"/proc/{pid}/stat"
        try:
            with open(stat_path, "r", encoding="ascii", errors="replace") as f:
                content = f.readline()
                rparen = content.rfind(")")
                if rparen != -1 and rparen + 2 < len(content):
                    state = content[rparen + 2]
                    # 'Z' 代表 Zombie (僵尸), 'X' 代表 Dead
                    if state in ("Z", "X"):
                        return False
        except (OSError, PermissionError):
            return False

    return True


def get_process_children_linux(parent_pid: int) -> List[int]:
    """Linux 原生从 /proc 解析获取指定 PID 的所有直接子进程。"""
    children: List[int] = []

    # 1. 优先尝试读取 /proc/[pid]/task/[tid]/children (Linux 3.5+ 内核特性)
    task_dir = f"/proc/{parent_pid}/task"
    if os.path.exists(task_dir):
        try:
            for tid in os.listdir(task_dir):
                children_file = f"{task_dir}/{tid}/children"
                if os.path.exists(children_file):
                    with open(children_file, "r") as cf:
                        content = cf.read().strip()
                        if content:
                            for c in content.split():
                                if c.isdigit():
                                    children.append(int(c))
            if children:
                return list(set(children))
        except (OSError, PermissionError):
            pass

    # 2. 备选方案：单次扫描所有 /proc/[pid]/stat 匹配 PPID
    try:
        for p in os.listdir("/proc"):
            if not p.isdigit():
                continue
            stat_file = f"/proc/{p}/stat"
            try:
                with open(stat_file, "r") as sf:
                    line = sf.readline()
                    # stat 格式: pid (comm) state ppid ...
                    # 注意 comm 可能包含空格和括号，取最后一个 ')' 之后的内容
                    rparen = line.rfind(")")
                    if rparen != -1:
                        rest = line[rparen + 1 :].split()
                        if len(rest) >= 2:
                            ppid = int(rest[1])
                            if ppid == parent_pid:
                                children.append(int(p))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass

    return list(set(children))


def get_all_descendant_pids(root_pid: int) -> List[int]:
    """递归获取所有后代子进程（按深度自底向上的顺序排列，便于清理）。"""
    if sys.platform != "linux":
        return []

    descendants: List[int] = []
    to_visit = [root_pid]
    visited = {root_pid}
    tree: Dict[int, List[int]] = {}

    while to_visit:
        curr = to_visit.pop(0)
        kids = get_process_children_linux(curr)
        tree[curr] = kids
        for kid in kids:
            if kid not in visited:
                visited.add(kid)
                to_visit.append(kid)

    # 深度优先后序遍历，确保子节点排在父节点前面
    def post_order(pid: int):
        for child in tree.get(pid, []):
            post_order(child)
            if child not in descendants:
                descendants.append(child)

    post_order(root_pid)
    return descendants


def terminate_pid(
    pid: int,
    timeout: float = 2.0,
    force: bool = False,
    kill_tree: bool = False,
) -> bool:
    """
    跨平台、带防漂移校验与子进程树清理的终止进程函数。
    返回 True 表示进程已成功退出；False 表示超时或未能终止。
    """
    check_pid_safety(pid)

    if not is_pid_alive(pid):
        return True

    # Windows 平台处理
    if sys.platform in ("win32", "cygwin"):
        import subprocess
        cmd = ["taskkill"]
        if force:
            cmd.append("/F")
        if kill_tree:
            cmd.append("/T")
        cmd.extend(["/PID", str(pid)])
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return not is_pid_alive(pid)

    # POSIX (Linux / macOS) 处理
    pids_to_kill = []
    if kill_tree and sys.platform == "linux":
        # 自底向上的子代列表
        pids_to_kill.extend(get_all_descendant_pids(pid))
    pids_to_kill.append(pid)

    sig_initial = signal.SIGKILL if force else signal.SIGTERM

    # 1. 发送初始信号
    for p in pids_to_kill:
        if is_pid_alive(p):
            try:
                os.kill(p, sig_initial)
            except (ProcessLookupError, PermissionError):
                pass

    if force:
        # 强制模式直接短暂等待验证
        time.sleep(0.05)
        return not is_pid_alive(pid)

    # 2. 优雅轮询等待退出
    deadline = time.time() + max(timeout, 0.1)
    while time.time() < deadline:
        if not is_pid_alive(pid):
            return True
        time.sleep(0.05)

    # 3. 超时未退出，升级为 SIGKILL
    for p in pids_to_kill:
        if is_pid_alive(p):
            try:
                os.kill(p, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    time.sleep(0.05)
    return not is_pid_alive(pid)
