"""Post-run analysis (added after the results; not pre-registered).

For every incorrect draft-1 run in results/D_autotag.jsonl, read the tool outputs and give the run
one root cause: the first of the tag-driven tool errors below that appears in the run, in this
order. Each cause is the error text src/semantics.py returns for one tag field:

  lineage has no url           _macro needs lineage.url; _views needs lineage.url_template
  AttributeError ... 'split'   _views splits tag.hierarchy; a null hierarchy raises, and
                               mcp_server.call_tool returns the exception as a tool error
  insufficient data: no reported Q <metric>
                               _fundamental reads the reported quarterly value when
                               time_rollup == reported_fy_value; flows are filed year-to-date
  method 'm' is not allowed    m is in the hand tag's valid_methods but not the draft's

A run with none of these has only tool errors that are not tied to a tag difference (an unknown
metric name, a period format, a method name that is not a method).

Also: the methods each draft allows that the hand tag forbids, and whether any run called them;
and validator rules (proposals only; src/tags.py is not changed) checked against the hand tags and
the three drafts.

Run: python followup/autotag/root_causes.py   (prints the section; build_results.py includes it)
"""
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import duckdb
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import m4  # noqa: E402
import score_d  # noqa: E402
import score_tags  # noqa: E402
import tags  # noqa: E402  (src/ is on sys.path via score_tags)

D_AUTOTAG = HERE / "results" / "D_autotag.jsonl"
INPUTS = HERE / "inputs"
DRAFT_NAMES = score_tags.DRAFT_NAMES
TITLE = "Post-run analysis (added after the results; not pre-registered)"

LINEAGE, HIERARCHY, REPORTED_Q, METHOD, NONE = (
    "lineage has no url", "hierarchy is null (AttributeError)",
    "insufficient data: no reported quarter", "method not allowed by the draft",
    "no tag-driven tool error")
CAUSE_ORDER = [LINEAGE, HIERARCHY, REPORTED_Q, METHOD, NONE]
CAUSE_FIELD = {LINEAGE: "lineage.url / lineage.url_template", HIERARCHY: "hierarchy",
               REPORTED_Q: "time_rollup", METHOD: "valid_methods", NONE: "none"}
# What src/semantics.py reads from lineage, per table.
LINEAGE_KEY = {"macro_monthly": "url", "brand_attention_daily": "url_template"}


def explanation(output):
    try:
        return json.loads(output).get("explanation") or ""
    except (json.JSONDecodeError, AttributeError):
        return str(output)


def run_causes(rec, hand, draft):
    """Every tag-driven cause in one run, as [(cause, tag id)], in the order of the tool calls."""
    short = m4.short_metric_map(list(hand.values()))
    out = []
    for tc in rec.get("tool_calls", []):
        if not tc.get("is_error"):
            continue
        text, args = explanation(tc["output"]), tc.get("input") or {}
        if m := re.match(r"^(\S+) lineage has no url$", text):
            out.append((LINEAGE, m[1]))
        elif "AttributeError: 'NoneType' object has no attribute 'split'" in text:
            out.append((HIERARCHY, args.get("metric_id")))
        elif m := re.match(r"^insufficient data: no reported Q (\w+) for", text):
            out.append((REPORTED_Q, short.get(m[1], m[1])))
        elif m := re.match(r"^method '([^']+)' is not allowed for (\S+)", text):
            method, tid = m[1], m[2]
            if (tid in hand and method in (hand[tid].get("valid_methods") or [])
                    and method not in (draft.get(tid, {}).get("valid_methods") or [])):
                out.append((METHOD, tid))
    return out


def primary_cause(causes):
    for c in CAUSE_ORDER[:-1]:
        for cause, tid in causes:
            if cause == c:
                return cause, tid
    return NONE, None


def field_values(cause, tid, hand, draft):
    """(hand value, draft value) of the field behind a cause, for one tag id."""
    h, d = hand.get(tid, {}), draft.get(tid, {})
    if cause == LINEAGE:
        key = LINEAGE_KEY.get(h.get("table"), "url")
        return f"{key}: {'present' if (h.get('lineage') or {}).get(key) else 'absent'}", \
               f"{key}: {'present' if (d.get('lineage') or {}).get(key) else 'absent'}"
    if cause == HIERARCHY:
        return h.get("hierarchy"), d.get("hierarchy")
    if cause == REPORTED_Q:
        return h.get("time_rollup"), d.get("time_rollup")
    if cause == METHOD:
        return h.get("valid_methods"), d.get("valid_methods")
    return None, None


def packet_urls(tid):
    """URLs (http or https) anywhere in a tag's input packet."""
    return re.findall(r"https?://", (INPUTS / f"{tid}.json").read_text())


# ---------- validator rules (proposals only) ----------

def _parent_columns(table, cache={}):
    if table not in cache:
        con = duckdb.connect(str(tags.DB_PATH), read_only=True)
        try:
            cache[table] = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()
                            if r[0].startswith("parent_")]
        finally:
            con.close()
    return cache[table]


# (rule, the fields an error must be on for the rule to catch it, check returning True on a violation)
RULES = [
    ("flow => additive_over_time is true and time_rollup is sum",
     {"additive_over_time", "time_rollup"},
     lambda e: e.get("semantic_type") == "flow"
     and (e.get("additive_over_time") is not True or e.get("time_rollup") != "sum")),
    ("sum_over_time in valid_methods => additive_over_time is true",
     {"additive_over_time", "valid_methods"},
     lambda e: "sum_over_time" in (e.get("valid_methods") or []) and e.get("additive_over_time") is not True),
    ("sum_across_entities in valid_methods => additive_over_entities is true",
     {"additive_over_entities", "valid_methods"},
     lambda e: "sum_across_entities" in (e.get("valid_methods") or [])
     and e.get("additive_over_entities") is not True),
    ("measure on a table with a parent_* column => hierarchy is set",
     {"hierarchy"},
     lambda e: e.get("semantic_type") in tags.MEASURE_TYPES and _parent_columns(e["table"])
     and not e.get("hierarchy")),
    ("measure on macro_monthly => lineage.url is set; on brand_attention_daily => "
     "lineage.url_template is set (the keys src/semantics.py reads)",
     {"lineage.url", "lineage.url_template"},
     lambda e: e.get("semantic_type") in tags.MEASURE_TYPES and e["table"] in LINEAGE_KEY
     and not (e.get("lineage") or {}).get(LINEAGE_KEY[e["table"]])),
]


def rule_hits(entries):
    return {name: sorted(e["id"] for e in entries if isinstance(e, dict) and "id" in e and f(e))
            for name, _, f in RULES}


def catching_rules(hits, tid, field):
    """Rules that flag this entry and cover this field."""
    return [name for name, fields, _ in RULES if field in fields and tid in hits[name]]


def analyze():
    hand_list = score_tags.read_entries(score_tags.HAND_PATH)
    hand = {e["id"]: e for e in hand_list}
    drafts = {n: score_tags.read_entries(HERE / "drafts" / f"{n}.yaml") for n in DRAFT_NAMES}
    d1 = {e["id"]: e for e in drafts["draft_1"]}
    scored, runs, _ = score_d.score_records(D_AUTOTAG)
    hand_runs = score_d.load_records(score_d.HAND_D)

    # Root cause per incorrect run.
    incorrect = sorted(k for k, s in scored.items() if not s["correct"])
    groups = defaultdict(lambda: {"runs": [], "tags": set()})
    any_cause = defaultdict(set)
    for k in incorrect:
        causes = run_causes(runs[k], hand, d1)
        for c, _ in causes:
            any_cause[c].add(k)
        cause, tid = primary_cause(causes)
        groups[cause]["runs"].append(k)
        if tid:
            groups[cause]["tags"].add(tid)
    cause_rows = []
    for c in CAUSE_ORDER:
        if c not in groups:
            continue
        g = groups[c]
        cause_rows.append({
            "cause": c, "field": CAUSE_FIELD[c], "tags": sorted(g["tags"]),
            "questions": sorted({q for q, _ in g["runs"]}), "runs": len(g["runs"]),
            "runs_with_error_anywhere": len(any_cause.get(c, ())) if c != NONE else len(g["runs"]),
            "values": {t: field_values(c, t, hand, d1) for t in sorted(g["tags"])},
            "classes": dict(sorted(defaultdict(int, {
                cl: sum(1 for k in g["runs"] if m4.classify(runs[k]) == cl)
                for cl in m4.CLASSES}).items())),
            "m4_linked_fields": sorted({"/".join(fs) for k in g["runs"]
                                        for fs in m4.linked_fields(runs[k], hand_list,
                                                                   drafts["draft_1"]).values()}),
        })

    # Lineage: were URLs in the input packets?
    lineage_tags = sorted(groups[LINEAGE]["tags"]) if LINEAGE in groups else []
    packet_url_counts = {t: len(packet_urls(t)) for t in lineage_tags}

    # Permissive errors: methods a draft allows that the hand tag forbids, and calls to them.
    calls = defaultdict(lambda: {"hand": set(), "draft_1": set(), "draft_1_ok": 0, "draft_1_errors": set()})
    for label, rs in (("hand", hand_runs), ("draft_1", runs)):
        for (qid, _), rec in rs.items():
            for tc in rec.get("tool_calls", []):
                a = tc.get("input") or {}
                if tc.get("name") == "aggregate" and isinstance(a.get("metric_id"), str):
                    key = (a["metric_id"], a.get("method"))
                    calls[key][label].add(qid)
                    if label == "draft_1" and not tc.get("is_error"):
                        calls[key]["draft_1_ok"] += 1
                    elif label == "draft_1":
                        calls[key]["draft_1_errors"].add(explanation(tc["output"]))
    permissive = []
    for tid, h in hand.items():
        if h["semantic_type"] not in tags.MEASURE_TYPES:
            continue
        allowed_by = defaultdict(list)
        for n in DRAFT_NAMES:
            d = {e["id"]: e for e in drafts[n]}.get(tid, {})
            for m in sorted(set(d.get("valid_methods") or []) - set(h.get("valid_methods") or [])):
                allowed_by[m].append(n)
        for m, ns in sorted(allowed_by.items()):
            c = calls.get((tid, m), {"hand": set(), "draft_1": set(), "draft_1_ok": 0,
                                     "draft_1_errors": set()})
            permissive.append({"tag": tid, "method": m, "drafts": ns,
                               "hand_run_questions": sorted(c["hand"]),
                               "draft_1_run_questions": sorted(c["draft_1"]),
                               "draft_1_ok_calls": c["draft_1_ok"],
                               "draft_1_errors": sorted(c["draft_1_errors"])})

    # What aggregate returns for each permissive pair, on each draft that allows it and on the hand tags.
    calls_by = defaultdict(list)
    for x in permissive:
        for n in x["drafts"] + ["hand"]:
            calls_by[n].append([x["tag"], hand[x["tag"]]["table"], x["method"]])
    paths = {n: HERE / "drafts" / f"{n}.yaml" for n in DRAFT_NAMES} | {"hand": score_tags.HAND_PATH}
    results = {n: probe(paths[n], c) for n, c in calls_by.items()}
    # Counterfactual: draft_1 with only lineage and hierarchy copied from the hand tags, i.e. after a
    # reviewer fills in the input gap (URLs) and the missing hierarchy. A temporary file, not a draft.
    d1_calls = [[x["tag"], hand[x["tag"]]["table"], x["method"]] for x in permissive
                if "draft_1" in x["drafts"]]
    with tempfile.TemporaryDirectory() as tmp:
        patched = [dict(e, lineage=hand[e["id"]]["lineage"], hierarchy=hand[e["id"]].get("hierarchy"))
                   for e in drafts["draft_1"]]
        path = Path(tmp) / "draft_1_hand_lineage_hierarchy.yaml"
        path.write_text(yaml.safe_dump(patched, sort_keys=False))
        cf = probe(path, d1_calls) if d1_calls else {}
    for x in permissive:
        key = f"{x['tag']} {x['method']}"
        x["hand_result"] = results["hand"][key]
        x["draft_results"] = {n: results[n][key] for n in x["drafts"]}
        x["counterfactual"] = cf.get(key)

    # Validator gap: what M3 passed, and what the proposed rules would flag.
    m3 = {n: score_tags.m3(HERE / "drafts" / f"{n}.yaml") for n in DRAFT_NAMES}
    hits = {"hand": rule_hits(hand_list)} | {n: rule_hits(drafts[n]) for n in DRAFT_NAMES}
    errors = []  # every M2 error, plus a missing lineage key semantics.py needs
    for n in DRAFT_NAMES:
        d_by = {e["id"]: e for e in drafts[n]}
        flagged = {tid for ids in hits[n].values() for tid in ids}
        for tid, errs in score_tags.m2(hand_list, drafts[n]).items():
            for e in errs:
                errors.append({"draft": n, "tag": tid, "field": e["field"], "hand": e["hand"],
                               "draft_value": e["draft"], "entry_flagged": tid in flagged,
                               "caught_by": catching_rules(hits[n], tid, e["field"])})
        for tid, h in hand.items():
            key = LINEAGE_KEY.get(h["table"])
            if (h["semantic_type"] in tags.MEASURE_TYPES and key and (h["lineage"] or {}).get(key)
                    and not (d_by.get(tid, {}).get("lineage") or {}).get(key)):
                errors.append({"draft": n, "tag": tid, "field": f"lineage.{key}", "hand": "present",
                               "draft_value": "absent", "entry_flagged": tid in flagged,
                               "caught_by": catching_rules(hits[n], tid, f"lineage.{key}")})
    return {"incorrect_runs": len(incorrect), "total_runs": len(scored), "causes": cause_rows,
            "packet_url_counts": packet_url_counts, "permissive": permissive, "m3": m3,
            "rule_hits": hits, "errors": errors}


# Arguments for calling aggregate on a permissive tag/method pair, per table (chosen for this
# analysis; any company, months or quarter in the data would do).
PROBE_ARGS = {"fundamentals": (["CMG"], "FY2025"), "macro_monthly": ([], "2025-01:2025-06"),
              "brand_attention_daily": (["KFC"], "CY2025Q1")}


def probe(tags_path, calls):
    """aggregate(tid, entities, period, method) for each (tid, table, method) with tags_path loaded,
    in a fresh process through autotag_env.install(). Returns {"tid method": envelope}."""
    out = subprocess.run([sys.executable, str(Path(__file__)), "--probe", str(tags_path),
                          json.dumps(calls)], cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def _probe_main(tags_path, calls):
    import autotag_env
    _, semantics, _ = autotag_env.install(tags_path)
    res = {}
    for tid, table, method in calls:
        entities, period = PROBE_ARGS[table]
        try:
            env = semantics.aggregate(tid, entities, period, method)
        except Exception as e:  # what mcp_server.call_tool would return
            env = {"status": "error", "explanation": f"{type(e).__name__}: {e}", "value": None}
        res[f"{tid} {method}"] = {"status": env["status"], "value": env.get("value"),
                                  "explanation": env.get("explanation")}
    print(json.dumps(res, default=str))


def _t(header, rows):
    return (["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
            + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def _j(v):
    return "null" if v is None else (v if isinstance(v, str) else json.dumps(v))


def section_lines(a=None):
    a = a or analyze()
    by = {c["cause"]: c for c in a["causes"]}
    L = [f"## {TITLE}", "",
         f"Written by `followup/autotag/root_causes.py` after the results above existed. It reads "
         f"the tool outputs of the {a['incorrect_runs']} incorrect draft-1 runs (of "
         f"{a['total_runs']}) in `followup/autotag/results/D_autotag.jsonl` and gives each run one "
         f"root cause: the first tag-driven tool error in the run, checked in the order of the "
         f"table. \"runs with this error\" counts every incorrect run in which the error appears "
         f"at all.", ""]
    L += _t(["cause (tool error text)", "draft field", "tag ids", "questions", "runs (root cause)",
             "runs with this error", "hand value -> draft_1 value"],
            [[c["cause"], c["field"], ", ".join(c["tags"]) or "-", ", ".join(c["questions"]),
              c["runs"], c["runs_with_error_anywhere"],
              "; ".join(f"{t}: {_j(h)} -> {_j(d)}" for t, (h, d) in c["values"].items()) or "-"]
             for c in a["causes"]]) + [""]

    if LINEAGE in by:
        c = by[LINEAGE]
        urls = sum(a["packet_url_counts"].values())
        L += [f"**{', '.join(c['questions'][:1])}-{c['questions'][-1]} (lineage).** In "
              f"{c['runs']} runs the tool refused because the draft lineage of "
              f"{' and '.join(c['tags'])} has no url, and src/semantics.py returns an error for a "
              f"macro series without one. The input packets for these tags contain {urls} URLs "
              f"(PREREG design decision 4: no URL is available from the vendor files), so this is "
              f"a gap in the inputs, not a tagging judgment. The M4 table attributes these runs to "
              f"{' and '.join(c['m4_linked_fields']) or 'no field'}: that is the scored-field "
              f"difference on the tags the runs named, not the cause; lineage is not a scored "
              f"field.", ""]
    if HIERARCHY in by:
        c = by[HIERARCHY]
        cls = ", ".join(f"{v} {k}" for k, v in c["classes"].items() if v)
        L += [f"**{c['questions'][0]}-{c['questions'][-1]} (hierarchy).** In {c['runs']} runs "
              f"({cls}) the draft's null hierarchy on {', '.join(c['tags'])} makes "
              f"src/semantics.py raise AttributeError when it splits the hierarchy string; "
              f"mcp_server.call_tool catches it and returns it as a tool error. The missing "
              f"hierarchy is a draft error. Raising instead of returning a clean refusal is a "
              f"robustness gap in src/semantics.py; it is not fixed here because src/ is frozen.",
              ""]
    if REPORTED_Q in by:
        c = by[REPORTED_Q]
        L += [f"**{', '.join(c['questions'])} (time_rollup).** In {c['runs']} runs the draft's "
              f"time_rollup on {', '.join(c['tags'])} is reported_fy_value, so src/semantics.py "
              f"looks for a reported quarterly value for a fiscal quarter. Those flows are filed "
              f"year-to-date, so the tool returns insufficient data.", ""]
    if NONE in by:
        c = by[NONE]
        L += [f"**{', '.join(c['questions'])} (no tag-driven error).** {c['runs']} runs had only "
              f"tool errors not tied to a tag difference (unknown metric names, period formats, "
              f"method names that are not methods).", ""]

    p = a["permissive"]
    called = [x for x in p if x["draft_1_ok_calls"]]
    tried = [x for x in p if x["draft_1_run_questions"]]

    def res(r):
        return (f"{r['status']}: {r['value']}" if r["status"] != "error"
                else f"error: {r['explanation']}")

    number = [x for x in p if any(r["status"] != "error" for r in x["draft_results"].values())]
    L += ["### Permissive errors not exercised", "",
          f"Every method a draft allows that the hand tag forbids ({len(p)} tag/method pairs), "
          f"whether any run called aggregate with it, and what aggregate returns for the pair when "
          f"called directly by this script (no model) on each draft that allows it and on the hand "
          f"tags, with "
          + "; ".join(f"{t}: entities {e}, period {per}" for t, (e, per) in PROBE_ARGS.items())
          + ". \"draft_1 ok calls\" counts calls in the draft-1 runs that returned a value.", ""]
    L += _t(["tag id", "method", "allowed by", "questions calling it (hand runs)",
             "questions calling it (draft_1 runs)", "draft_1 ok calls", "draft_1 call errors",
             "direct call on the drafts", "draft_1 with hand lineage and hierarchy",
             "direct call on hand tags"],
            [[x["tag"], x["method"], ", ".join(x["drafts"]),
              ", ".join(x["hand_run_questions"]) or "none",
              ", ".join(x["draft_1_run_questions"]) or "none", x["draft_1_ok_calls"],
              "; ".join(x["draft_1_errors"]) or "-",
              "; ".join(f"{n} {res(r)}" for n, r in x["draft_results"].items()),
              res(x["counterfactual"]) if x["counterfactual"] else "not allowed by draft_1",
              res(x["hand_result"])] for x in p]) + [""]
    cf_number = [x for x in p if x["counterfactual"] and x["counterfactual"]["status"] != "error"]
    key_err = [x for x in p if any("KeyError" in (r["explanation"] or "")
                                   for r in x["draft_results"].values())]
    L += [f"{len(tried)} of the {len(p)} pairs were called in a draft-1 run and {len(called)} "
          f"returned a value there. Called directly, {len(number)} of the {len(p)} pairs return a "
          f"number on the drafts as written: {len(key_err)} raise KeyError in src/semantics.py "
          f"(the tag allows a method the fundamentals code path does not implement; a second "
          f"robustness gap, not fixed here because src/ is frozen), and the rest stop first at the "
          f"missing lineage url or hierarchy. With draft_1's lineage and hierarchy taken from the "
          f"hand tags, {len(cf_number)} of the pairs draft_1 allows return a number where the hand "
          f"tags refuse: "
          + ("; ".join(f"{x['tag']} {x['method']} = {x['counterfactual']['value']} "
                       f"({x['counterfactual']['explanation']})" for x in cf_number) or "none")
          + ". The M4 count of 0 silent errors covers only what the 42 questions exercised, on "
          f"drafts whose other errors blocked these calls; it does not show that the permissive "
          f"errors are harmless.", ""]

    passed = [n for n in DRAFT_NAMES if a["m3"][n]["pass"]]
    errs = a["errors"]
    L += ["### Validator gap (proposals only; src/tags.py is not changed)", "",
          f"{len(passed)} of {len(DRAFT_NAMES)} drafts pass load_tags and check_tags_against_db, "
          f"so none of the {len(errs)} draft errors below (the M2 errors, plus a lineage key that "
          f"src/semantics.py needs) was caught. Rules a validator could enforce, checked against "
          f"the hand tags and each draft:", ""]
    hits = a["rule_hits"]
    L += _t(["proposed rule", "hand tags violating"] + [f"{n} entries flagged" for n in DRAFT_NAMES],
            [[name, len(hits["hand"][name]) or "0"]
             + [", ".join(hits[n][name]) or "none" for n in DRAFT_NAMES] for name, _, _ in RULES]) + [""]
    caught = [e for e in errs if e["caught_by"]]
    missed = [e for e in errs if not e["caught_by"]]
    on_flagged = [e for e in missed if e["entry_flagged"]]
    L += [f"A rule catches an error when it flags the entry and covers the error's field. "
          f"{len(caught)} of the {len(errs)} draft errors are caught that way. The other "
          f"{len(missed)} are caught by none of these rules and need a human reviewer; "
          f"{len(on_flagged)} of them are on an entry that a rule flags for another field, so a "
          f"reviewer opening the flagged entries would see them:", ""]
    L += (_t(["draft", "tag id", "field", "hand", "draft value", "entry flagged for another field"],
             [[e["draft"], e["tag"], e["field"], _j(e["hand"]), _j(e["draft_value"]),
               "yes" if e["entry_flagged"] else "no"] for e in missed])
          if missed else ["none"]) + [""]
    return L


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        _probe_main(sys.argv[2], json.loads(sys.argv[3]))
    else:
        print("\n".join(section_lines()))
