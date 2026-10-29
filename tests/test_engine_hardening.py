"""Engine hardening after the auto-tag follow-up: aggregate() never computes a method its code path
does not implement, never raises on missing tag metadata, and the validator rules hold.

The matrix calls aggregate() for every measure tag x every method name, on a copy of the tag whose
valid_methods includes that method. Every number that comes back is checked against direct SQL
(not semantics.py)."""
import math
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import semantics  # noqa: E402
import tags  # noqa: E402

MEASURES = sorted(t for t, v in semantics.TAGS.items() if v.semantic_type in tags.MEASURE_TYPES)
METHODS = sorted(tags.VALID_METHOD_NAMES)
ARGS = {"fundamentals": (["CMG"], "FY2025"), "macro_monthly": ([], "2025-01:2025-06"),
        "brand_attention_daily": (["KFC"], "CY2025Q1"), "comps_quarterly": (["CMG"], "FY2025Q1")}
FY_START, FY_END = "2025-01-01", "2025-03-31"


def _sql(q, params=()):
    con = duckdb.connect(str(tags.DB_PATH), read_only=True)
    try:
        return con.execute(q, list(params)).fetchall()
    finally:
        con.close()


def _install(monkeypatch, tag):
    monkeypatch.setitem(semantics.TAGS, tag.id, tag)
    metric = (tag.filter or {}).get("metric")
    if tag.table == "fundamentals" and isinstance(metric, str):
        monkeypatch.setitem(semantics.FUNDAMENTALS, metric, tag)


def _fy(metric, ticker="CMG", basis="FY"):
    rows = _sql("SELECT value FROM fundamentals WHERE ticker = ? AND metric = ? AND fiscal_year = 2025 "
                "AND period_basis = ? AND fiscal_quarter = 4", (ticker, metric, basis))
    assert len(rows) == 1
    return rows[0][0]


def _oracle(tag, method):
    """The expected value of a computation, from direct SQL."""
    if tag.table == "fundamentals":
        metric = tag.filter["metric"]
        if method == "ratio_of_sums":
            num, den = metric if isinstance(metric, list) else (metric, "revenue")
            return _fy(num) / _fy(den) * 100
        if tag.semantic_type == "stock":
            return _fy(metric, basis="instant")
        return _fy(metric)  # one company's FY figure; sum_over_time adds up to it
    if tag.table == "macro_monthly":
        vals = [v for (v,) in _sql("SELECT value FROM macro_monthly WHERE series_id = ? AND date "
                                   "BETWEEN '2025-01-01' AND '2025-06-01' ORDER BY date",
                                   (tag.filter["series_id"],))]
        assert len(vals) == 6
        return {"pct_change": (vals[-1] - vals[0]) / vals[0] * 100, "sum_over_time": sum(vals),
                "mean_over_time": sum(vals) / len(vals)}[method]
    if tag.table == "brand_attention_daily":
        return _sql("SELECT sum(views) FROM brand_attention_daily WHERE brand = 'KFC' "
                    "AND date BETWEEN ? AND ?", (FY_START, FY_END))[0][0]
    raise AssertionError(f"no oracle for {tag.id}")


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("tag_id", MEASURES)
def test_matrix_number_only_for_implemented_methods(monkeypatch, tag_id, method):
    base = semantics.TAGS[tag_id]
    tag = base.model_copy(update={"valid_methods": sorted(set(base.valid_methods) | {method})})
    _install(monkeypatch, tag)
    entities, period = ARGS[tag.table]
    res = semantics.aggregate(tag_id, entities, period, method,
                              denominator_id="fundamentals.revenue")  # never raises
    assert res["status"] in ("ok", "warning", "error")
    if res["status"] == "error":
        assert res["value"] is None
        return
    branch = semantics._branch(tag)
    assert method in semantics.IMPLEMENTED[branch], res
    if method in semantics.REQUIRES:
        field, needed = semantics.REQUIRES[method]
        assert getattr(tag, field) == needed
    expected = _oracle(tag, method)
    assert math.isclose(res["value"], expected, rel_tol=1e-9), (res["value"], expected)


def test_matrix_refuses_the_follow_up_permissive_pairs(monkeypatch):
    # The pairs that returned a number in followup/autotag/RESULTS.md's counterfactual.
    for tid, method in [("brand_attention_daily.views", "mean_over_time"),
                        ("brand_attention_daily.views", "pct_change"),
                        ("macro.CUSR0000SEFV", "last"), ("macro.food_services_sales", "last"),
                        ("fundamentals.revenue", "pct_change"), ("fundamentals.diluted_eps", "pct_change")]:
        base = semantics.TAGS[tid]
        _install(monkeypatch, base.model_copy(update={"valid_methods": base.valid_methods + [method]}))
        entities, period = ARGS[base.table]
        res = semantics.aggregate(tid, entities, period, method)
        assert res["status"] == "error" and res["value"] is None
        assert "is allowed by the tag but not implemented" in res["explanation"], res["explanation"]


def test_stock_sum_over_time_refused(monkeypatch):
    base = semantics.TAGS["fundamentals.total_assets"]
    _install(monkeypatch, base.model_copy(update={"valid_methods": base.valid_methods + ["sum_over_time"]}))
    res = semantics.aggregate("fundamentals.total_assets", ["CMG"], "FY2025", "sum_over_time")
    assert res["status"] == "error"
    assert res["explanation"] == ("method 'sum_over_time' needs additive_over_time = True but "
                                  "fundamentals.total_assets has False; refusing")


# ---------- missing metadata ----------

@pytest.mark.parametrize("update, field", [
    ({"hierarchy": None}, "hierarchy"),
    ({"hierarchy": "brand"}, "hierarchy"),
    ({"hierarchy": "brand -> no_such_column"}, "hierarchy"),
    ({"lineage": {"source": "x"}}, "lineage.url_template"),
    ({"lineage": {"url_template": "https://x/{article_title}/{start_date}"}}, "lineage.url_template"),
])
def test_pageviews_missing_metadata_is_a_clean_error(monkeypatch, update, field):
    tid = "brand_attention_daily.views"
    _install(monkeypatch, semantics.TAGS[tid].model_copy(update=update))
    for method in semantics.TAGS[tid].valid_methods:
        res = semantics.aggregate(tid, ["KFC"], "CY2025Q1", method)
        assert res["status"] == "error" and res["value"] is None
        assert f"tag field {field}" in res["explanation"], res["explanation"]


@pytest.mark.parametrize("tid", ["macro.CUSR0000SEFV", "macro.food_services_sales"])
def test_macro_missing_lineage_url_is_a_clean_error(monkeypatch, tid):
    _install(monkeypatch, semantics.TAGS[tid].model_copy(update={"lineage": {"source": "x"}}))
    for method in semantics.TAGS[tid].valid_methods:
        res = semantics.aggregate(tid, [], "2025-01:2025-06", method)
        assert res["status"] == "error" and res["value"] is None
        assert res["explanation"] == f"{tid}: tag field lineage.url is missing; refusing"


def test_fundamentals_missing_filter_is_a_clean_error(monkeypatch):
    tid = "fundamentals.revenue"
    _install(monkeypatch, semantics.TAGS[tid].model_copy(update={"filter": None}))
    for method in ("sum_over_time", "sum_across_entities", "ratio_of_sums"):
        res = semantics.aggregate(tid, ["CMG"], "FY2025", method, denominator_id="fundamentals.revenue")
        assert res["status"] == "error" and res["value"] is None


# ---------- validator rules (src/tags.py check_semantic_rules) ----------

def test_hand_tags_pass_every_rule():
    assert tags.check_semantic_rules(tags.load_tags()) == []


def _hand(tid):
    return {t.id: t for t in tags.load_tags()}[tid]


@pytest.mark.parametrize("tid, update, expect", [
    ("fundamentals.revenue", {"additive_over_time": False, "time_rollup": "reported_fy_value",
                              "valid_methods": ["sum_across_entities"]},
     "a flow needs additive_over_time true and time_rollup sum"),
    ("fundamentals.total_assets", {"valid_methods": ["last", "sum_over_time"]},
     "sum_over_time in valid_methods needs additive_over_time true"),
    ("fundamentals.diluted_eps", {"valid_methods": ["sum_across_entities"]},
     "sum_across_entities in valid_methods needs additive_over_entities true"),
    ("brand_attention_daily.views", {"hierarchy": None, "valid_methods": ["sum_over_time"]},
     "so the measure needs a hierarchy"),
    ("macro.CUSR0000SEFV", {"lineage": {"source": "x"}}, "needs lineage.url"),
    ("brand_attention_daily.views", {"lineage": {"source": "x"}}, "needs lineage.url_template"),
])
def test_each_rule_has_a_failing_fixture(tid, update, expect):
    bad = _hand(tid).model_copy(update=update)
    problems = tags.check_semantic_rules([bad])
    assert len(problems) == 1 and problems[0].startswith(tid) and expect in problems[0], problems
