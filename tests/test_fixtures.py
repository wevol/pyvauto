"""
Fixture regression tests — wire the real tests/*.sv files into CI.

These .sv files used to be for manual verification only, not loaded by pytest,
so they rotted easily as the code evolved. Here we run expand_all on each
fixture and verify idempotency: expanding a second time must equal the first
(f(f(x)) == f(x)). This property needs no hardcoded expected output per file,
yet catches parse crashes and non-idempotent expansions, and matches the CLI's
behavior of indexing the whole directory.
"""

import sys
from pathlib import Path

import pytest

# Add the project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyvauto import VerilogProject, VerilogExpander

FIXTURE_DIR = Path(__file__).parent
SV_FIXTURES = sorted(FIXTURE_DIR.glob("*.sv"))


@pytest.fixture(scope="module")
def expander() -> VerilogExpander:
    """An expander that indexes the whole tests/ directory, mimicking the CLI's
    cwd indexing.

    Module scope indexes only once: expand_all is a pure string->string that
    never mutates the project, so it is safe to share across all parametrized
    cases and avoids re-walking the whole directory per case.
    """
    project = VerilogProject()
    project.add_directory(str(FIXTURE_DIR))
    return VerilogExpander(project)


def test_fixtures_present():
    """Ensure fixtures were actually collected (avoid a glob slip that yields '0 tests but all green')."""
    assert SV_FIXTURES, f"No .sv fixture found in {FIXTURE_DIR}"


@pytest.mark.parametrize("sv_path", SV_FIXTURES, ids=lambda p: p.name)
def test_fixture_expansion_is_idempotent(expander, sv_path):
    """Each .sv fixture must be unchanged when expand_all is run again."""
    content = sv_path.read_text(encoding="utf-8")
    once = expander.expand_all(content, str(sv_path))
    twice = expander.expand_all(once, str(sv_path))

    assert once == twice, (
        f"{sv_path.name}: expand_all is not idempotent\n"
        f"--- once ---\n{once}\n--- twice ---\n{twice}"
    )
