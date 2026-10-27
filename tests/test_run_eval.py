"""Offline checks for eval/run_eval.py (Phase 12): run_sql rules, prompt parity, parsing, pricing.

No API calls.
"""
import json

import yaml

import run_eval
from tool_specs import RUN_SQL_SPEC, TOOL_SPECS


def test_run_sql_caps_rows_at_200():
    text, err = run_eval.run_sql("SELECT * FROM range(500) t(i)")
    lines = text.splitlines()
    assert not err
    assert lines[0] == "i"
    assert len(lines) == 1 + 200 + 1
    assert "truncated" in lines[-1]


def test_run_sql_returns_errors_as_text():
    text, err = run_eval.run_sql("SELECT * FROM no_such_table")
    assert err and text.startswith("ERROR:")


def test_run_sql_is_read_only():
    text, err = run_eval.run_sql("CREATE TABLE x AS SELECT 1")
    assert err and text.startswith("ERROR:")


def test_run_sql_cannot_read_files():
    for sql in ("SELECT * FROM read_text('eval/questions.yaml')",
                "SELECT * FROM read_csv('eval/verification_log.csv')",
                "SET enable_external_access = true"):
        text, err = run_eval.run_sql(sql)
        assert err, sql


def test_run_sql_times_out(monkeypatch):
    monkeypatch.setattr(run_eval, "SQL_TIMEOUT_S", 1)
    text, err = run_eval.run_sql("SELECT count(*) FROM range(100000000000) a")
    assert err and "timed out" in text


def test_tools_come_from_tool_specs():
    assert run_eval.SETUPS["A"]["tools"] == [RUN_SQL_SPEC]
    assert run_eval.SETUPS["B"]["tools"] == [RUN_SQL_SPEC]
    assert run_eval.SETUPS["C"]["tools"] == [RUN_SQL_SPEC]
    assert run_eval.SETUPS["D"]["tools"] is TOOL_SPECS
    assert all(t["name"] != "run_sql" for t in TOOL_SPECS)


def test_base_instructions_identical_and_d_has_no_tag_content():
    blocks = {s: run_eval.system_blocks(s, cache=False) for s in run_eval.SETUPS}
    assert all(b[0]["text"] == run_eval.BASE_INSTRUCTIONS for b in blocks.values())
    assert [len(blocks[s]) for s in "ABCD"] == [2, 2, 2, 1]
    tag_ids = [t["id"] for t in yaml.safe_load((run_eval.ROOT / "tags" / "tags.yaml").read_text())]
    d_text = json.dumps(blocks["D"])
    assert not [t for t in tag_ids if t in d_text]


def test_cache_control_only_when_asked():
    assert "cache_control" in run_eval.system_blocks("C", cache=True)[-1]
    assert all("cache_control" not in b for b in run_eval.system_blocks("A", cache=False))


def test_parse_final():
    line, obj = run_eval.parse_final(
        'Done.\nFINAL: {"answer": 8197000000, "unit": "USD", "warning": false, "refused": false}')
    assert obj == {"answer": 8197000000, "unit": "USD", "warning": False, "refused": False}
    assert run_eval.parse_final("no final here") == (None, None)
    assert run_eval.parse_final('FINAL: {"answer": 1}')[1] is None
    assert run_eval.parse_final("FINAL: not json")[1] is None


def test_call_cost_uses_prompt_length_tier():
    small = {"input_tokens": 10_000, "output_tokens": 0}
    assert abs(run_eval.call_cost(small) - 10_000 * run_eval.PRICES["up_to_100k"]["input"] / 1e6) < 1e-12
    big = {"input_tokens": 50_000, "cache_read_input_tokens": 60_000, "output_tokens": 1000}
    p = run_eval.PRICES["over_100k"]
    want = (50_000 * p["input"] + 60_000 * p["cache_read"] + 1000 * p["output"]) / 1e6
    assert abs(run_eval.call_cost(big) - want) < 1e-12


def test_pilot_questions_span_five_categories():
    qs = {q["id"]: q for q in run_eval.load_questions(run_eval.PILOT_IDS)}
    assert len({q["category"] for q in qs.values()}) == 5
    assert "q003" in qs and "Yum" in qs["q003"]["question"] and "2025" in qs["q003"]["question"]
    assert any(q["expected_behavior"] == "refuse" for q in qs.values())
