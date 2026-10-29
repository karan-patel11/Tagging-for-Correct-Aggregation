"""Follow-up (followup/autotag/): leak test for the tagger inputs and plumbing test for the wrapper
that runs setup D on an alternate tags file. No model calls."""
import json
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
AUTOTAG = ROOT / "followup" / "autotag"
sys.path.insert(0, str(AUTOTAG))

import prompt  # noqa: E402
import tags  # noqa: E402

TAGS_YAML = ROOT / "tags" / "tags.yaml"
FORBIDDEN = ["ratio_of_sums", "reported_fy_value", "Q4 = FY - YTD9", "latest-filed"]
ENUM_ONLY = ["ratio_of_sums", "reported_fy_value"]  # allowed in the schema block as enum values


def _hand_entries():
    return yaml.safe_load(TAGS_YAML.read_text())


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _banned_texts():
    banned = list(FORBIDDEN)
    for e in _hand_entries():
        banned += _sentences(e["description"])
        if e.get("derivation"):
            banned.append(e["derivation"])
    return banned


def _packets():
    paths = sorted((AUTOTAG / "inputs").glob("*.json"))
    assert len(paths) == 43, f"expected 43 packets, found {len(paths)}"
    return {p.stem: p.read_text() for p in paths}


# ---------- leak test ----------

def test_one_packet_per_tag_id():
    assert set(_packets()) == {e["id"] for e in _hand_entries()}


def test_no_packet_or_user_message_leaks():
    leaks = []
    for tag_id, text in _packets().items():
        user = prompt.user_message(json.loads(text))
        for b in _banned_texts():
            if b in text or b in user:
                leaks.append((tag_id, b))
    assert not leaks, leaks


def test_instruction_and_format_text_do_not_leak():
    for part in (prompt.INSTRUCTIONS, prompt.FORMAT_RULES):
        hits = [b for b in _banned_texts() if b in part]
        assert not hits, hits


def test_schema_block_only_carries_forbidden_strings_as_enum_values():
    block = prompt.schema_block()
    hits = [b for b in _banned_texts() if b not in ENUM_ONLY and b in block]
    assert not hits, hits
    # Every quoted value in the schema block is an allowed value from the Tag model or
    # VALID_METHOD_NAMES, and nothing else.
    allowed = set(tags.VALID_METHOD_NAMES)
    for f in tags.Tag.model_fields.values():
        for a in typing.get_args(f.annotation):
            allowed.update(typing.get_args(a) if typing.get_origin(a) is typing.Literal else ())
        if typing.get_origin(f.annotation) is typing.Literal:
            allowed.update(typing.get_args(f.annotation))
    quoted = re.findall(r'"([^"]*)"', block)
    assert set(quoted) <= allowed, set(quoted) - allowed
    stripped = re.sub(r'"[^"]*"', "", block)
    assert not [s for s in ENUM_ONLY if s in stripped]
    # Field names in the block are exactly the Tag model's, minus the copied ones.
    names = re.findall(r"^- (\w+):", block, flags=re.M)
    assert names == [n for n in tags.Tag.model_fields if n not in prompt.COPIED_FIELDS]


def test_system_prefix_is_instructions_schema_and_format_rules_only():
    assert prompt.system_prefix() == "\n\n".join(
        [prompt.INSTRUCTIONS, prompt.schema_block(), prompt.FORMAT_RULES])


def test_format_rules_name_no_table_or_tag_id():
    entries = _hand_entries()
    names = {e["id"] for e in entries} | {e["table"] for e in entries}
    hits = [n for n in names if n in prompt.FORMAT_RULES]
    assert not hits, hits


def test_comps_notes_never_in_packets():
    import csv
    with open(ROOT / "data" / "comps_definitions.csv", newline="") as f:
        notes = [r["notes"] for r in csv.DictReader(f)]
    for tag_id, text in _packets().items():
        for n in notes:
            for s in _sentences(n):
                assert s not in text, (tag_id, s)


def test_derived_packet_has_id_and_filter_only():
    p = json.loads(_packets()["derived.operating_margin"])
    assert p == {"id": "derived.operating_margin", "table": "fundamentals",
                 "filter": {"metric": ["operating_income", "revenue"]}}


# ---------- plumbing test ----------

def _probe(path):
    out = subprocess.run([sys.executable, str(AUTOTAG / "plumbing_probe.py"), str(path)],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _dump(entries):
    return json.loads(json.dumps({t.id: t.model_dump() for t in entries}, default=str))


@pytest.fixture
def hand_copy(tmp_path):
    p = tmp_path / "tags_copy.yaml"
    p.write_bytes(TAGS_YAML.read_bytes())
    return p


def test_plumbing_identical_copy_loads_the_hand_tags(hand_copy):
    got = _probe(hand_copy)
    original = tags.load_tags(TAGS_YAML)
    assert got["tags_path"] == str(hand_copy.resolve())
    assert got["results_dir"] == str(AUTOTAG / "results")
    assert got["TAGS"] == _dump(original)
    assert got["FUNDAMENTALS"] == {t.filter["metric"]: t.id for t in original
                                   if t.table == "fundamentals"
                                   and isinstance((t.filter or {}).get("metric"), str)}
    assert got["total_assets_sum_over_time"]["status"] == "error"


def test_plumbing_changed_copy_changes_aggregate(tmp_path):
    entries = _hand_entries()
    for e in entries:
        if e["id"] == "fundamentals.total_assets":
            e["additive_over_time"] = True
            e["time_rollup"] = "sum"
            e["valid_methods"] = sorted(set(e["valid_methods"]) | {"sum_over_time"})
    changed = tmp_path / "tags_changed.yaml"
    changed.write_text(yaml.safe_dump(entries, sort_keys=False))

    hand = _probe(TAGS_YAML)["total_assets_sum_over_time"]
    draft = _probe(changed)
    got = draft["total_assets_sum_over_time"]
    assert draft["TAGS"]["fundamentals.total_assets"]["time_rollup"] == "sum"
    assert hand["status"] == "error" and "not allowed" in hand["explanation"]
    assert got["status"] == "ok" and got["value"] is not None
    assert got != hand
    print(f"\nhand tags:    status={hand['status']} | {hand['explanation']}")
    print(f"changed tags: status={got['status']} value={got['value']} | {got['explanation']}")


def test_install_refuses_when_semantics_already_imported():
    code = ("import sys; sys.path[:0] = [%r, %r, %r]; import semantics, autotag_env\n"
            "try:\n    autotag_env.install(%r)\nexcept RuntimeError as e:\n    print('refused', e)"
            % (str(ROOT / "src"), str(ROOT / "eval"), str(AUTOTAG), str(TAGS_YAML)))
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.startswith("refused"), out.stdout + out.stderr


def test_output_path_under_eval_is_refused():
    import autotag_env
    with pytest.raises(ValueError):
        autotag_env.check_output_path(ROOT / "eval" / "results" / "D_autotag.jsonl")
    assert autotag_env.check_output_path(AUTOTAG / "results" / "D_autotag.jsonl")


# ---------- score_tags (STEP 4) on a tiny hand-made fixture ----------

import score_tags  # noqa: E402

_LIN = {"source": "x"}
FIX_HAND = [
    {"id": "t.flow", "table": "t", "semantic_type": "flow", "unit": "USD",
     "additive_over_entities": True, "additive_over_time": True, "time_rollup": "sum",
     "valid_methods": ["sum_over_time", "sum_across_entities"], "period_basis": "daily",
     "calendar": "calendar", "hierarchy": "brand -> parent", "lineage": _LIN, "description": "a"},
    {"id": "t.ratio", "table": "t", "semantic_type": "ratio", "unit": "percent",
     "additive_over_entities": False, "additive_over_time": False, "time_rollup": "none",
     "valid_methods": [], "period_basis": "quarterly", "calendar": "fiscal",
     "comparability": "by_definition_id", "annualized": False, "lineage": _LIN, "description": "b"},
    {"id": "t.dim", "table": "t", "semantic_type": "dimension", "lineage": _LIN, "description": "c"},
    {"id": "t.key", "table": "t", "semantic_type": "identifier", "lineage": _LIN, "description": "d"},
]


def _fix_draft():
    d = [dict(e) for e in FIX_HAND]
    # t.flow: one extra method, one missing method, wrong unit, hierarchy written differently.
    d[0]["valid_methods"] = ["sum_over_time", "mean_over_time"]
    d[0]["unit"] = "usd"
    d[0]["hierarchy"] = "brand->parent"
    # t.ratio: comparability dropped, annualized present but different value, wrong time_rollup.
    d[1]["comparability"] = None
    d[1]["annualized"] = True
    d[1]["time_rollup"] = "mean"
    # t.dim right; t.key drafted as a dimension.
    d[3]["semantic_type"] = "dimension"
    return d


def test_m1_fixture():
    r = score_tags.m1(FIX_HAND, _fix_draft())
    assert set(r) == {"t.flow", "t.ratio"}  # measures only
    f, q = r["t.flow"], r["t.ratio"]
    assert not f["unit"]["match"] and f["semantic_type"]["match"] and f["time_rollup"]["match"]
    assert f["valid_methods"] == {"hand": ["sum_across_entities", "sum_over_time"],
                                  "draft": ["mean_over_time", "sum_over_time"], "match": False,
                                  "extra": ["mean_over_time"], "missing": ["sum_across_entities"]}
    # Presence fields are scored only where the hand tag has them, and score presence only.
    assert set(f) & set(score_tags.PRESENCE_FIELDS) == {"hierarchy"}
    assert f["hierarchy"]["match"]  # present, though written differently (M2 catches that)
    assert set(q) & set(score_tags.PRESENCE_FIELDS) == {"comparability", "annualized"}
    assert not q["comparability"]["match"]
    assert q["annualized"]["match"]  # False in the hand tag still counts as "has it"
    assert not q["time_rollup"]["match"]
    assert q["valid_methods"]["match"]  # [] == []


def test_m1_missing_entry_mismatches_every_field():
    r = score_tags.m1(FIX_HAND, [e for e in _fix_draft() if e["id"] != "t.ratio"])
    assert not any(v["match"] for v in r["t.ratio"].values())
    assert r["t.ratio"]["valid_methods"]["draft"] == score_tags.MISSING


def test_m1b_fixture():
    r = score_tags.m1b(FIX_HAND, _fix_draft())
    assert r == {"t.dim": {"hand": "dimension", "draft": "dimension", "match": True},
                 "t.key": {"hand": "identifier", "draft": "dimension", "match": False}}


def test_m2_fixture():
    r = score_tags.m2(FIX_HAND, _fix_draft())
    flow = {e["field"]: e for e in r["t.flow"]}
    assert set(flow) == {"valid_methods", "hierarchy"}  # unit is not dangerous; missing method isn't
    assert flow["valid_methods"]["forbidden_allowed"] == ["mean_over_time"]
    assert flow["hierarchy"]["draft"] == "brand->parent"  # decision 8: different value counts
    ratio = {e["field"]: e for e in r["t.ratio"]}
    assert set(ratio) == {"time_rollup", "comparability"}  # annualized is not in M2
    assert ratio["comparability"] == {"field": "comparability", "hand": "by_definition_id", "draft": None}
    assert score_tags.m2(FIX_HAND, FIX_HAND) == {"t.flow": [], "t.ratio": []}


def test_m2_flag_not_required_where_hand_has_none():
    d = _fix_draft()
    d[1]["comparability"] = "by_definition_id"
    d[1]["hierarchy"] = "x -> y"  # hand has no hierarchy on t.ratio: an extra flag is not M2
    assert {e["field"] for e in score_tags.m2(FIX_HAND, d)["t.ratio"]} == {"time_rollup"}


def test_verdicts_fixture():
    hand_m1 = score_tags.m1(FIX_HAND, FIX_HAND)
    bad_m1 = score_tags.m1(FIX_HAND, _fix_draft())
    v = score_tags.verdicts({"d1": hand_m1, "d2": hand_m1, "d3": bad_m1},
                            {"d1": score_tags.m1b(FIX_HAND, FIX_HAND),
                             "d2": score_tags.m1b(FIX_HAND, FIX_HAND),
                             "d3": score_tags.m1b(FIX_HAND, _fix_draft())})
    assert v["unit"]["verdict"] == "needs human review"  # one draft wrong on one measure
    assert v["semantic_type"]["verdict"] == "safe to auto-draft"
    assert v["calendar"]["verdict"] == "safe to auto-draft"
    assert v["hierarchy"]["verdict"] == "safe to auto-draft"  # presence only
    assert v["comparability"]["verdict"] == "needs human review"
    assert v["seasonal_adjustment"]["verdict"] == "needs human review"  # no entry scored: not safe
    assert v["semantic_type (dimension/identifier)"]["verdict"] == "needs human review"


def test_scored_fields_differ_fixture():
    d = {e["id"]: e for e in _fix_draft()}
    h = {e["id"]: e for e in FIX_HAND}
    assert set(score_tags.scored_fields_differ(h["t.flow"], d["t.flow"])) == {"unit", "valid_methods"}
    assert score_tags.scored_fields_differ(h["t.dim"], d["t.dim"]) == []
    assert score_tags.scored_fields_differ(h["t.key"], d["t.key"]) == ["semantic_type"]
    assert score_tags.scored_fields_differ(h["t.key"], None) == ["entry"]


def test_m3_lists_every_failure(tmp_path):
    d = _fix_draft()
    d[0]["time_rollup"] = "average"          # not an allowed value
    d[1]["valid_methods"] = ["median"]       # unknown method
    del d[2]["lineage"]                      # required field missing
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    r = score_tags.m3(p)
    assert not r["pass"] and not r["load_tags_ok"]
    assert set(r["entry_errors"]) == {"t.flow", "t.ratio", "t.dim"}
    assert any("time_rollup" in e for e in r["entry_errors"]["t.flow"])
    assert any("lineage" in e for e in r["entry_errors"]["t.dim"])
    assert r["db_checked_entries"] == 1  # only t.key validated
    assert any("table 't' not in database" in x for x in r["db_problems"])


def test_m3_hand_tags_pass():
    r = score_tags.m3(TAGS_YAML)
    assert r["pass"] and r["entry_errors"] == {} and r["db_problems"] == []


def test_score_all_hand_against_itself_is_perfect():
    r = score_tags.score_all({"draft_1": TAGS_YAML})
    d = r["drafts"]["draft_1"]
    assert len(d["m1"]) == 12 and len(d["m1b"]) == 31
    assert all(v["match"] for row in d["m1"].values() for v in row.values())
    assert all(v["match"] for v in d["m1b"].values())
    assert all(not v for v in d["m2"].values())
    assert d["m3"]["pass"]


# ---------- draft.py parsing and M4 classification (no model calls) ----------

import draft  # noqa: E402
import m4  # noqa: E402


def test_parse_fields():
    assert draft.parse_fields('{"a": 1}') == ({"a": 1}, [])
    assert draft.parse_fields('```json\n{"a": 1}\n```') == ({"a": 1}, ["code fence removed"])
    obj, notes = draft.parse_fields('Here it is: {"a": 1}')
    assert obj is None and "not valid JSON" in notes[0]
    assert draft.parse_fields("[1]")[0] is None


def test_build_entry_copies_id_table_filter_and_keeps_unknown_keys():
    pkt = {"table": "fundamentals", "column": "value", "filter": {"metric": "revenue"}}
    hand = {e["id"]: e for e in _hand_entries()}["fundamentals.revenue"]
    obj = {k: v for k, v in hand.items() if k not in ("id", "table", "filter")}
    obj["table"] = "wrong"
    entry, notes = draft.build_entry("fundamentals.revenue", pkt, obj)
    assert entry == hand and list(entry)[:3] == ["id", "table", "filter"]
    assert notes == ["model returned ['table']; replaced by the packet's values"]
    entry, _ = draft.build_entry("fundamentals.revenue", pkt, {**obj, "confidence": 0.9})
    assert entry["confidence"] == 0.9  # left in, so load_tags rejects it (M3)
    entry, _ = draft.build_entry("x.y", {"table": "x"}, None)
    assert entry == {"id": "x.y", "table": "x", "filter": None}


def _rec(final=None, parsed=True, error=None, tool_errors=False, calls=()):
    tcs = [{"name": n, "input": i, "is_error": tool_errors} for n, i in calls] or \
          [{"name": "list_metrics", "input": {}, "is_error": tool_errors}]
    return {"final": final, "parsed": parsed, "error": error, "tool_calls": tcs}


def test_m4_classify_order():
    F = lambda **k: {"answer": 1.0, "unit": "USD", "warning": False, "refused": False, **k}
    assert m4.classify(_rec(None, parsed=False)) == m4.OTHER
    assert m4.classify(_rec(F(refused=True, warning=True), error="APIError: x")) == m4.OTHER
    assert m4.classify(_rec(F(refused=True, warning=True))) == m4.REFUSAL
    assert m4.classify(_rec(F(answer=None, warning=True), tool_errors=True)) == m4.REFUSAL
    assert m4.classify(_rec(F(answer=None, warning=True))) == m4.WARNING  # no tool error
    assert m4.classify(_rec(F(warning=True), tool_errors=True)) == m4.WARNING  # numeric answer
    assert m4.classify(_rec(F())) == m4.SILENT


def test_m4_links_named_tags_that_differ():
    hand = _hand_entries()
    d = [dict(e) for e in hand]
    for e in d:
        if e["id"] == "fundamentals.total_assets":
            e["time_rollup"] = "sum"
    rec = _rec(calls=[("get_metric", {"ticker": "CMG", "metric": "total_assets", "period": "FY2025"}),
                      ("describe_column", {"metric_id": "fundamentals.revenue"}),
                      ("describe_column", {"metric_id": "made.up"})])
    assert m4.named_tag_ids(rec, m4.short_metric_map(hand)) == [
        "fundamentals.revenue", "fundamentals.total_assets", "made.up"]
    assert m4.linked_fields(rec, hand, d) == {"fundamentals.total_assets": ["time_rollup"]}


def test_m4_changed_outcomes():
    hand_s = {("q1", r): {"correct": True} for r in (1, 2, 3)} | {("q2", r): {"correct": True} for r in (1, 2, 3)}
    draft_s = dict(hand_s) | {("q1", 2): {"correct": False}}
    F = {"answer": 5, "unit": "USD", "warning": False, "refused": False}
    runs = {k: _rec(F) for k in draft_s}
    ch = m4.changed_outcomes(hand_s, draft_s, runs, _hand_entries(), _hand_entries())
    assert ch == {"q1": {"hand_correct": 3, "draft_correct": 2, "incorrect_draft_runs": [
        {"run": 2, "class": m4.SILENT, "final_line": None, "linked": {}}]}}
