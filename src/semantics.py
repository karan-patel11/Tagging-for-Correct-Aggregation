"""Aggregation rules for the warehouse (SPEC §9). The only place these rules live.

Rules come from tags/tags.yaml at import time (additivity, valid methods, time rollup, units,
lineage); nothing here is hardcoded per metric. The database is opened read-only.

Every public function returns the §9.2 envelope.
"""
import re
from datetime import date, timedelta
from pathlib import Path

import duckdb

from tags import load_tags

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"

TAGS = {t.id: t for t in load_tags()}
# Short fundamentals metric name -> tag (single-value filters only; derived tags use a list).
FUNDAMENTALS = {t.filter["metric"]: t for t in TAGS.values()
                if t.table == "fundamentals" and isinstance((t.filter or {}).get("metric"), str)}
MEASURES = {"flow", "stock", "ratio", "per_share", "index", "count"}

# Cumulative piece for each fiscal quarter: Q2 = YTD6 - Q1, Q3 = YTD9 - YTD6, Q4 = FY - YTD9.
CUMULATIVE = {1: "Q", 2: "YTD6", 3: "YTD9", 4: "FY"}
# The method a tag's time_rollup corresponds to, used for use_instead.
ROLLUP_METHOD = {"sum": "sum_over_time", "last": "last", "mean": "mean_over_time"}

_con = None


def _db():
    global _con
    if _con is None:
        _con = duckdb.connect(str(DB_PATH), read_only=True)
    return _con


def _rows(sql, params=()):
    cur = _db().execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------- envelope ----------

def _envelope(status, value=None, values=None, unit=None, period=None, explanation="",
              derivation=None, sources=None, use_instead=None, definitions=None):
    return {"status": status, "value": value, "values": values, "unit": unit, "period": period,
            "explanation": explanation, "derivation": derivation or [], "sources": sources or [],
            "use_instead": use_instead, "definitions": definitions}


def _error(explanation, **kw):
    return _envelope("error", explanation=explanation, **kw)


def _insufficient(detail, **kw):
    return _error(f"insufficient data: {detail}", **kw)


def _iso(d):
    return d.isoformat() if d is not None else None


# ---------- periods (§9.1) ----------

def _parse_period(period):
    if m := re.fullmatch(r"FY(\d{4})", period):
        return {"kind": "FY", "year": int(m[1]), "quarter": 4}
    if m := re.fullmatch(r"FY(\d{4})Q([1-4])", period):
        return {"kind": "FQ", "year": int(m[1]), "quarter": int(m[2])}
    if m := re.fullmatch(r"CY(\d{4})Q([1-4])", period):
        y, q = int(m[1]), int(m[2])
        start = date(y, 3 * q - 2, 1)
        end = date(y + (q == 4), (3 * q) % 12 + 1, 1) - timedelta(days=1)
        return {"kind": "CQ", "start": start, "end": end}
    if m := re.fullmatch(r"(\d{4})-(\d{2}):(\d{4})-(\d{2})", period):
        start, end = date(int(m[1]), int(m[2]), 1), date(int(m[3]), int(m[4]), 1)
        if end < start:
            return None
        return {"kind": "MR", "start": start, "end": end}
    return None


def _months(start, end):
    out, d = [], start
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


# ---------- sources ----------

def _sec_source(row):
    cik = str(int(row["cik"]))
    return {"type": "sec_filing", "accession": row["accession"], "form": row["form"],
            "period_basis": row["period_basis"], "period_start": _iso(row["period_start"]),
            "period_end": _iso(row["period_end"]),
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{row['accession'].replace('-', '')}/"}


# ---------- fundamentals ----------

def _fiscal_rows(ticker, metric, year):
    return _rows("SELECT * FROM fundamentals WHERE ticker = ? AND metric = ? AND fiscal_year = ?",
                 (ticker, metric, year))


def _one(rows, basis, quarter):
    hits = [r for r in rows if r["period_basis"] == basis and r["fiscal_quarter"] == quarter]
    return hits[0] if len(hits) == 1 else None


def _fundamental(ticker, metric, p, label):
    """One company, one fiscal period, for a stored fundamentals metric."""
    tag = FUNDAMENTALS[metric]
    unit = tag.unit
    rows = _fiscal_rows(ticker, metric, p["year"])
    q = p["quarter"]

    if tag.semantic_type == "stock":
        r = _one(rows, "instant", q)
        if r is None:
            return _insufficient(f"no {metric} balance for {ticker} {label}", unit=unit)
        return _envelope("ok", r["value"], unit=unit,
                         period={"label": label, "start": None, "end": _iso(r["period_end"])},
                         explanation=f"Balance at the period end ({r['period_end']}).",
                         derivation=[f"{metric} at {r['period_end']} = {r['value']}"],
                         sources=[_sec_source(r)])

    if p["kind"] == "FY" or tag.time_rollup == "reported_fy_value":
        # Full years are the reported FY figure; per-share quarters are never derived.
        basis = "FY" if p["kind"] == "FY" else "Q"
        r = _one(rows, basis, q)
        if r is None:
            return _insufficient(f"no reported {basis} {metric} for {ticker} {label}", unit=unit)
        return _envelope("ok", r["value"], unit=unit,
                         period={"label": label, "start": _iso(r["period_start"]),
                                 "end": _iso(r["period_end"])},
                         explanation=f"Reported {basis} value as filed.",
                         derivation=[f"{basis} = {r['value']}"], sources=[_sec_source(r)])

    # A reported single quarter is used as is.
    r = _one(rows, "Q", q)
    if r is not None:
        return _envelope("ok", r["value"], unit=unit,
                         period={"label": label, "start": _iso(r["period_start"]),
                                 "end": _iso(r["period_end"])},
                         explanation="Reported single quarter as filed.",
                         derivation=[f"Q{q} = {r['value']}"], sources=[_sec_source(r)])

    if not tag.derivation:
        return _insufficient(f"no single-quarter {metric} for {ticker} {label}", unit=unit)
    later = _one(rows, CUMULATIVE[q], q)
    earlier = _one(rows, CUMULATIVE[q - 1], q - 1) if q > 1 else None
    if later is None or earlier is None:
        return _insufficient(f"missing a piece to derive {ticker} {label} {metric} "
                             f"({CUMULATIVE[q]} - {CUMULATIVE.get(q - 1)})", unit=unit)
    start = earlier["period_end"] + timedelta(days=1)
    lined_up = (later["fiscal_year"] == earlier["fiscal_year"] == p["year"]
                and later["period_start"] == earlier["period_start"]
                and later["period_end"] > earlier["period_end"]
                and 80 <= (later["period_end"] - start).days + 1 <= 100)
    if not lined_up:
        return _insufficient(f"pieces for {ticker} {label} {metric} do not line up "
                             f"({earlier['period_start']}..{earlier['period_end']} and "
                             f"{later['period_start']}..{later['period_end']})", unit=unit)
    value = later["value"] - earlier["value"]
    lb, eb = later["period_basis"], earlier["period_basis"]
    return _envelope("ok", value, unit=unit,
                     period={"label": label, "start": _iso(start), "end": _iso(later["period_end"])},
                     explanation=f"Derived as {lb} minus {eb}.",
                     derivation=[f"{lb} ({later['period_start']}..{later['period_end']}) = {later['value']}",
                                 f"{eb} ({earlier['period_start']}..{earlier['period_end']}) = {earlier['value']}",
                                 f"Q{q} = {lb} - {eb} = {value}"],
                     sources=[_sec_source(later), _sec_source(earlier)])


def get_metric(ticker, metric, period):
    """One company, one fiscal period (FY2025 or FY2025Q3) for a fundamentals metric."""
    if metric not in FUNDAMENTALS:
        return _error(f"unknown metric '{metric}'; get_metric covers {sorted(FUNDAMENTALS)}")
    p = _parse_period(period)
    if p is None or p["kind"] not in ("FY", "FQ"):
        return _error(f"get_metric needs a fiscal period like FY2025 or FY2025Q3, got '{period}'")
    return _fundamental(ticker, metric, p, period)


def _fye_month(ticker):
    rows = _rows("SELECT DISTINCT month(period_end) AS m FROM fundamentals "
                 "WHERE ticker = ? AND period_basis = 'FY'", (ticker,))
    months = {r["m"] for r in rows}
    return months.pop() if len(months) == 1 else None


# ---------- list / describe ----------

def list_metrics():
    metrics = {tid: t.description for tid, t in TAGS.items() if t.semantic_type in MEASURES}
    return _envelope("ok", values=metrics, explanation=f"{len(metrics)} metrics.",
                     sources=[{"type": "tags", "url": "tags/tags.yaml"}])


def describe_column(metric_id):
    tag = TAGS.get(metric_id)
    if tag is None:
        return _error(f"unknown metric '{metric_id}'")
    definitions = None
    if tag.comparability == "by_definition_id":
        definitions = {r["ticker"]: {"definition_id": r["definition_id"],
                                     "definition_text": r["definition_text"],
                                     "source_url": r["source_url"]}
                       for r in _rows("SELECT * FROM comps_definitions ORDER BY ticker")}
    return _envelope("ok", values=tag.model_dump(), unit=tag.unit, explanation=tag.description,
                     sources=[{"type": "tags", "url": "tags/tags.yaml"}], definitions=definitions)


# ---------- aggregate ----------

def _use_instead(tag, method):
    """The allowed method that fits the tag's own rollup rule, if any."""
    candidates = [ROLLUP_METHOD.get(tag.time_rollup)]
    if tag.semantic_type == "ratio":
        candidates.insert(0, "ratio_of_sums")
    for c in candidates:
        if c and c in tag.valid_methods and c != method:
            return c
    return None


def _comps_warning(tag, entities, p, label):
    if p is None or p["kind"] != "FQ":
        return _error(f"comps need a fiscal quarter like FY2025Q1, got '{label}'", unit=tag.unit)
    marks = ",".join("?" * len(entities))
    rows = _rows(f"SELECT q.*, d.definition_text FROM comps_quarterly q "
                 f"JOIN comps_definitions d USING (definition_id) "
                 f"WHERE q.ticker IN ({marks}) AND q.fiscal_year = ? AND q.fiscal_quarter = ?",
                 (*entities, p["year"], p["quarter"]))
    found = {r["ticker"] for r in rows}
    missing = [e for e in entities if e not in found]
    if missing:
        return _insufficient(f"no comps for {missing} in {label}", unit=tag.unit)
    return _envelope(
        "warning", None, values={r["ticker"]: r["comp_sales_pct"] for r in rows}, unit=tag.unit,
        period={"label": label, "start": None, "end": None},
        explanation="Comparable sales measures differ by company (see definitions); "
                    "no combined value is computed.",
        sources=[{"type": "earnings_release", "ticker": r["ticker"], "url": r["source_url"]}
                 for r in rows],
        definitions={r["ticker"]: {"definition_id": r["definition_id"],
                                   "definition_text": r["definition_text"]} for r in rows})


def _fundamental_quarters_sum(ticker, metric, p, label):
    """sum_over_time for a fundamentals flow: derive discrete quarters, then sum."""
    quarters = [p["quarter"]] if p["kind"] == "FQ" else [1, 2, 3, 4]
    parts = [_fundamental(ticker, metric, {"kind": "FQ", "year": p["year"], "quarter": q},
                          f"FY{p['year']}Q{q}") for q in quarters]
    bad = next((r for r in parts if r["status"] != "ok"), None)
    if bad:
        return bad
    return _envelope("ok", sum(r["value"] for r in parts), unit=FUNDAMENTALS[metric].unit,
                     period={"label": label, "start": parts[0]["period"]["start"],
                             "end": parts[-1]["period"]["end"]},
                     explanation="Sum of discrete quarters.",
                     derivation=[f"{r['period']['label']} = {r['value']}" for r in parts],
                     sources=[s for r in parts for s in r["sources"]])


def _macro(tag, method, p, label):
    if p is None or p["kind"] not in ("MR", "CQ"):
        return _error(f"macro series need a month range like 2025-01:2025-12 or a calendar "
                      f"quarter like CY2025Q1, got '{label}'", unit=tag.unit)
    series = tag.filter["series_id"]
    months = _months(p["start"].replace(day=1), p["end"].replace(day=1))
    rows = {r["date"]: r for r in _rows(
        "SELECT * FROM macro_monthly WHERE series_id = ? AND date BETWEEN ? AND ?",
        (series, months[0], months[-1]))}
    if not tag.lineage.get("url"):
        return _error(f"{tag.id} lineage has no url")
    sources = [{"type": "macro_series", "series_id": series, "url": tag.lineage["url"],
                "retrieved_on": tag.lineage.get("retrieved_on")}]
    period = {"label": label, "start": _iso(months[0]), "end": _iso(months[-1])}

    if method == "pct_change":
        a, b = rows.get(months[0]), rows.get(months[-1])
        if a is None or b is None:
            return _insufficient(f"{series} has no value for "
                                 f"{months[0] if a is None else months[-1]:%Y-%m}", unit="percent")
        value = (b["value"] - a["value"]) / a["value"] * 100
        return _envelope("ok", value, unit="percent", period=period,
                         explanation="Percent change from the first to the last month.",
                         derivation=[f"{months[0]:%Y-%m} = {a['value']}", f"{months[-1]:%Y-%m} = {b['value']}",
                                     f"({b['value']} - {a['value']}) / {a['value']} * 100 = {value}"],
                         sources=sources)

    missing = [m for m in months if m not in rows]
    if missing:
        return _insufficient(f"{series} has no value for {[f'{m:%Y-%m}' for m in missing]}",
                             unit=tag.unit)
    vals = [rows[m]["value"] for m in months]
    value = sum(vals) if method == "sum_over_time" else sum(vals) / len(vals)
    return _envelope("ok", value, unit=tag.unit, period=period,
                     explanation=("Sum" if method == "sum_over_time" else "Mean") + " of monthly values.",
                     derivation=[f"{m:%Y-%m} = {rows[m]['value']}" for m in months], sources=sources)


def _views(tag, method, entities, p, label):
    if p is None or p["kind"] != "CQ":
        return _error(f"pageviews need a calendar quarter like CY2025Q1, got '{label}'", unit=tag.unit)
    child_grain, parent_col = (s.strip() for s in tag.hierarchy.split("->"))
    marks = ",".join("?" * len(entities))
    if method == "rollup_to_parent":
        where = f"grain = ? AND {parent_col} IN ({marks})"
        params = (child_grain, *entities)
    else:
        where = f"brand IN ({marks})"
        params = tuple(entities)
    rows = _rows(f"SELECT brand, article_title, sum(views) AS views FROM brand_attention_daily "
                 f"WHERE {where} AND date BETWEEN ? AND ? GROUP BY ALL ORDER BY brand, article_title",
                 (*params, p["start"], p["end"]))
    if not rows:
        return _insufficient(f"no pageviews for {entities} in {label}", unit=tag.unit)
    expected_days = (p["end"] - p["start"]).days + 1
    by_brand = {}
    for r in rows:
        by_brand[r["brand"]] = by_brand.get(r["brand"], 0) + r["views"]
    short = [b for b in by_brand
             if _rows("SELECT count(DISTINCT date) AS n FROM brand_attention_daily "
                      "WHERE brand = ? AND date BETWEEN ? AND ?",
                      (b, p["start"], p["end"]))[0]["n"] != expected_days]
    if short:
        return _insufficient(f"pageviews missing days for {short} in {label}", unit=tag.unit)
    template = tag.lineage.get("url_template")
    if not template:
        return _error(f"{tag.id} lineage has no url")
    values = by_brand
    return _envelope("ok", sum(values.values()), values=values, unit=tag.unit,
                     period={"label": label, "start": _iso(p["start"]), "end": _iso(p["end"])},
                     explanation=(f"Sum of grain = '{child_grain}' rows only, all titles of a brand "
                                  f"summed by date." if method == "rollup_to_parent"
                                  else "Sum of daily views."),
                     derivation=[f"{r['article_title']} ({r['brand']}) = {r['views']}" for r in rows],
                     sources=[{"type": "pageviews", "article_title": r["article_title"],
                               "url": template.format(title=r["article_title"])} for r in rows])


def _ratio_of_sums(tag, entities, p, label, denominator_id):
    if tag.table == "fundamentals" and isinstance(tag.filter.get("metric"), list):
        num, den = tag.filter["metric"]
    else:
        if denominator_id not in TAGS:
            return _error("ratio_of_sums needs denominator_id naming a flow tag")
        num, den = tag.filter.get("metric"), TAGS[denominator_id].filter.get("metric")
        if TAGS[denominator_id].semantic_type != "flow" or num not in FUNDAMENTALS:
            return _error("ratio_of_sums needs a flow numerator and a flow denominator")
    parts = {}
    for side, metric in (("numerator", num), ("denominator", den)):
        for e in entities:
            r = _fundamental(e, metric, p, label)
            if r["status"] != "ok":
                return r
            parts[(side, e)] = r
    n = sum(parts[("numerator", e)]["value"] for e in entities)
    d = sum(parts[("denominator", e)]["value"] for e in entities)
    if d == 0:
        return _error("denominator sums to zero")
    value = n / d * 100
    per_entity = {e: parts[("numerator", e)]["value"] / parts[("denominator", e)]["value"] * 100
                  for e in entities}
    return _envelope("ok", value, values=per_entity, unit="percent",
                     period={"label": label, "start": None, "end": None},
                     explanation=f"Sum of {num} divided by sum of {den}, in percent.",
                     derivation=[f"{num} = {' + '.join(str(parts[('numerator', e)]['value']) for e in entities)} = {n}",
                                 f"{den} = {' + '.join(str(parts[('denominator', e)]['value']) for e in entities)} = {d}",
                                 f"{n} / {d} * 100 = {value}"],
                     sources=[s for r in parts.values() for s in r["sources"]])


def aggregate(metric_id, entities, period, method, denominator_id=None):
    """Aggregate a tagged metric, after checking the method against the tag (§9.3)."""
    tag = TAGS.get(metric_id)
    if tag is None or tag.semantic_type not in MEASURES:
        return _error(f"unknown metric '{metric_id}'")
    entities = list(entities or [])
    p = _parse_period(period)

    # Comps across companies: always a warning with definitions, whatever the method.
    if tag.comparability == "by_definition_id" and len(entities) > 1:
        return _comps_warning(tag, entities, p, period)

    if method not in tag.valid_methods:
        use = _use_instead(tag, method)
        return _error(f"method '{method}' is not allowed for {metric_id} "
                      f"(allowed: {tag.valid_methods or 'none'})", unit=tag.unit, use_instead=use)
    if p is None:
        return _error(f"unrecognized period '{period}'", unit=tag.unit)

    if tag.table == "macro_monthly":
        return _macro(tag, method, p, period)
    if tag.table == "brand_attention_daily":
        return _views(tag, method, entities, p, period)
    if tag.table != "fundamentals":
        return _error(f"aggregate does not support {metric_id}", unit=tag.unit)

    if not entities:
        return _error("fundamentals aggregates need at least one ticker", unit=tag.unit)
    if p["kind"] not in ("FY", "FQ"):
        return _error(f"fundamentals need a fiscal period like FY2025 or FY2025Q3, got '{period}'",
                      unit=tag.unit)

    if method == "ratio_of_sums":
        result = _ratio_of_sums(tag, entities, p, period, denominator_id)
    else:
        metric = tag.filter["metric"]
        per = {}
        for e in entities:
            r = (_fundamental_quarters_sum(e, metric, p, period) if method == "sum_over_time"
                 else _fundamental(e, metric, p, period))
            if r["status"] != "ok":
                return r
            per[e] = r
        values = {e: r["value"] for e, r in per.items()}
        if len(entities) > 1 and not tag.additive_over_entities:
            return _error(f"{metric_id} is not additive across entities", unit=tag.unit,
                          use_instead=_use_instead(tag, method))
        result = _envelope("ok", sum(values.values()), values=values, unit=tag.unit,
                           period={"label": period, "start": None, "end": None},
                           explanation={"last": "Balance at the last period end.",
                                        "sum_over_time": "Sum of discrete quarters.",
                                        "sum_across_entities": "Sum across the listed companies."}[method],
                           derivation=[f"{e} = {v}" for e, v in values.items()],
                           sources=[s for r in per.values() for s in r["sources"]])

    # Mixed fiscal calendars (e.g. DRI's May year-end with December year-ends).
    if result["status"] == "ok" and tag.calendar == "fiscal" and len(entities) > 1:
        fye = {e: _fye_month(e) for e in entities}
        if len(set(fye.values())) > 1:
            result["status"] = "warning"
            result["explanation"] += (f" Warning: fiscal periods don't line up across companies "
                                      f"(fiscal year-end months {fye}).")
    return result
