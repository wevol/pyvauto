"""
CLI entry-point tests — actually run `python pyvauto.py <file>` via subprocess.

Verify main()'s in-place expansion, multi-file handling, the Skip message for a
missing file, and idempotency. These paths (argparse, directory scanning,
writing files back) used to be verified only by hand, not in CI.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "pyvauto.py"

SUB = "module sub (input clk, input [7:0] data_i, output [7:0] data_o);\nendmodule\n"
TOP = "module top;\n    sub u_sub (\n        /*AUTOINST*/\n    );\nendmodule\n"


def _run(args, cwd):
    """Run pyvauto.py with the given cwd (the target file's directory is searched for module definitions)."""
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


def test_cli_delete_reverses_expansion(tmp_path):
    (tmp_path / "sub.sv").write_text(SUB)
    top = tmp_path / "top.sv"
    top.write_text(TOP)

    _run(["top.sv"], tmp_path)  # expand first
    assert ".clk" in top.read_text()

    r = _run(["--delete", "top.sv"], tmp_path)  # un-expand

    assert r.returncode == 0, r.stderr
    out = top.read_text()
    assert "/*AUTOINST*/" in out
    assert ".clk" not in out and ".data_o" not in out


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
