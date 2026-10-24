import copy

import pytest
from pydantic import ValidationError

import duckdb
from tags import DB_PATH, Tag, check_tags_against_db, load_tags

GOOD = {
    "id": "fundamentals.example",
    "table": "fundamentals",
    "filter": {"metric": "revenue"},
    "semantic_type": "flow",
    "unit": "USD",
    "additive_over_entities": True,
    "additive_over_time": True,
    "time_rollup": "sum",
    "valid_methods": ["sum_over_time"],
    "lineage": {"source": "synthetic"},
    "description": "Synthetic tag used only in tests.",
}


def test_tags_yaml_loads_and_validates():
    tags = load_tags()
    assert len(tags) > 0
    assert len({t.id for t in tags}) == len(tags)


def test_unknown_field_fails():
    bad = copy.deepcopy(GOOD)
    bad["additivity"] = True
    with pytest.raises(ValidationError):
        Tag(**bad)


def test_flow_without_additive_over_time_fails():
    bad = {k: v for k, v in GOOD.items() if k != "additive_over_time"}
    with pytest.raises(ValidationError):
        Tag(**bad)
    Tag(**GOOD)  # the unbroken dict is valid


@pytest.mark.skipif(not DB_PATH.exists(), reason="run python src/build_db.py first")
def test_every_stored_metric_has_a_tag():
    tags = load_tags()
    assert check_tags_against_db(tags) == []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    stored = {r[0] for r in con.execute("select distinct metric from fundamentals").fetchall()}
    con.close()
    tagged = {t.filter["metric"] for t in tags
              if t.table == "fundamentals" and t.semantic_type not in ("dimension", "identifier")
              and isinstance((t.filter or {}).get("metric"), str)}
    assert stored <= tagged
