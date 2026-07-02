"""
Vim plugin integration tests — drive plugin/pyvauto.vim with headless vim.

Automates the end-to-end flow that previously could only be run by hand, and
locks the plugin's key contracts into CI: the default g:pyvauto_script points at
the real pyvauto.py, the :Pyvauto command exists, \va is bound, and pressing
expand inside vim actually expands the file in place.

If vim is unavailable (e.g. on some CI), the whole module is skipped rather than
failing.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PLUGIN = REPO / "plugin" / "pyvauto.vim"
VIM = shutil.which("vim")
GO = shutil.which("go")

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
    """The default script path resolves to a real pyvauto.py; :Pyvauto and \\va are ready."""
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
    """Open a file in vim -> :Pyvauto -> the file is expanded in place (full end-to-end)."""
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


def test_plugin_delete_command_and_mappings(tmp_path):
    """The :NVA command exists; \\nva and <F6> are both bound to :NVA."""
    result = tmp_path / "result.txt"
    script = tmp_path / "check.vim"
    script.write_text(
        f"source {PLUGIN}\n"
        f"redir! > {result}\n"
        "echo 'has_NVA=' . exists(':NVA')\n"
        "echo 'map_nva=' . maparg('\\nva', 'n')\n"
        "echo 'map_F6=' . maparg('<F6>', 'n')\n"
        "redir END\n"
        "qa!\n"
    )
    _run_vim(script)

    text = result.read_text()
    assert "has_NVA=2" in text          # command defined
    assert "map_nva=:NVA" in text       # \nva maps to :NVA
    assert "map_F6=:NVA" in text        # <F6> maps to :NVA


def test_plugin_end_to_end_delete(tmp_path):
    """After :Pyvauto expands inside vim -> :NVA un-expands -> auto connections gone, tag remains."""
    (tmp_path / "sub.sv").write_text(SUB)
    top = tmp_path / "top.sv"
    top.write_text(TOP)

    script = tmp_path / "run.vim"
    script.write_text(
        f"source {PLUGIN}\n"
        f"cd {tmp_path}\n"
        "edit top.sv\n"
        "Pyvauto\n"
        "NVA\n"
        "qa!\n"
    )
    _run_vim(script)

    out = top.read_text()
    assert "/*AUTOINST*/" in out
    assert ".clk" not in out and ".data_o" not in out


@pytest.mark.skipif(GO is None, reason="go not installed")
def test_plugin_uses_go_binary_via_g_pyvauto_bin(tmp_path):
    """With g:pyvauto_bin set, :Pyvauto expands via the compiled Go binary
    (no Python) and produces the grouped AUTOINST output."""
    binpath = tmp_path / "pyvauto_go"
    build = subprocess.run(
        [GO, "build", "-o", str(binpath), "./cmd/pyvauto"],
        cwd=str(REPO / "go"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if build.returncode != 0:
        pytest.skip(f"go build failed: {build.stderr}")

    (tmp_path / "sub.sv").write_text(SUB)
    top = tmp_path / "top.sv"
    top.write_text(TOP)

    script = tmp_path / "run.vim"
    script.write_text(
        f"let g:pyvauto_bin='{binpath}'\n"
        f"source {PLUGIN}\n"
        f"cd {tmp_path}\n"
        "edit top.sv\n"
        "Pyvauto\n"
        "qa!\n"
    )
    _run_vim(script)

    out = top.read_text()
    assert ".clk" in out and ".data_i" in out and ".data_o" in out
    assert "// Outputs" in out  # Go grouped AUTOINST output
