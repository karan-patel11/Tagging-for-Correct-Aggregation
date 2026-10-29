"""STEP 4: score drafted tags against the hand tags in tags/tags.yaml (PREREG.md, Metrics).

  M1   per-field exact match for the 12 measures (hand semantic_type in MEASURE_TYPES):
       semantic_type, unit, additive_over_entities, additive_over_time, time_rollup, period_basis,
       calendar; valid_methods as set equality (extra and missing methods listed); presence of
       comparability / hierarchy / seasonal_adjustment / annualized where the hand tag has them.
  M1b  semantic_type exact match for the 31 dimension/identifier entries.
  M2   dangerous errors per measure: a method the hand tag forbids; a different
       additive_over_time, additive_over_entities or time_rollup; a comparability or hierarchy
       value the hand tag has and the draft lacks or changes (design decision 8).
  M3   does the draft file pass load_tags and check_tags_against_db; every failure is listed.

A draft entry that is missing (no entry with that id) counts as a mismatch on every field.
Free-text fields (description, derivation, lineage) are not scored.

Scores the drafts that exist (draft 1 alone is enough, for the run order in PREREG_DEVIATIONS.md)
and lists the missing ones. The per-field verdict needs all three drafts and is left out until then.

Run: python followup/autotag/score_tags.py   (writes followup/autotag/results/score_tags.json)
"""
import json
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import tags  # noqa: E402

HAND_PATH = ROOT / "tags" / "tags.yaml"
DRAFTS = HERE / "drafts"
OUT = HERE / "results" / "score_tags.json"

EXACT_FIELDS = ["semantic_type", "unit", "additive_over_entities", "additive_over_time",
                "time_rollup", "period_basis", "calendar"]
PRESENCE_FIELDS = ["comparability", "hierarchy", "seasonal_adjustment", "annualized"]
M1_FIELDS = EXACT_FIELDS + ["valid_methods"] + PRESENCE_FIELDS
DANGEROUS_EXACT = ["additive_over_time", "additive_over_entities", "time_rollup"]
DANGEROUS_FLAGS = ["comparability", "hierarchy"]
MISSING = "<no entry>"
DRAFT_NAMES = ["draft_1", "draft_2", "draft_3"]


def read_entries(path):
    raw = yaml.safe_load(Path(path).read_text())
    return raw if isinstance(raw, list) else []


def _by_id(entries):
    return {e["id"]: e for e in entries if isinstance(e, dict) and "id" in e}


def is_measure(entry):
    return entry["semantic_type"] in tags.MEASURE_TYPES


def m1(hand, draft):
    """Per measure and per field: {"hand", "draft", "match"}; valid_methods also lists
    extra/missing; presence fields are scored only where the hand tag has a value."""
    d_by = _by_id(draft)
    out = {}
    for h in hand:
        if not is_measure(h):
            continue
        d = d_by.get(h["id"])
        row = {}
        for f in EXACT_FIELDS:
            dv = MISSING if d is None else d.get(f)
            row[f] = {"hand": h.get(f), "draft": dv, "match": d is not None and dv == h.get(f)}
        hm = set(h.get("valid_methods") or [])
        dm = None if d is None else set(d.get("valid_methods") or [])
        row["valid_methods"] = {
            "hand": sorted(hm), "draft": MISSING if dm is None else sorted(dm),
            "match": dm == hm,
            "extra": [] if dm is None else sorted(dm - hm),
            "missing": sorted(hm) if dm is None else sorted(hm - dm)}
        for f in PRESENCE_FIELDS:
            if h.get(f) is None:
                continue
            dv = MISSING if d is None else d.get(f)
            row[f] = {"hand": h[f], "draft": dv, "match": d is not None and dv is not None}
        out[h["id"]] = row
    return out


def m1b(hand, draft):
    d_by = _by_id(draft)
    out = {}
    for h in hand:
        if is_measure(h):
            continue
        d = d_by.get(h["id"])
        dv = MISSING if d is None else d.get("semantic_type")
        out[h["id"]] = {"hand": h["semantic_type"], "draft": dv,
                        "match": d is not None and dv == h["semantic_type"]}
    return out


def m2(hand, draft):
    """Dangerous errors per measure: a list of {"field", "hand", "draft", ...}; empty if none."""
    d_by = _by_id(draft)
    out = {}
    for h in hand:
        if not is_measure(h):
            continue
        d = d_by.get(h["id"])
        errs = []
        if d is None:
            errs.append({"field": "entry", "hand": h["id"], "draft": MISSING})
            out[h["id"]] = errs
            continue
        extra = sorted(set(d.get("valid_methods") or []) - set(h.get("valid_methods") or []))
        if extra:
            errs.append({"field": "valid_methods", "hand": sorted(h.get("valid_methods") or []),
                         "draft": sorted(d.get("valid_methods") or []), "forbidden_allowed": extra})
        for f in DANGEROUS_EXACT:
            if d.get(f) != h.get(f):
                errs.append({"field": f, "hand": h.get(f), "draft": d.get(f)})
        for f in DANGEROUS_FLAGS:
            if h.get(f) is not None and d.get(f) != h[f]:
                errs.append({"field": f, "hand": h[f], "draft": d.get(f)})
        out[h["id"]] = errs
    return out


def m3(path, db_path=tags.DB_PATH):
    """load_tags and check_tags_against_db on a draft file. load_tags stops at the first bad entry,
    so on failure every entry is also validated alone to list every failure, and the database check
    is run on the entries that validated."""
    result = {"load_tags_ok": True, "load_tags_error": None, "entry_errors": {},
              "db_checked_entries": None, "db_problems": []}
    try:
        good = tags.load_tags(path)
    except (ValidationError, ValueError, TypeError) as e:
        result["load_tags_ok"] = False
        result["load_tags_error"] = f"{type(e).__name__}: {e}"
        good = []
        for i, entry in enumerate(read_entries(path)):
            key = entry.get("id", f"#{i}") if isinstance(entry, dict) else f"#{i}"
            try:
                good.append(tags.Tag(**entry))
            except (ValidationError, TypeError) as ee:
                result["entry_errors"][key] = [
                    f"{'.'.join(map(str, x['loc'])) or '(entry)'}: {x['msg']}"
                    for x in ee.errors()] if isinstance(ee, ValidationError) else [str(ee)]
    result["db_checked_entries"] = len(good)
    result["db_problems"] = tags.check_tags_against_db(good, db_path)
    result["pass"] = result["load_tags_ok"] and not result["db_problems"]
    return result


def scored_fields_differ(hand_entry, draft_entry):
    """Scored fields (M1 for measures, M1b for the rest) on which a draft entry differs."""
    if draft_entry is None:
        return ["entry"]
    if not is_measure(hand_entry):
        return [] if draft_entry.get("semantic_type") == hand_entry["semantic_type"] else ["semantic_type"]
    row = m1([hand_entry], [draft_entry])[hand_entry["id"]]
    return [f for f, v in row.items() if not v["match"]]


def verdicts(m1_by_draft, m1b_by_draft):
    """Per field: "safe to auto-draft" only if every draft matches the hand tag on every entry
    scored for that field; otherwise "needs human review"."""
    out = {}
    for f in M1_FIELDS:
        cells = [row[f]["match"] for rows in m1_by_draft.values() for row in rows.values() if f in row]
        n_per_draft = {k: sum(1 for row in rows.values() if f in row) for k, rows in m1_by_draft.items()}
        out[f] = {"entries_per_draft": n_per_draft, "all_match": all(cells) and bool(cells),
                  "verdict": "safe to auto-draft" if cells and all(cells) else "needs human review"}
    cells = [v["match"] for rows in m1b_by_draft.values() for v in rows.values()]
    out["semantic_type (dimension/identifier)"] = {
        "entries_per_draft": {k: len(v) for k, v in m1b_by_draft.items()},
        "all_match": all(cells) and bool(cells),
        "verdict": "safe to auto-draft" if cells and all(cells) else "needs human review"}
    return out


def score_all(draft_paths, hand_path=HAND_PATH, db_path=tags.DB_PATH):
    hand = read_entries(hand_path)
    out = {"hand_path": str(Path(hand_path).relative_to(ROOT)) if Path(hand_path).is_relative_to(ROOT)
           else str(hand_path), "drafts": {}}
    for name, p in draft_paths.items():
        draft = read_entries(p)
        out["drafts"][name] = {"m1": m1(hand, draft), "m1b": m1b(hand, draft),
                               "m2": m2(hand, draft), "m3": m3(p, db_path)}
    if set(out["drafts"]) == set(DRAFT_NAMES):
        out["verdicts"] = verdicts({k: v["m1"] for k, v in out["drafts"].items()},
                                   {k: v["m1b"] for k, v in out["drafts"].items()})
    else:
        out["verdicts"] = None  # the decision rule needs all three drafts
    return out


def main(drafts_dir=DRAFTS, out_path=OUT):
    paths = {n: Path(drafts_dir) / f"{n}.yaml" for n in DRAFT_NAMES}
    present = {n: p for n, p in paths.items() if p.exists()}
    missing = [n for n in DRAFT_NAMES if n not in present]
    if not present:
        sys.exit(f"no draft files in {drafts_dir}")
    result = score_all(present)
    result["missing_drafts"] = missing
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=1, default=str) + "\n")
    for name, d in result["drafts"].items():
        exact = sum(v["match"] for row in d["m1"].values() for v in row.values())
        cells = sum(len(row) for row in d["m1"].values())
        dang = sum(len(v) for v in d["m2"].values())
        print(f"{name}: M1 {exact}/{cells} field cells match | M1b "
              f"{sum(v['match'] for v in d['m1b'].values())}/{len(d['m1b'])} | M2 {dang} dangerous "
              f"errors | M3 {'pass' if d['m3']['pass'] else 'FAIL'}")
    if missing:
        print(f"missing drafts (not scored; no per-field verdict until all three exist): {missing}")
    print(f"wrote {out_path}")
    return result


if __name__ == "__main__":
    main()
