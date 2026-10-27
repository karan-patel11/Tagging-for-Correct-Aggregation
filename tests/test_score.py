"""Scoring rules in eval/score.py (Phase 13). Synthetic runs; no API calls, no result files."""
import json

import pytest

import yaml

import run_eval
import score

QS = {q["id"]: q for q in yaml.safe_load(score.QUESTIONS.read_text())}


def run(qid, answer, unit, warning=False, refused=False, setup="A", n=1, parsed=True):
    final = {"answer": answer, "unit": unit, "warning": warning, "refused": refused}
    return {"question_id": qid, "setup": setup, "run": n, "parsed": parsed,
            "final": final if parsed else None, "final_line": "FINAL: ..." if parsed else None,
            "tool_calls": [], "tokens": {}, "cost_usd": 0.0}


def s(rec):
    return score.score_run(rec, QS[rec["question_id"]])


def test_tolerance_kinds_follow_spec():
    assert score.tolerance_kind(QS["q018"]) == "index_pct_change"   # CPI percent change
    assert score.tolerance_kind(QS["q007"]) == "percent"            # operating margin
    assert score.tolerance_kind(QS["q032"]) == "percent"            # percentage points
    assert score.tolerance_kind(QS["q022"]) == "USD"                # USD millions
    assert score.tolerance_kind(QS["q020"]) == "index_points"
    assert score.tolerance(QS["q003"]) == 0.005 * QS["q003"]["correct"]


def test_answer_within_tolerance_is_correct():
    c = QS["q003"]["correct"]
    assert s(run("q003", c * 1.004, "USD"))["correct"]
    assert not s(run("q003", c * 1.006, "USD"))["correct"]


def test_scale_words_convert_to_base_units():
    r = s(run("q003", 8.197, "USD billions"))
    assert r["correct"] and r["scaled"] and r["value"] == pytest.approx(8.197e9)
    r = s(run("q016", 588.2, "USD millions"))
    assert r["correct"] and r["scaled"]
    r = s(run("q016", 588200, "thousands of USD"))
    assert r["correct"] and r["scaled"]


def test_scale_relative_to_question_unit():
    c = QS["q022"]["correct"]                       # a USD millions question
    assert not s(run("q022", c, "USD millions"))["scaled"]
    assert s(run("q022", c, "USD millions"))["correct"]
    r = s(run("q022", c / 1000, "USD billions"))
    assert r["scaled"] and r["correct"]


def test_unscaled_wrong_magnitude_is_wrong():
    assert not s(run("q016", 588.2, "USD"))["correct"]


def test_answer_behavior():
    c = QS["q003"]["correct"]
    assert not s(run("q003", c, "USD", refused=True))["correct"]
    r = s(run("q003", c, "USD", warning=True))
    assert r["correct"] and r["over_warning"]


def test_answer_with_warning_behavior():
    c = QS["q032"]["correct"]
    assert s(run("q032", c, "percentage_points", warning=True))["correct"]
    assert not s(run("q032", c, "percentage_points", warning=False))["correct"]
    assert not s(run("q032", None, "percentage_points", warning=True, refused=True))["correct"]


def test_refuse_behavior():
    assert s(run("q038", None, "percent", refused=True))["correct"]
    assert not s(run("q038", 3.1, "percent", refused=True))["correct"]
    assert not s(run("q038", None, "percent", refused=False))["correct"]


def test_trap_hit_recorded():
    traps = QS["q003"]["trap_answers"]
    r = s(run("q003", traps["sum_of_4_quarter_ends"], "USD"))
    assert not r["correct"] and r["trap_hit"] == "sum_of_4_quarter_ends"
    r = s(run("q016", QS["q016"]["trap_answers"]["used_ytd9_value"] / 1e6, "USD millions"))
    assert r["trap_hit"] == "used_ytd9_value"


def test_unparsed_is_incorrect_and_listed():
    rows = [s(run("q003", None, None, parsed=False))]
    assert not rows[0]["correct"]
    summary = score.summarize(rows, [], QS)
    assert summary["setups"]["A"]["unparsed"] == ["q003 run 1"]


def test_last_duplicate_line_counts(tmp_path):
    c = QS["q003"]["correct"]
    lines = {"A": [run("q003", 1, "USD"), run("q003", c, "USD")]}
    for setup in score.SETUPS:
        (tmp_path / f"{setup}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines.get(setup, [])))
    runs, dupes = score.load_runs(tmp_path)
    assert dupes == 1 and runs[("q003", "A", 1)]["final"]["answer"] == c


def test_resume_skips_completed_runs_only(tmp_path):
    p = tmp_path / "A.jsonl"
    ok = {"question_id": "q003", "setup": "A", "run": 1, "error": None, "cost_usd": 0.001}
    bad = {"question_id": "q003", "setup": "A", "run": 2, "error": "APIConnectionError: x", "cost_usd": 0.0005}
    p.write_text(json.dumps(ok) + "\n" + json.dumps(bad) + "\n" + '{"question_id": "q00')
    done, spent = run_eval.completed_runs([p, tmp_path / "missing.jsonl"])
    assert done == {("q003", "A", 1)}
    assert abs(spent - 0.0015) < 1e-12


def test_pilot_writes_to_pilot_dir():
    src = (score.ROOT / "eval" / "run_eval.py").read_text()
    assert 'RESULTS / "pilot" if args.pilot else RESULTS' in src
