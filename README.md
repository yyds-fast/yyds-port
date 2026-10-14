# yyds-port

[![PyPI version](https://img.shields.io/pypi/v/yyds-port.svg)](https://pypi.org/project/yyds-port/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)

面向现代 Python、微服务容器与本地开发环境的**零依赖端口诊断、智能避让、优雅释放与就绪探测库**。既是生产级高可靠 Python SDK，又是极速 CLI 终端诊断神器。

---

## 💡 核心特性 (Key Features)

* 🪶 **100% 零第三方重依赖（Zero Runtime Dependencies）**：纯 Python 标准库编写，无 `psutil`、`click` 或 `rich` 等额外依赖。即便在无 `gcc`、极度精简的 Docker 容器（如 `python:3.11-slim`, `alpine`）中也能秒级安装、开箱即用。
* 🐧 **Linux 原生 `/proc` 深度解析（Docker/容器极致友好）**：在精简镜像中往往没有预装 `lsof`/`netstat`/`ss`。`yyds-port` 通过纯 Python 读取内核虚拟文件系统（`/proc/net/tcp[6]`、`/proc/net/udp[6]` 与 `/proc/[pid]/fd`），结合 Hex 高速预过滤，单端口毫秒级精准锁定占用 PID、进程名、启动命令行与运行用户。
* ⚡ **Windows 原生 `ctypes` 极速引擎**：Windows 下优先使用纯标准库 `ctypes` 直调 Windows 内核 `iphlpapi.dll`（`GetExtendedTcpTable` / `GetExtendedUdpTable`），查询耗时从调用 `netstat` 的数百毫秒降至 **< 5ms（提速 100 倍以上）**，且彻底杜绝 GBK/UTF-8 终端编码页乱码。
* 🛡️ **安全熔断与防误杀（Anti-Kill-Accident）**：默认建立关键系统保护区（严禁误杀 22 SSH、53 DNS 等端口），拒绝向 PID $\le 100$ 的系统底层进程发信号；支持内核状态机感知（识别并回收 Zombie 僵尸进程），并在发信号前进行防 PID 漂移二次校验。
* 🔒 **协作式排他锁（抗 TOCTOU 并发竞态）**：针对 `pytest -n auto` 等多进程并发自动化测试，提供基于 `XDG_RUNTIME_DIR`（tmpfs 纯内存盘）的用户级协同文件锁，消除多进程同时申请端口的抢占冲突。
* ⏱️ **毫秒级就绪探测与指数退避**：提供同步 `wait_open()` 与异步 `async_wait_open()`，替代脆弱的 `time.sleep()`；支持双栈回退（IPv4/IPv6），并在短连接探测后利用 `SO_LINGER` 发送 RST 快速回收，杜绝 TIME_WAIT 堆积耗尽系统的临时端口。
* 🖥️ **全能极速 CLI**：开箱即用提供 `yyds-port who`、`free`、`wait`、`find`、`ls` 五大子命令，纯 ANSI 优美终端卡片与表格输出，全线命令支持 `--json` 输出，并可与同家桌面通知工具 `yyds-notify-os` 自动联动。

---

## 🚀 安装 (Installation)

通过 PyPI 安装：
```bash
pip install -U yyds-port
```

或在源码目录中以可编辑模式开发安装：
```bash
pip install -e .
```

---

## 💻 Python API 使用指南

### 1. 基础诊断与占用查询

`Port` 继承自 Python 原生 `int`，既能无缝作为整型端口传给 `socket.bind()`、`requests` 或 `uvicorn.run()`，又自带丰富的操作能力：

```python
from yyds_port import Port, Protocol

p = Port(8000)

# 1. 状态判断
print(p.is_free())          # 是否完全空闲可绑定
print(p.is_open())          # 是否已有服务处于 LISTEN 状态且可连通

# 2. 占用者详细诊断
occupant = p.occupant()
if occupant:
    if occupant.permission_denied:
        print("提示: 端口已被特权用户占用，请使用 sudo 运行以查看详情")
    else:
        print(f"PID:        {occupant.pid}")
        print(f"进程名:     {occupant.name}")          # 如: python3
        print(f"启动命令行: {occupant.cmdline}")       # 如: ['python3', '-m', 'uvicorn', ...]
        print(f"监听地址:   {occupant.listen_address}") # 如: 0.0.0.0:8000
        print(f"运行用户:   {occupant.user}")          # 如: wzb
        print(f"工作目录:   {occupant.cwd}")           # 如: /home/wzb/my_project
```

### 2. 智能避让与动态端口分配

```python
# 1. 查找首个可用空闲端口（从 8000 往后顺延避让）
port = Port.find_free(start=8000, end=9000)

# 2. 批量查找连续 N 个可用端口（适用于分布式集群、微服务多端口矩阵）
ports = Port.find_free_range(count=3, start=9000)  # [9000, 9001, 9002]

# 3. 独占预留上下文管理器（多进程并发测试防止端口冲突）
with Port.reserve(start=8000) as port:
    server = start_my_test_server(port=port)
```

### 3. 服务就绪等待（告别硬编码 `time.sleep`）

```python
import asyncio
from yyds_port import Port

# 同步阻塞等待：等待本地/远程数据库在 15 秒内就绪，内置指数退避
Port(5432).wait_open(host="127.0.0.1", timeout=15.0)

# 支持应用层探针 Hook（连通后发送探活数据）
def redis_ping(sock):
    sock.sendall(b"PING\r\n")
    return b"+PONG" in sock.recv(1024)

Port(6379).wait_open(check_fn=redis_ping, timeout=10.0)

# 原生 asyncio 异步等待：FastAPI / Asyncio 启动流程中等待下游服务就绪
await Port(11434).async_wait_open(host="localhost", timeout=10.0)

# 等待旧服务完全退出并释放端口
Port(8080).wait_closed(timeout=5.0)
```

### 4. 智能释放与进程治理

```python
p = Port(8000)

# 优雅释放（默认先发 SIGTERM，等待 2 秒未退出则自动升级为 SIGKILL）
p.free(timeout=2.0)

# 强力彻底释放进程树（递归干掉所有衍生子进程，杜绝孤儿/僵尸进程）
p.free(force=True, kill_tree=True)
```

---

## 🛠️ CLI 命令行工具 (`yyds-port`)

`yyds-port` 内置轻量 ANSI 渲染引擎，在无第三方库依赖下呈现终端高颜值输出：

### 1. `yyds-port who <port>`（谁在占用该端口）
```bash
yyds-port who 8000
```
```text
╭── Port 8000 Occupant ─────────────────────────────────────────╮
│  Port:                    8000 (TCP)                          │
│  PID:                     28419                               │
│  Process:                 uvicorn                             │
│  User:                    wzb                                 │
│  Command:                 python3 -m uvicorn app:app --port 8000
│  Status:                  LISTEN (0.0.0.0:8000)               │
│  CWD:                     /home/wzb/app                       │
╰───────────────────────────────────────────────────────────────╯
```
支持管道化 JSON 输出：
```bash
$ yyds-port who 8000 --json | jq .occupant.pid
28419
```

### 2. `yyds-port free <port> [-f/--force] [-y/--yes]`（安全释放端口）
```bash
yyds-port free 8000
```
```text
[?] Process uvicorn (PID 28419) is listening on port 8000. Kill it? [y/N]: y
[*] Terminating PID 28419 (uvicorn)...
[✓] Successfully freed port 8000!
```

### 3. `yyds-port wait <host:port> [--notify]`（等待端口就绪，脚本神器）
```bash
yyds-port wait 127.0.0.1:11434 --timeout 30 --notify
```
```text
[*] Waiting for 127.0.0.1:11434 to become reachable (timeout=30.0s)...
[✓] Port 11434 is OPEN! (connected in 1.42s)
[🔔] Desktop notification dispatched.
```

### 4. `yyds-port find [port] [end] [-c/--count 1]`（查找空闲端口）
支持直接传入起始端口（位置参数），非常适合在 CI/CD 或 Shell 启动脚本中极简嵌套赋值：
```bash
# 自动寻找从 8000 开始的首个可用端口
APP_PORT=$(yyds-port find 8000)
echo "Allocated port: $APP_PORT"

# 在 8000~8050 区间内寻找连续 3 个可用端口
yyds-port find 8000 8050 --count 3
```


### 5. `yyds-port ls`（全景端口看板）
一览当前机器所有正在监听的 TCP/UDP 端口及对应进程，替代难读的 `netstat -tulnp`：
```bash
yyds-port ls
```
```text
Port   Proto  Address                           PID      Process              User           
─────────────────────────────────────────────────────────────────────────────────────────────
22     TCP    0.0.0.0:22                        892      sshd                 root           
5432   TCP    127.0.0.1:5432                    1420     postgres             postgres       
6379   TCP    127.0.0.1:6379                    1510     redis-server         redis          
8000   TCP    0.0.0.0:8000                      28419    uvicorn              wzb            
11434  TCP    127.0.0.1:11434                   3102     ollama               wzb            
```

---

## 🧪 自动化测试与质量保障

项目测试套件严格遵循高质量生产规范，覆盖真实 Socket 绑定、并发文件锁、异步等待、安全熔断与 CLI 命令：

```bash
# 运行全部单元与集成测试
pytest -v

# 运行代码静态检查
ruff check yyds_port tests

# 验证构建 Wheel 包与源分发包
./build.sh --clean
```

---

## 📄 授权许可 (License)

本项目基于 [MIT License](LICENSE) 开源。
