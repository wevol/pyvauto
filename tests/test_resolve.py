import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyvauto import VerilogProject


def _write(d, name, body):
    p = os.path.join(str(d), name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


def test_resolve_filename_fast_path_skips_unneeded(tmp_path):
    # foo.v defines foo; bar.v defines bar (a decoy we must NOT parse).
    _write(tmp_path, "foo.v", "module foo(input a, output b); endmodule\n")
    _write(tmp_path, "bar.v", "module bar(input c); endmodule\n")

    project = VerilogProject()
    project.resolve(str(tmp_path), {"foo"})

    assert "foo" in project.modules
    assert "bar" not in project.modules  # decoy never parsed


def test_resolve_multi_module_file_resolves_all(tmp_path):
    # One file defines two needed modules; one parse satisfies both.
    _write(tmp_path, "pair.sv",
           "module a(input x); endmodule\nmodule b(output y); endmodule\n")
    _write(tmp_path, "c.v", "module c(input z); endmodule\n")  # decoy

    project = VerilogProject()
    project.resolve(str(tmp_path), {"a", "b"})

    assert "a" in project.modules
    assert "b" in project.modules
    assert "c" not in project.modules


def test_resolve_name_differs_from_basename_via_fallback(tmp_path):
    # widget lives in stuff.v — no widget.v, so fast-path misses.
    _write(tmp_path, "stuff.v", "module widget(input a); endmodule\n")

    project = VerilogProject()
    project.resolve(str(tmp_path), {"widget"})

    assert "widget" in project.modules


def test_resolve_fallback_tolerates_nonspace_whitespace(tmp_path):
    # Module declared with a tab/newline after `module`, in a file whose name
    # differs from the module — forces the fallback's pre-filter. A literal
    # "module <name>" space check would miss these; the parser would not.
    _write(tmp_path, "tabbed.v", "module\twidget(input a); endmodule\n")
    _write(tmp_path, "newlined.v", "module\ngadget(input b); endmodule\n")

    project = VerilogProject()
    project.resolve(str(tmp_path), {"widget", "gadget"})

    assert "widget" in project.modules
    assert "gadget" in project.modules


def test_resolve_undefined_module_degrades_without_error(tmp_path):
    _write(tmp_path, "foo.v", "module foo(input a); endmodule\n")

    project = VerilogProject()
    project.resolve(str(tmp_path), {"nonexistent"})  # must not raise

    assert "nonexistent" not in project.modules


def test_resolve_empty_needed_parses_nothing(tmp_path):
    _write(tmp_path, "foo.v", "module foo(input a); endmodule\n")

    project = VerilogProject()
    project.resolve(str(tmp_path), set())

    assert project.modules == {}


PYVAUTO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyvauto.py"
)


def test_cli_resolves_submodule_from_sibling_file(tmp_path):
    # Sub-module in its own file; top instantiates it with /*AUTOINST*/.
    _write(tmp_path, "sub.v",
           "module sub(input clk, output done); endmodule\n")
    top = _write(
        tmp_path,
        "top.v",
        "module top;\n"
        "  sub u_sub (/*AUTOINST*/);\n"
        "endmodule\n",
    )
    # Decoy file that must not be needed to expand top.
    _write(tmp_path, "unused.v", "module unused(input q); endmodule\n")

    result = subprocess.run(
        [sys.executable, PYVAUTO, "top.v"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    with open(top, encoding="utf-8") as f:
        expanded = f.read()
    assert ".clk" in expanded and ".done" in expanded   # AUTOINST filled in
    assert "unused" not in result.stdout                  # decoy not parsed


def test_resolve_searches_multiple_roots(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    c = tmp_path / "c"
    for d in (a, b, c):
        d.mkdir()
    _write(b, "sub.v", "module sub(input clk); endmodule\n")
    _write(c, "decoy.v", "module decoy(input x); endmodule\n")

    project = VerilogProject()
    project.resolve([str(a), str(b)], {"sub"})

    assert "sub" in project.modules
    assert "decoy" not in project.modules  # c not among the roots


def test_cli_resolves_submodule_from_file_directory_outside_cwd(tmp_path):
    proj = tmp_path / "proj"
    other = tmp_path / "other"
    proj.mkdir()
    other.mkdir()
    _write(proj, "sub.v", "module sub(input clk, output done); endmodule\n")
    top = _write(proj, "top.sv", "module top;\n  sub u (/*AUTOINST*/);\nendmodule\n")

    result = subprocess.run(
        [sys.executable, PYVAUTO, str(top)],
        cwd=str(other),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with open(top, encoding="utf-8") as f:
        expanded = f.read()
    assert ".clk" in expanded and ".done" in expanded


def test_cli_incdir_finds_submodule(tmp_path):
    proj = tmp_path / "proj"
    lib = tmp_path / "lib"
    other = tmp_path / "other"
    for d in (proj, lib, other):
        d.mkdir()
    _write(lib, "sub.v", "module sub(input clk, output done); endmodule\n")
    top = _write(proj, "top.sv", "module top;\n  sub u (/*AUTOINST*/);\nendmodule\n")

    subprocess.run(
        [sys.executable, PYVAUTO, str(top)],
        cwd=str(other), capture_output=True, text=True,
    )
    with open(top, encoding="utf-8") as f:
        assert ".clk" not in f.read()

    result = subprocess.run(
        [sys.executable, PYVAUTO, "--incdir", str(lib), str(top)],
        cwd=str(other), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    with open(top, encoding="utf-8") as f:
        assert ".clk" in f.read()
