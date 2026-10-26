"""Tests for src/semantics.py (SPEC §9.4).

Every expected value comes from tests/expected_values.md (checked by hand against the filings
and source pages). Never compute an expected value from the database or from code, and never
change one to make a test pass.

API under test (SPEC §9.3):
    get_metric(ticker, metric, period)                      metric = fundamentals metric name
    aggregate(metric_id, entities, period, method, denominator_id=None)   metric_id = tag id
Both return the §9.2 envelope (status, value, values, unit, period, explanation, derivation,
sources, use_instead, definitions).
"""
from datetime import date

import pytest

try:
    import semantics
except ModuleNotFoundError as e:
    if e.name != "semantics":
        raise
    semantics = None


@pytest.fixture
def sem():
    if semantics is None:
        pytest.fail("src/semantics.py does not exist yet")
    return semantics


def usd(x):
    return pytest.approx(x, rel=1e-9)


# ---- calls shared with test 11 (every ok result has a source) ----

def t1_yum_total_assets(sem):
    return sem.get_metric("YUM", "total_assets", "FY2025")

def t3_dri_ocf_q3(sem):
    return sem.get_metric("DRI", "op_cash_flow", "FY2025Q3")

def t4_cmg_capex_q4(sem):
    return sem.get_metric("CMG", "capex", "FY2025Q4")

def t5_cmg_eps_fy(sem):
    return sem.get_metric("CMG", "diluted_eps", "FY2025")

def t6_combined_margin(sem):
    return sem.aggregate("derived.operating_margin", ["CMG", "WING"], "FY2025", "ratio_of_sums")

def t7_yum_rollup(sem):
    return sem.aggregate("brand_attention_daily.views", ["YUM"], "CY2025Q1", "rollup_to_parent")

def t9_cpi_pct_change(sem):
    return sem.aggregate("macro.CUSR0000SEFV", [], "2024-12:2025-12", "pct_change")


# expected_values.md, "Test 1 and 2: YUM total assets"
def test_01_yum_fy2025_total_assets_is_q4_balance(sem):
    r = t1_yum_total_assets(sem)
    assert r["status"] == "ok"
    assert r["value"] == usd(8_197_000_000)


# expected_values.md, "Test 1 and 2: YUM total assets"
def test_02_sum_over_time_on_total_assets_rejected(sem):
    r = sem.aggregate("fundamentals.total_assets", ["YUM"], "FY2025", "sum_over_time")
    assert r["status"] == "error"
    assert r["use_instead"] == "last"


# expected_values.md, "Test 3 and 12: DRI operating cash flow" (continuing operations only)
def test_03_dri_q3_ocf_is_ytd9_minus_ytd6(sem):
    r = t3_dri_ocf_q3(sem)
    assert r["status"] == "ok"
    assert r["value"] == usd(588_200_000)
    accessions = sorted(s["accession"] for s in r["sources"])
    assert accessions == ["0000940944-25-000071", "0000940944-26-000009"]


# expected_values.md, "Test 4: CMG capex"
def test_04_cmg_q4_capex_is_fy_minus_ytd9(sem):
    r = t4_cmg_capex_q4(sem)
    assert r["status"] == "ok"
    assert r["value"] > 0
    assert r["value"] == usd(197_455_000)


# expected_values.md, "Test 5: CMG FY2025 diluted EPS"
# Excluded from the eval: the quarter sum (0.28 + 0.32 + 0.29 + 0.25) also equals 1.14,
# so this question cannot tell summing from the reported figure. The semantic test stays.
def test_05_cmg_fy2025_eps_is_reported_annual(sem):
    r = t5_cmg_eps_fy(sem)
    assert r["status"] == "ok"
    assert r["value"] == pytest.approx(1.14, abs=0.01)
    assert [s["accession"] for s in r["sources"]] == ["0001058090-26-000009"]


# expected_values.md, "Test 6: combined FY2025 operating margin, CMG + WING"
def test_06_combined_margin_is_ratio_of_sums(sem):
    r = t6_combined_margin(sem)
    assert r["status"] == "ok"
    assert r["value"] == pytest.approx(16.7565593822, abs=1e-4)

    mean = sem.aggregate("derived.operating_margin", ["CMG", "WING"], "FY2025", "mean_over_time")
    assert mean["status"] == "error"
    assert mean["use_instead"] == "ratio_of_sums"


# expected_values.md, "Test 7: YUM brand rollup, CY2025Q1"
def test_07_yum_rollup_excludes_parent(sem):
    r = t7_yum_rollup(sem)
    assert r["status"] == "ok"
    assert r["value"] == 621380      # four brands, both Habit titles summed
    assert r["value"] != 759382      # trap: parent row included


# expected_values.md, "Test 8: multi-company comps, FY2025 Q1"
def test_08_multi_company_comps_warns_with_definitions(sem):
    r = sem.aggregate("comps_quarterly.comp_sales_pct", ["CMG", "WING"], "FY2025Q1",
                      "sum_across_entities")
    assert r["status"] == "warning"
    assert r["value"] is None
    assert r["values"] == {"CMG": pytest.approx(-0.4), "WING": pytest.approx(0.5)}
    assert r["definitions"]["CMG"]["definition_id"] == "CMG_10K"
    assert r["definitions"]["WING"]["definition_id"] == "WING_10K"
    assert r["definitions"]["CMG"]["definition_text"]
    assert r["definitions"]["WING"]["definition_text"]


# expected_values.md, "Test 9: CPI food away from home"
def test_09_cpi_pct_change_ok_and_sum_rejected(sem):
    r = t9_cpi_pct_change(sem)
    assert r["status"] == "ok"
    assert r["value"] == pytest.approx(4.06919635707, abs=1e-4)

    s = sem.aggregate("macro.CUSR0000SEFV", [], "2024-12:2025-12", "sum_over_time")
    assert s["status"] == "error"


# expected_values.md, "Test 10: missing period"
def test_10_missing_period_is_insufficient_data(sem):
    r = sem.get_metric("CMG", "revenue", "FY2023Q1")
    assert r["status"] == "error"
    assert "insufficient data" in r["explanation"]
    assert r["value"] is None


# expected_values.md, "Test 11: every ok result has at least one source"
@pytest.mark.parametrize("call", [
    t1_yum_total_assets, t3_dri_ocf_q3, t4_cmg_capex_q4, t5_cmg_eps_fy,
    t6_combined_margin, t7_yum_rollup, t9_cpi_pct_change,
])
def test_11_every_ok_result_has_a_source(sem, call):
    r = call(sem)
    assert r["status"] == "ok"
    assert len(r["sources"]) >= 1
    assert all(s.get("url") for s in r["sources"])


# expected_values.md, "Test 3 and 12: DRI operating cash flow" (Test 12 check)
def test_12_dri_fiscal_q3_dates(sem):
    p = t3_dri_ocf_q3(sem)["period"]
    start, end = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
    assert start == date(2024, 11, 25)
    assert end == date(2025, 2, 23)
    for d in (start, end):
        assert date(2024, 11, 15) <= d <= date(2025, 3, 15)
