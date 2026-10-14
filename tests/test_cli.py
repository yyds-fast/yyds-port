"""单元测试：CLI 命令行接口。"""

import json
import pytest
from yyds_port.cli.main import main


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "yyds-port" in captured.out


def test_cli_find(capsys):
    ret = main(["find", "--start", "38000", "--end", "39000"])
    assert ret == 0
    captured = capsys.readouterr()
    port_val = int(captured.out.strip())
    assert 38000 <= port_val <= 39000


def test_cli_find_positional_arg(capsys):
    # 测试 yyds-port find 38000 位置参数语法
    ret = main(["find", "38000"])
    assert ret == 0
    captured = capsys.readouterr()
    port_val = int(captured.out.strip())
    assert port_val >= 38000


def test_cli_find_range_positional_arg(capsys):
    # 测试 yyds-port find 38000 38050 位置参数区间语法
    ret = main(["find", "38000", "38050"])
    assert ret == 0
    captured = capsys.readouterr()
    port_val = int(captured.out.strip())
    assert 38000 <= port_val <= 38050



def test_cli_find_json(capsys):
    ret = main(["find", "--start", "38000", "--end", "39000", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "port" in data
    assert 38000 <= data["port"] <= 39000


def test_cli_who_free_port(capsys):
    # 找一个必然空闲的端口
    from yyds_port import Port
    free_p = Port.find_free(start=40000, end=41000)

    ret = main(["who", str(int(free_p))])
    # 未被占用时返回 1
    assert ret == 1
    captured = capsys.readouterr()
    assert "FREE" in captured.out


def test_cli_ls_json(capsys):
    ret = main(["ls", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
