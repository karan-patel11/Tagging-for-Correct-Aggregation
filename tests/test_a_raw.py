"""Offline checks for exploratory setup A_raw (SPEC §15, 2026-11-01). No API calls.

A_raw must be setup A with only the database and its DESCRIBE context changed, and must never
leak into the main A-D setups.
"""
import duckdb
import pytest

import run_eval
from build_raw_views import DROPPED, RAW_DB
from tool_specs import RUN_SQL_SPEC

pytestmark = pytest.mark.skipif(not RAW_DB.exists(), reason="run python src/build_raw_views.py")


def test_a_raw_is_not_a_main_setup():
    assert list(run_eval.SETUPS) == ["A", "B", "C", "D"]
    assert "A_raw" in run_eval.EXPLORATORY and "A_raw" not in run_eval.SETUPS


def test_a_raw_matches_a_except_db_and_context():
    a, raw = run_eval.SETUPS["A"], run_eval.EXPLORATORY["A_raw"]
    assert raw["tools"] == a["tools"] == [RUN_SQL_SPEC]
    assert raw["context"] == "schema_raw.txt" and a["context"] == "schema_only.txt"
    assert run_eval.setup_db("A") == run_eval.DB_PATH
    assert run_eval.setup_db("A_raw") == run_eval.RAW_DB_PATH == RAW_DB
    ba, br = run_eval.system_blocks("A", True), run_eval.system_blocks("A_raw", True)
    assert ba[0] == br[0] and ba[0]["text"] == run_eval.BASE_INSTRUCTIONS
    assert ba[1]["cache_control"] == br[1]["cache_control"]
    assert br[1]["text"].startswith(run_eval.CONTEXT_HEADER)
    assert run_eval.EXPLORATORY_COST_CAP_USD == 2.40


def test_a_raw_run_sql_reads_raw_db_read_only():
    text, err = run_eval.execute_tool("A_raw", "run_sql", {"sql": "SELECT period_basis FROM fundamentals"})
    assert err and "period_basis" in text
    text, err = run_eval.execute_tool("A_raw", "run_sql", {"sql": "SELECT count(*) FROM fundamentals"})
    assert not err
    text, err = run_eval.execute_tool("A_raw", "run_sql", {"sql": "CREATE TABLE x AS SELECT 1"})
    assert err
    text, err = run_eval.execute_tool("A_raw", "run_sql",
                                      {"sql": "SELECT * FROM read_text('eval/questions.yaml')"})
    assert err
    # the main setup still reads the original warehouse
    text, err = run_eval.execute_tool("A", "run_sql", {"sql": "SELECT count(period_basis) FROM fundamentals"})
    assert not err


def test_raw_db_has_no_dropped_columns():
    con = duckdb.connect(str(RAW_DB), read_only=True)
    for table, dropped in DROPPED.items():
        cols = {r[0] for r in con.execute(f'DESCRIBE "{table}"').fetchall()}
        assert not set(dropped) & cols


def test_harness_problem():
    ok = {"error": None, "stop_reason": "end_turn"}
    assert run_eval.harness_problem(ok) is None
    assert run_eval.harness_problem({**ok, "stop_reason": "max_tokens"}) is None
    assert run_eval.harness_problem({**ok, "error": "APIError: x"})
    assert run_eval.harness_problem({**ok, "stop_reason": "tool_turn_limit"})
    assert run_eval.harness_problem({**ok, "stop_reason": None})
