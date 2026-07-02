"""
Standalone execution test — verify pyvauto.py works without any external module.

This test would fail (RED) while pyvauto.py still depended on parser.py.
Once the merge was done, it passes (GREEN).
"""

import sys
import os
from pathlib import Path
import importlib.util


def test_pyvauto_is_standalone():
    """
    pyvauto.py must work on its own, without depending on parser.py.

    This test would fail (RED) while pyvauto.py had, at line 8:
    from parser import VerilogModule, RegexVerilogParser
    """
    project_root = Path(__file__).parent.parent
    pyvauto_path = project_root / "pyvauto.py"

    # Read pyvauto.py's content
    with open(pyvauto_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify: there must be no "from parser import" statement
    assert "from parser import" not in content, (
        "pyvauto.py still depends on parser.py. "
        "This test is expected to fail (RED) until the merge is done."
    )

    # Further: all required classes must be defined inside pyvauto.py
    assert "class VerilogPort:" in content, (
        "VerilogPort class should be defined in pyvauto.py"
    )
    assert "class VerilogModule:" in content, (
        "VerilogModule class should be defined in pyvauto.py"
    )
    assert "class RegexVerilogParser:" in content, (
        "RegexVerilogParser class should be defined in pyvauto.py"
    )


def test_pyvauto_imports_only_stdlib():
    """
    pyvauto.py must import only the standard library.
    """
    project_root = Path(__file__).parent.parent
    pyvauto_path = project_root / "pyvauto.py"

    with open(pyvauto_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Standard-library module allow-list
    stdlib_modules = {"re", "os", "sys", "argparse", "traceback", "typing"}

    # Extract all import statements
    import_lines = [
        line.strip()
        for line in content.split("\n")
        if line.strip().startswith(("import ", "from "))
    ]

    for line in import_lines:
        # Skip trailing comments
        if "#" in line:
            line = line.split("#")[0].strip()

        # Parse "import xxx" or "from xxx import ..."
        if line.startswith("from "):
            module = line.split()[1]
        else:
            module = line.split()[1].split(".")[0]

        # Verify only stdlib or builtins are used
        assert module in stdlib_modules or module.startswith("__"), (
            f"Found a non-stdlib import: {module}. pyvauto.py should use only the standard library."
        )
