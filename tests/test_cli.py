"""
CLI 進入點測試 - 以 subprocess 實際執行 `python pyvauto.py <file>`。

驗證 main() 的就地展開、多檔處理、找不到檔案時的 Skip 訊息與冪等性。
這些路徑（argparse、掃描 cwd、寫回檔案）過去只有手動驗證，未進 CI。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "pyvauto.py"

SUB = "module sub (input clk, input [7:0] data_i, output [7:0] data_o);\nendmodule\n"
TOP = "module top;\n    sub u_sub (\n        /*AUTOINST*/\n    );\nendmodule\n"


def _run(args, cwd):
    """以 cwd 執行 pyvauto.py（CLI 會索引 cwd 找模組定義）。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_expands_in_place(tmp_path):
    (tmp_path / "sub.sv").write_text(SUB)
    top = tmp_path / "top.sv"
    top.write_text(TOP)

    r = _run(["top.sv"], tmp_path)

    assert r.returncode == 0, r.stderr
    out = top.read_text()
    assert ".clk" in out and ".data_i" in out and ".data_o" in out
    assert "Successfully expanded" in r.stdout


def test_cli_missing_file_is_skipped(tmp_path):
    r = _run(["does_not_exist.sv"], tmp_path)

    assert r.returncode == 0
    assert "Skip" in r.stdout and "not found" in r.stdout


def test_cli_second_run_is_idempotent(tmp_path):
    (tmp_path / "sub.sv").write_text(SUB)
    top = tmp_path / "top.sv"
    top.write_text(TOP)

    _run(["top.sv"], tmp_path)
    after_first = top.read_text()
    r = _run(["top.sv"], tmp_path)

    assert top.read_text() == after_first
    assert "No changes made" in r.stdout


def test_cli_handles_multiple_files(tmp_path):
    (tmp_path / "sub.sv").write_text(SUB)
    t1 = tmp_path / "top.sv"
    t1.write_text(TOP)
    t2 = tmp_path / "top2.sv"
    t2.write_text(TOP.replace("module top;", "module top2;").replace("u_sub", "u_sub2"))

    r = _run(["top.sv", "top2.sv"], tmp_path)

    assert r.returncode == 0, r.stderr
    assert ".clk" in t1.read_text()
    assert ".clk" in t2.read_text()
