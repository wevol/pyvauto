"""
Fixture 回歸測試 - 將 tests/*.sv 真實檔案接入 CI。

過去這些 .sv 僅供手動驗證、不被 pytest 載入，容易隨程式碼演進而腐爛。
這裡對每個 fixture 執行 expand_all，並驗證「冪等性」：再展開一次的結果
必須與第一次相同（f(f(x)) == f(x)）。此性質不需硬編每個檔案的預期輸出，
即可捕捉解析崩潰與非冪等的展開，且與 CLI 實際索引整個目錄的行為一致。
"""

import sys
from pathlib import Path

import pytest

# 添加專案根目錄到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyvauto import VerilogProject, VerilogExpander

FIXTURE_DIR = Path(__file__).parent
SV_FIXTURES = sorted(FIXTURE_DIR.glob("*.sv"))


@pytest.fixture(scope="module")
def expander() -> VerilogExpander:
    """索引整個 tests/ 目錄的 expander，模擬 CLI 對 cwd 的索引行為。

    用 module scope 只索引一次：expand_all 是純 string→string、不會變動
    project，故可安全地在所有參數化案例間共用，避免每個案例重walk 整個目錄。
    """
    project = VerilogProject()
    project.add_directory(str(FIXTURE_DIR))
    return VerilogExpander(project)


def test_fixtures_present():
    """確保確實有 fixture 被收集到（避免 glob 失誤導致『0 個測試卻全綠』）。"""
    assert SV_FIXTURES, f"在 {FIXTURE_DIR} 找不到任何 .sv fixture"


@pytest.mark.parametrize("sv_path", SV_FIXTURES, ids=lambda p: p.name)
def test_fixture_expansion_is_idempotent(expander, sv_path):
    """每個 .sv fixture 經 expand_all 後應可重複執行而不再變動。"""
    content = sv_path.read_text(encoding="utf-8")
    once = expander.expand_all(content, str(sv_path))
    twice = expander.expand_all(once, str(sv_path))

    assert once == twice, (
        f"{sv_path.name}: expand_all 非冪等\n"
        f"--- once ---\n{once}\n--- twice ---\n{twice}"
    )
