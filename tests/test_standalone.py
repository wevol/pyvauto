"""
測試單一檔案執行 - 驗證 pyautocomplete.py 無需外部模組即可運作

這個測試會失敗 (RED)，因為目前 pyautocomplete.py 依賴 parser.py。
當我們完成合併後，這個測試應該會通過 (GREEN)。
"""

import sys
import os
from pathlib import Path
import importlib.util


def test_pyautocomplete_is_standalone():
    """
    測試 pyautocomplete.py 可以單獨運作，不依賴 parser.py

    這個測試目前應該失敗 (RED)，因為 pyautocomplete.py
    在第 8 行: from parser import VerilogModule, RegexVerilogParser
    """
    project_root = Path(__file__).parent.parent
    pyautocomplete_path = project_root / "pyautocomplete.py"

    # 讀取 pyautocomplete.py 的內容
    with open(pyautocomplete_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 驗證：不應該有 "from parser import" 這樣的語句
    assert "from parser import" not in content, (
        "pyautocomplete.py 仍然依賴 parser.py。"
        "這個測試預期會失敗 (RED)，直到我們完成合併。"
    )

    # 進一步驗證：所有必要的類別都應該在 pyautocomplete.py 內部定義
    assert "class VerilogPort:" in content, (
        "VerilogPort 類別應該在 pyautocomplete.py 中定義"
    )
    assert "class VerilogModule:" in content, (
        "VerilogModule 類別應該在 pyautocomplete.py 中定義"
    )
    assert "class RegexVerilogParser:" in content, (
        "RegexVerilogParser 類別應該在 pyautocomplete.py 中定義"
    )


def test_pyautocomplete_imports_only_stdlib():
    """
    測試 pyautocomplete.py 只使用標準庫
    """
    project_root = Path(__file__).parent.parent
    pyautocomplete_path = project_root / "pyautocomplete.py"

    with open(pyautocomplete_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 標準庫模組列表
    stdlib_modules = {"re", "os", "sys", "argparse", "traceback", "typing"}

    # 提取所有 import 語句
    import_lines = [
        line.strip()
        for line in content.split("\n")
        if line.strip().startswith(("import ", "from "))
    ]

    for line in import_lines:
        # 跳過註解
        if "#" in line:
            line = line.split("#")[0].strip()

        # 解析 "import xxx" 或 "from xxx import ..."
        if line.startswith("from "):
            module = line.split()[1]
        else:
            module = line.split()[1].split(".")[0]

        # 驗證只使用標準庫或內建型別
        assert module in stdlib_modules or module.startswith("__"), (
            f"發現非標準庫引用: {module}。pyautocomplete.py 應該只使用標準庫。"
        )
