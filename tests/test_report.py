"""Checks for the report helpers (report/analyze_over_warnings.py, report/build_key.py)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "report"))

import analyze_over_warnings as aow  # noqa: E402
import build_key  # noqa: E402


def test_keyword_pattern_matches_filing_metadata_sentence():
    text = "The total is 588.2M.\nCaveat: the six-month row has a filing date in 2026. FINAL: {}"
    sentence, word = aow.matched_sentence(text)
    assert word.lower() == "filing date"
    assert sentence.startswith("Caveat:")


def test_keyword_pattern_ignores_unit_assumption_caveat():
    assert aow.matched_sentence("The table has no unit metadata, so I assumed millions.") == (None, None)


def test_over_warning_counts_match_summary():
    data = json.loads((ROOT / "report" / "over_warning_reasons.json").read_text())
    summary = json.loads((ROOT / "eval" / "results" / "summary.json").read_text())
    for s, v in data["setups"].items():
        assert v["warning_runs"] == summary["setups"][s]["over_warning_runs"]
        assert v["matched"] + v["unmatched"] == v["warning_runs"]


def test_key_expands_id_ranges():
    assert build_key.mentioned_ids("see q022–q024 and q030") == {"q022", "q023", "q024", "q030"}
