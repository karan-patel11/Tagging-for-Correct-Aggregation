"""Deterministic replay after the engine hardening (src/semantics.py, src/tags.py). No model calls.

  (a) Every tool call recorded in eval/results/D.jsonl (hand tags) is re-executed through
      mcp_server.call_tool on the current engine and compared with the recorded output string.
      Any difference in status, value or unit stops the replay (exit 1).
  (b) Every tool call recorded in followup/autotag/results/D_autotag.jsonl is re-executed with the
      draft_1 tags (autotag_env.install, a fresh process); old and new outputs are classed as
      number / ok without a number / clean error / exception.
  (c) The 12 permissive tag/method pairs and the counterfactual of followup/autotag/RESULTS.md
      (draft_1 with the hand lineage and hierarchy), on the engine the results were produced with
      (src/ at RESULTS_COMMIT, exported from git into a temporary directory) and on the current one.
  (d) The new validator rules (tags.semantic_rule_violations) on drafts 1-3: how many of the
      draft errors (the M2 errors plus a missing lineage key semantics.py needs) they catch.

Writes followup/engine_fix/REPLAY.md and followup/engine_fix/replay.json.

Run: python followup/engine_fix/replay.py
"""
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTOTAG = ROOT / "followup" / "autotag"
HAND_D = ROOT / "eval" / "results" / "D.jsonl"
DRAFT_D = AUTOTAG / "results" / "D_autotag.jsonl"
HAND_TAGS = ROOT / "tags" / "tags.yaml"
DRAFTS = {n: AUTOTAG / "drafts" / f"{n}.yaml" for n in ("draft_1", "draft_2", "draft_3")}
RESULTS_COMMIT = "bbc6310"  # the main results (eval/results) were produced with src/ at this commit
SRC_FILES = ["semantics.py", "tags.py", "mcp_server.py", "tool_specs.py"]
OUT_MD, OUT_JSON = HERE / "REPLAY.md", HERE / "replay.json"
# Arguments for a direct aggregate call on a permissive pair, per table (as in
# followup/autotag/root_causes.py).
PROBE_ARGS = {"fundamentals": (["CMG"], "FY2025"), "macro_monthly": ([], "2025-01:2025-06"),
              "brand_attention_daily": (["KFC"], "CY2025Q1")}
EXC = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(Error|Exception): ")
# A call Python rejects before the engine runs (an argument the tool does not have, or one missing).
ARG_ERR = re.compile(r"^TypeError: \w+\(\) (got an unexpected keyword argument|missing \d+ required)")
# The fields each rule's violation covers, for matching a violation to a draft error.
RULE_FIELDS = {"flow": {"additive_over_time", "time_rollup"},
               "sum_over_time": {"additive_over_time", "valid_methods"},
               "sum_across_entities": {"additive_over_entities", "valid_methods"},
               "hierarchy": {"hierarchy"}, "lineage": {"lineage.url", "lineage.url_template"}}


def records(path):
    """Records keyed by (question_id, run); the last line of a key counts (eval/score.py's rule)."""
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["question_id"], r["run"])] = r
    return out


def tool_calls(path):
    return [(qid, run, i, tc) for (qid, run), r in sorted(records(path).items())
            for i, tc in enumerate(r["tool_calls"])]


def out_class(output):
    """number / ok without a number / clean error / exception, for one tool output string."""
    try:
        env = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return "unparseable"
    if env.get("status") == "error":
        text = env.get("explanation") or ""
        if ARG_ERR.match(text):
            return "argument error"
        return "exception" if EXC.match(text) else "clean error"
    v = env.get("value")
    return "number" if isinstance(v, (int, float)) and not isinstance(v, bool) else "ok without a number"


# ---------- child processes ----------

def _child_calls(calls):
    """Run [(name, input)] through mcp_server.call_tool as run_eval.execute_tool does."""
    import mcp_server
    return [[json.dumps(env := mcp_server.call_tool(name, args)), env.get("status") == "error"]
            for name, args in calls]


def _child_main(mode, src, tags_path, payload):
    calls = json.loads(Path(payload).read_text())
    if mode == "autotag":  # (b): the follow-up's own loader, current src/
        sys.path.insert(0, str(AUTOTAG))
        import autotag_env
        autotag_env.install(tags_path)
    else:  # (c): any src/ directory, tags file swapped in before semantics is imported
        sys.path.insert(0, src)
        import tags
        tags.load_tags.__defaults__ = (Path(tags_path),)
    import semantics
    assert Path(semantics.__file__).resolve().parent == Path(src).resolve(), semantics.__file__
    print(json.dumps(_child_calls(calls)))


def child(mode, src, tags_path, calls):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(calls, f)
    out = subprocess.run([sys.executable, str(Path(__file__)), "--child", mode, str(src),
                          str(tags_path), f.name], cwd=ROOT, capture_output=True, text=True)
    Path(f.name).unlink()
    if out.returncode:
        sys.exit(f"child process failed:\n{out.stderr}")
    return json.loads(out.stdout.strip().splitlines()[-1])


# ---------- (a) hand-tag replay ----------

def replay_hand():
    sys.path.insert(0, str(ROOT / "src"))
    import mcp_server
    calls = tool_calls(HAND_D)
    diffs = []
    for qid, run, i, tc in calls:
        new = json.dumps(mcp_server.call_tool(tc["name"], tc["input"]))
        new_err = json.loads(new).get("status") == "error"
        if new != tc["output"] or new_err != tc["is_error"]:
            old_env, new_env = json.loads(tc["output"]), json.loads(new)
            fields = sorted(k for k in set(old_env) | set(new_env) if old_env.get(k) != new_env.get(k))
            diffs.append({"question_id": qid, "run": run, "call": i, "tool": tc["name"],
                          "input": tc["input"], "fields": fields,
                          "critical": bool({"status", "value", "unit"} & set(fields))})
    return {"calls": len(calls), "identical": len(calls) - len(diffs), "different": len(diffs),
            "critical": sum(d["critical"] for d in diffs), "diffs": diffs,
            "by_tool": dict(Counter(tc["name"] for *_, tc in calls))}


# ---------- (b) draft_1 replay ----------

def replay_draft():
    calls = tool_calls(DRAFT_D)
    new = child("autotag", ROOT / "src", DRAFTS["draft_1"], [[tc["name"], tc["input"]] for *_, tc in calls])
    pairs = Counter()
    changed = []
    for (qid, run, i, tc), (out, _) in zip(calls, new):
        a, b = out_class(tc["output"]), out_class(out)
        pairs[(a, b)] += 1
        if a in ("exception", "argument error") or (a == "number") != (b == "number"):
            changed.append({"question_id": qid, "run": run, "tool": tc["name"],
                            "metric": tc["input"].get("metric_id") or tc["input"].get("metric"),
                            "method": tc["input"].get("method"), "old": a, "new": b,
                            "old_explanation": json.loads(tc["output"]).get("explanation"),
                            "new_explanation": json.loads(out).get("explanation")})
    return {"calls": len(calls), "pairs": {f"{a} -> {b}": n for (a, b), n in sorted(pairs.items())},
            "old_exceptions": sum(n for (a, _), n in pairs.items() if a == "exception"),
            "new_exceptions": sum(n for (_, b), n in pairs.items() if b == "exception"),
            "changed": changed}


# ---------- (c) permissive pairs, before and after ----------

def _entries(path):
    return yaml.safe_load(Path(path).read_text())


def permissive_pairs(hand, drafts):
    out = []
    for tid, h in hand.items():
        if h["semantic_type"] not in ("flow", "stock", "ratio", "per_share", "index", "count"):
            continue
        by = defaultdict(list)
        for n, d in drafts.items():
            for m in sorted(set(d.get(tid, {}).get("valid_methods") or []) - set(h.get("valid_methods") or [])):
                by[m].append(n)
        out += [{"tag": tid, "table": h["table"], "method": m, "drafts": ns} for m, ns in sorted(by.items())]
    return out


def replay_permissive(old_src):
    hand = {e["id"]: e for e in _entries(HAND_TAGS)}
    drafts = {n: {e["id"]: e for e in _entries(p)} for n, p in DRAFTS.items()}
    pairs = permissive_pairs(hand, drafts)
    with tempfile.TemporaryDirectory() as tmp:
        cf_path = Path(tmp) / "draft_1_hand_lineage_hierarchy.yaml"
        cf_path.write_text(yaml.safe_dump(
            [dict(e, lineage=hand[e["id"]]["lineage"], hierarchy=hand[e["id"]].get("hierarchy"))
             for e in _entries(DRAFTS["draft_1"])], sort_keys=False))
        targets = {**DRAFTS, "counterfactual": cf_path}
        results = {}
        for label, src in (("before", old_src), ("after", ROOT / "src")):
            for t, path in targets.items():
                use = [p for p in pairs if (t == "counterfactual" and "draft_1" in p["drafts"])
                       or t in p["drafts"]]
                calls = [["aggregate", {"metric_id": p["tag"], "entities": PROBE_ARGS[p["table"]][0],
                                        "period": PROBE_ARGS[p["table"]][1], "method": p["method"]}]
                         for p in use]
                for p, (out, _) in zip(use, child("plain", src, path, calls) if calls else []):
                    env = json.loads(out)
                    results[(label, t, p["tag"], p["method"])] = {
                        "class": out_class(out), "value": env.get("value"),
                        "explanation": env.get("explanation")}
    rows = []
    for p in pairs:
        row = dict(p)
        for label in ("before", "after"):
            row[label] = {t: results[(label, t, p["tag"], p["method"])]
                          for t in list(DRAFTS) + ["counterfactual"]
                          if (label, t, p["tag"], p["method"]) in results}
        rows.append(row)
    count = lambda label: sum(r["class"] == "number" for row in rows for r in row[label].values())
    return {"pairs": rows, "numbers_before": count("before"), "numbers_after": count("after"),
            "calls_per_engine": sum(len(row["after"]) for row in rows)}


# ---------- (d) validator on the drafts ----------

def validator_on_drafts():
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(AUTOTAG))
    import score_tags  # followup scorer: M2 errors, read only
    import tags
    hand_list = _entries(HAND_TAGS)
    hand = {e["id"]: e for e in hand_list}
    lineage_key = tags.LINEAGE_KEY
    per = {}
    for n, path in DRAFTS.items():
        entries = _entries(path)
        d_by = {e["id"]: e for e in entries}
        errors = [(tid, e["field"]) for tid, errs in score_tags.m2(hand_list, entries).items() for e in errs]
        for tid, h in hand.items():
            key = lineage_key.get(h["table"])
            if (h["semantic_type"] in tags.MEASURE_TYPES and key and h["lineage"].get(key)
                    and not (d_by.get(tid, {}).get("lineage") or {}).get(key)):
                errors.append((tid, f"lineage.{key}"))
        viol = tags.semantic_rule_violations(tags.load_tags(path))
        caught = [(tid, f) for tid, f in errors
                  if any(v_tid == tid and f in RULE_FIELDS[rule] for v_tid, rule, _ in viol)]
        per[n] = {"errors": len(errors), "caught": len(caught), "violations": len(viol),
                  "by_rule": dict(Counter(rule for _, rule, _ in viol)),
                  "missed": sorted(f"{tid} {f}" for tid, f in set(errors) - set(caught))}
    hand_viol = tags.semantic_rule_violations(tags.load_tags(HAND_TAGS))
    return {"drafts": per, "errors": sum(v["errors"] for v in per.values()),
            "caught": sum(v["caught"] for v in per.values()), "hand_violations": len(hand_viol)}


# ---------- report ----------

def table(header, rows):
    return (["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
            + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def cell(r):
    if r["class"] == "number":
        return f"number {r['value']}"
    return f"{r['class']}: {r['explanation']}"


def write(a, b, c, d):
    L = ["# Replay after the engine hardening", "",
         "Generated by `followup/engine_fix/replay.py`; no model calls. The engine changes are in "
         "`src/semantics.py` (each aggregate code path refuses methods it does not implement and "
         "returns a clean error for missing tag metadata) and `src/tags.py` (five validator rules, "
         "`check_semantic_rules`). The main results were produced with `src/` at "
         f"`{RESULTS_COMMIT}`.", ""]
    L += ["## (a) Hand tags: every recorded setup D tool call, re-executed", "",
          f"`eval/results/D.jsonl`: {a['calls']} tool calls re-executed through "
          f"`mcp_server.call_tool` on the current engine and compared with the recorded output "
          f"string. Identical: {a['identical']} of {a['calls']}. Different: {a['different']} "
          f"({a['critical']} in status, value or unit).", ""]
    L += table(["tool", "calls"], sorted(a["by_tool"].items())) + [""]
    if a["diffs"]:
        L += table(["question", "run", "call", "tool", "input", "fields that differ"],
                   [[x["question_id"], x["run"], x["call"], x["tool"], json.dumps(x["input"]),
                     ", ".join(x["fields"])] for x in a["diffs"]]) + [""]
    L += ["## (b) Draft 1: every tool call of the follow-up's setup D run, re-executed", "",
          f"`followup/autotag/results/D_autotag.jsonl`: {b['calls']} tool calls re-executed with "
          f"the draft_1 tags through `autotag_env.install()`. Exceptions (an error envelope whose "
          f"explanation is a Python exception raised inside the engine): {b['old_exceptions']} "
          f"recorded, {b['new_exceptions']} on the current engine. \"argument error\" is a call "
          f"Python rejected before the engine ran (an argument the tool does not have); "
          f"mcp_server.call_tool returns it as a tool error, before and after.", ""]
    L += table(["recorded output -> current output", "calls"], list(b["pairs"].items())) + [""]
    if b["changed"]:
        L += ["Calls whose class changed to or from a number, or that were an exception:", ""]
        agg = Counter((x["tool"], x["metric"], x["method"], x["old"], x["new"], x["new_explanation"])
                      for x in b["changed"])
        L += table(["tool", "metric", "method", "recorded", "current", "current explanation", "calls"],
                   [[*k, n] for k, n in sorted(agg.items(), key=str)]) + [""]
    L += ["## (c) Permissive pairs and the counterfactual, before and after", "",
          f"The {len(c['pairs'])} tag/method pairs a draft allows and the hand tag forbids, called "
          f"directly (`aggregate`) on each draft that allows the pair and on the counterfactual "
          f"(draft_1 with the hand tags' lineage and hierarchy; only pairs draft_1 allows). Before: "
          f"`src/` at `{RESULTS_COMMIT}`. After: the current `src/`. Arguments: "
          + "; ".join(f"{t}: entities {e}, period {p}" for t, (e, p) in PROBE_ARGS.items())
          + f". Numbers returned: {c['numbers_before']} before, {c['numbers_after']} after, out of "
          f"{c['calls_per_engine']} calls per engine.", ""]
    rows = []
    for row in c["pairs"]:
        for t in row["after"]:
            rows.append([row["tag"], row["method"], t, cell(row["before"][t]), cell(row["after"][t])])
    L += table(["tag id", "method", "tags", "before", "after"], rows) + [""]
    after_numbers = [(row["tag"], row["method"], t, r["value"], r["explanation"])
                     for row in c["pairs"] for t, r in row["after"].items() if r["class"] == "number"]
    if after_numbers:
        L += ["Numbers after the hardening: "
              + "; ".join(f"{tid} {m} on {t} = {v} ({x})" for tid, m, t, v, x in after_numbers)
              + ". Each is a method the code path implements and the tags in use allow; the hand "
              "tags forbid it. The engine follows the tags it is given, so it cannot detect a "
              "permissive tag; that needs review or a validator rule (none of the five covers "
              "this case).", ""]
    L += ["`followup/autotag/RESULTS.md` is not regenerated here. Its \"Permissive errors not "
          "exercised\" table calls the engine live (followup/autotag/root_causes.py), so "
          "rebuilding it now would show the \"after\" column above in place of the "
          f"`{RESULTS_COMMIT}` behaviour it recorded; its pre-registered sections (M1-M4) read "
          "recorded files only and do not change.", ""]
    L += ["## (d) The new validator rules on drafts 1-3", "",
          f"Hand tags: {d['hand_violations']} violations. A draft error (an M2 error, or a lineage "
          f"key src/semantics.py needs) counts as caught when a rule flags that entry and the rule "
          f"covers the error's field. Caught: {d['caught']} of {d['errors']}.", ""]
    L += table(["draft", "errors", "caught", "rule violations", "by rule", "not caught"],
               [[n, v["errors"], v["caught"], v["violations"],
                 ", ".join(f"{k} {x}" for k, x in sorted(v["by_rule"].items())),
                 "; ".join(v["missed"])] for n, v in d["drafts"].items()]) + [""]
    L += ["The five rules were derived from these same drafts' errors (followup/autotag/RESULTS.md, "
          "\"Validator gap\"), so (d) is not a test on new data: it shows the rules do what they "
          "were written to do, not how well they generalize.", ""]
    OUT_MD.write_text("\n".join(L))
    OUT_JSON.write_text(json.dumps({
        "results_commit": RESULTS_COMMIT,
        "hand": {k: a[k] for k in ("calls", "identical", "different", "critical")},
        "draft_1": {k: b[k] for k in ("calls", "old_exceptions", "new_exceptions")} | {"pairs": b["pairs"]},
        "permissive": {k: c[k] for k in ("numbers_before", "numbers_after", "calls_per_engine")}
                      | {"pairs": len(c["pairs"])},
        "validator": {k: d[k] for k in ("errors", "caught", "hand_violations")}}, indent=1) + "\n")


def main():
    # src/ at RESULTS_COMMIT, laid out as <tmp>/src next to a link to the real data/ (semantics.py
    # finds the warehouse relative to its own file).
    with tempfile.TemporaryDirectory() as tmp:
        old_src = Path(tmp) / "src"
        old_src.mkdir()
        (Path(tmp) / "data").symlink_to(ROOT / "data")
        for f in SRC_FILES:
            (old_src / f).write_text(subprocess.run(
                ["git", "show", f"{RESULTS_COMMIT}:src/{f}"], cwd=ROOT, capture_output=True,
                text=True, check=True).stdout)
        c = replay_permissive(old_src)
    b = replay_draft()
    d = validator_on_drafts()
    a = replay_hand()
    write(a, b, c, d)
    print(f"(a) hand: {a['identical']}/{a['calls']} identical, {a['different']} different, "
          f"{a['critical']} in status/value/unit")
    print(f"(b) draft_1: {b['calls']} calls; exceptions {b['old_exceptions']} -> {b['new_exceptions']}")
    print(f"(c) permissive: numbers {c['numbers_before']} -> {c['numbers_after']} "
          f"of {c['calls_per_engine']} calls")
    print(f"(d) validator: {d['caught']}/{d['errors']} draft errors caught; hand violations "
          f"{d['hand_violations']}")
    print(f"wrote {OUT_MD.relative_to(ROOT)} and {OUT_JSON.relative_to(ROOT)}")
    if a["critical"]:
        print("STOP: a recorded hand-tag call differs in status, value or unit")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child_main(*sys.argv[2:6])
    else:
        main()
