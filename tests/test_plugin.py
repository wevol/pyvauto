"""
Vim 插件整合測試 - 以 headless vim 實際驅動 plugin/pyvauto.vim。

自動化先前只能手動跑的端到端流程，並把插件的關鍵約定鎖進 CI：
預設 g:pyvauto_script 指向真正的 pyvauto.py、:Pyvauto 命令存在、
\va 有綁定，以及在 vim 內按下擴展後檔案確實被就地展開。

若環境沒有 vim（例如某些 CI），整個模組會 skip，不會誤紅。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PLUGIN = REPO / "plugin" / "pyvauto.vim"
VIM = shutil.which("vim")

pytestmark = pytest.mark.skipif(VIM is None, reason="vim not installed")

SUB = "module sub (input clk, input [7:0] data_i, output [7:0] data_o);\nendmodule\n"
TOP = "module top;\n    sub u_sub (\n        /*AUTOINST*/\n    );\nendmodule\n"


def _run_vim(script_path):
    subprocess.run(
        [VIM, "-u", "NONE", "-N", "-es", "-S", str(script_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_plugin_defaults_and_mappings(tmp_path):
    """預設腳本路徑解析到存在的 pyvauto.py，:Pyvauto 與 \\va 都就緒。"""
    result = tmp_path / "result.txt"
    script = tmp_path / "check.vim"
    script.write_text(
        f"source {PLUGIN}\n"
        f"redir! > {result}\n"
        "echo 'script_readable=' . filereadable(g:pyvauto_script)\n"
        "echo 'has_Pyvauto=' . exists(':Pyvauto')\n"
        "echo 'map_va=' . maparg('\\va', 'n')\n"
        "redir END\n"
        "qa!\n"
    )
    _run_vim(script)

    text = result.read_text()
    assert "script_readable=1" in text          # default path points at a real file
    assert "has_Pyvauto=2" in text               # command is defined
    assert "Pyvauto" in text                     # \va maps to :Pyvauto


def test_plugin_end_to_end_expansion(tmp_path):
    """在 vim 內開檔 → :Pyvauto → 檔案被就地展開（完整端到端）。"""
    (tmp_path / "sub.sv").write_text(SUB)
    top = tmp_path / "top.sv"
    top.write_text(TOP)

    script = tmp_path / "run.vim"
    script.write_text(
        f"source {PLUGIN}\n"
        f"cd {tmp_path}\n"
        "edit top.sv\n"
        "Pyvauto\n"
        "qa!\n"
    )
    _run_vim(script)

    out = top.read_text()
    assert ".clk" in out and ".data_i" in out and ".data_o" in out
