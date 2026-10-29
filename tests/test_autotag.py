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
