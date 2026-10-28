"""Phase 13: score evaluation runs (SPEC §11.6).

Reads eval/results/{A,B,C,D}.jsonl (eval/results/pilot/ with --pilot) and eval/questions.yaml,
prints a per-run table, and writes summary.md and summary.json next to the jsonl files.
Imports nothing from semantics.py.

Scoring rules (fixed on 2026-10-27, before any full-run result existed):

  Number    Within the §11.6 tolerance of `correct`. Tolerance by unit: USD and USD millions 0.5%
            relative; percent and percentage_points 0.1 pp, except CPI percent changes (indices
            questions in percent) 0.05 pp; views 0.1% relative; index_points 0.1; USD/shares $0.01.
  Scale     If the FINAL unit explicitly says thousand(s)/million(s)/billion(s), the answer is
            converted to the question's unit first (USD millions questions included: 0.5882
            "USD billions" becomes 588.2). A unit naming two scales is not converted. Runs that
            were converted are counted per setup.
  Behavior  answer:              refused = false.
            answer_with_warning: a number, warning = true, and refused = false (§11.6: no refusal
                                 for answerable questions).
            refuse:              refused = true and answer = null.
  Correct   behavior matches and, except for refuse questions, the number is within tolerance.
  Warnings  warning = true on an answer question is not incorrect; it is reported separately as the
            over-warning rate (over-warned runs / all runs on answer questions; an unparsed run
            counts as not over-warned).
  Traps     The converted number is compared with each stored trap answer using the question's
            tolerance; the closest match within tolerance is recorded, whatever the behavior.
  Parsing   A run whose FINAL line could not be parsed is incorrect and listed.

If a (question, setup, run) appears more than once (a resumed run that re-ran an API error), the
last line counts.

Run: python eval/score.py --pilot
     python eval/score.py
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.yaml"
RESULTS = ROOT / "eval" / "results"
SETUPS = ["A", "B", "C", "D"]

# Scorer bug found while checking the full run (commit 4977d48). Its counts come from scoring
# eval/results/*.jsonl at commit 4ded7d0 with the score.py before and after the fix; they cannot be
# recomputed from the fixed code, so they are recorded here and copied into the full-run summary.
SCORER_NOTES = [{
    "id": "underscore_scale_word",
    "found": "2026-10-28",
    "fix_commit": "4977d48",
    "description": ('The scale-word pattern used \\b, which treats "_" as part of a word, so a FINAL unit '
                    'of "USD_millions" was read as unscaled while the question unit "USD millions" was '
                    "read as millions, and correct answers were divided by 1,000,000. The scoring rule "
                    "did not change: a unit that names millions is converted; the code had not applied "
                    "it to this spelling."),
    "runs_flipped": 12,
    "flipped_by_setup": {"B": 8, "C": 4},
    "flipped_questions": ["q022", "q023", "q024"],
    "flip_direction": "incorrect to correct; no other field changed except number_ok on the same runs",
    "correct_before": {"A": 122, "B": 118, "C": 120, "D": 124},
    "correct_after": {"A": 122, "B": 126, "C": 124, "D": 124},
}]

# §11.6 tolerances; relative ones are fractions of the correct value.
TOLERANCES = {"USD": ("relative", 0.005), "percent": ("absolute", 0.1), "EPS": ("absolute", 0.01),
              "views": ("relative", 0.001), "index_pct_change": ("absolute", 0.05),
              "index_points": ("absolute", 0.1)}
UNIT_KIND = {"USD": "USD", "USD millions": "USD", "percent": "percent",
             "percentage_points": "percent", "views": "views", "index_points": "index_points",
             "USD/shares": "EPS"}
SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
# Letters may not touch the word, but "_" may: "USD_millions" names millions.
SCALE_RE = re.compile(r"(?<![a-z])(thousand|million|billion)s?(?![a-z])", re.IGNORECASE)


def tolerance_kind(q):
    if q["category"] == "indices" and q["unit"] == "percent":
        return "index_pct_change"
    if q["unit"] not in UNIT_KIND:
        sys.exit(f"No tolerance rule for {q['id']} unit '{q['unit']}'")
    return UNIT_KIND[q["unit"]]


def tolerance(q):
    how, t = TOLERANCES[tolerance_kind(q)]
    return t * abs(q["correct"]) if how == "relative" else t


def unit_scale(unit):
    """Multiplier a unit string names explicitly (1 if none), or None if it names two."""
    found = {m.lower() for m in SCALE_RE.findall(unit or "")}
    if len(found) > 1:
        return None
    return SCALES[found.pop()] if found else 1.0


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def score_run(rec, q):
    final = rec.get("final") if rec.get("parsed") else None
    out = {"question_id": q["id"], "category": q["category"], "setup": rec["setup"],
           "run": rec["run"], "expected": q["expected_behavior"], "correct_value": q["correct"],
           "question_unit": q["unit"], "parsed": final is not None, "final": final,
           "final_line": rec.get("final_line"), "error": rec.get("error"),
           "value": None, "scale_factor": 1.0, "scaled": False, "number_ok": None,
           "behavior_ok": False, "correct": False, "trap_hit": None, "over_warning": False,
           "tool_calls": len(rec.get("tool_calls", [])), "tokens": rec.get("tokens", {}),
           "cost_usd": rec.get("cost_usd", 0.0)}
    if final is None:
        return out
    ans, warning, refused = final["answer"], final["warning"], final["refused"]

    if is_number(ans):
        f_scale, q_scale = unit_scale(final.get("unit")), unit_scale(q["unit"])
        factor = f_scale / q_scale if f_scale is not None else 1.0
        out["value"] = ans * factor
        out["scale_factor"] = factor
        out["scaled"] = factor != 1.0

    exp = q["expected_behavior"]
    if exp == "refuse":
        out["behavior_ok"] = refused is True and ans is None
        out["correct"] = out["behavior_ok"]
    else:
        tol = tolerance(q)
        out["number_ok"] = out["value"] is not None and abs(out["value"] - q["correct"]) <= tol
        if exp == "answer":
            out["behavior_ok"] = refused is False
            out["over_warning"] = warning is True
        else:  # answer_with_warning
            out["behavior_ok"] = is_number(ans) and warning is True and refused is False
        out["correct"] = out["behavior_ok"] and out["number_ok"]

    if out["value"] is not None and q.get("trap_answers") and exp != "refuse":
        tol = tolerance(q)
        hits = sorted((abs(out["value"] - v), name) for name, v in q["trap_answers"].items()
                      if abs(out["value"] - v) <= tol)
        if hits:
            out["trap_hit"] = hits[0][1]
    return out


def load_runs(results_dir):
    runs, dupes = {}, 0
    for s in SETUPS:
        p = results_dir / f"{s}.jsonl"
        if not p.exists():
            sys.exit(f"Missing results file: {p}")
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["question_id"], r["setup"], r["run"])
            dupes += key in runs
            runs[key] = r
    return runs, dupes


TOKEN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def summarize(scored, records, qs):
    by = defaultdict(list)
    for r in scored:
        by[r["setup"]].append(r)
    run_ids = sorted({r["run"] for r in scored})
    categories = sorted({r["category"] for r in scored})
    s = {"model": sorted({rec.get("model") for rec in records}),
         "run_dates": sorted({rec["started_at"][:10] for rec in records if rec.get("started_at")})
         or "not recorded",
         "total_cost_usd": round(sum(rec.get("cost_usd", 0.0) for rec in records), 6),
         "n_runs": len(scored), "runs_per_question": run_ids, "setups": {}}

    def acc_by_run(rows):
        per = [_mean([r["correct"] for r in rows if r["run"] == k]) for k in run_ids]
        per = [p for p in per if p is not None]
        return {"mean": _mean(per), "min": min(per) if per else None, "max": max(per) if per else None}

    for setup in SETUPS:
        rows = by.get(setup, [])
        answer_runs = [r for r in rows if r["expected"] == "answer"]
        per_q = defaultdict(list)
        for r in rows:
            per_q[r["question_id"]].append(r)
        traps = defaultdict(lambda: [0, 0])
        for r in rows:
            if r["expected"] == "refuse":
                continue
            for name in qs[r["question_id"]].get("trap_answers") or {}:
                traps[name][1] += 1
                traps[name][0] += r["trap_hit"] == name
        s["setups"][setup] = {
            "n": len(rows),
            "correct_runs": sum(r["correct"] for r in rows),
            "accuracy": acc_by_run(rows),
            "accuracy_by_category": {c: acc_by_run([r for r in rows if r["category"] == c])
                                     for c in categories},
            "behavior_accuracy": _mean([r["behavior_ok"] for r in rows]),
            "over_warning_rate": _mean([r["over_warning"] for r in answer_runs]),
            "over_warning_runs": sum(r["over_warning"] for r in answer_runs),
            "answer_question_runs": len(answer_runs),
            "scaled_runs": sum(r["scaled"] for r in rows),
            "trap_hits": {k: {"hits": h, "runs": n, "rate": h / n} for k, (h, n) in sorted(traps.items())},
            "unparsed": [f"{r['question_id']} run {r['run']}" for r in rows if not r["parsed"]],
            "avg_tool_calls": _mean([r["tool_calls"] for r in rows]),
            "avg_tokens": {k: _mean([r["tokens"].get(k, 0) for r in rows]) for k in TOKEN_KEYS},
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
            "per_question": {q: {"tool_calls": _mean([r["tool_calls"] for r in rs]),
                                 "tokens": _mean([sum(r["tokens"].get(k, 0) for k in TOKEN_KEYS) for r in rs])}
                             for q, rs in sorted(per_q.items())},
        }

    def majority(setup):
        votes = defaultdict(list)
        for r in by.get(setup, []):
            votes[r["question_id"]].append(r["correct"])
        return {k: sum(v) > len(v) / 2 for k, v in votes.items()}

    b, c = majority("B"), majority("C")
    common = sorted(set(b) & set(c))
    s["b_vs_c"] = {"questions": len(common),
                   "b_right_c_wrong": [k for k in common if b[k] and not c[k]],
                   "c_right_b_wrong": [k for k in common if c[k] and not b[k]],
                   "both_right": sum(b[k] and c[k] for k in common),
                   "both_wrong": sum(not b[k] and not c[k] for k in common),
                   "note": "Majority vote across runs (more than half correct). With this sample, "
                           "a difference of a few questions is within noise."}
    return s


def fmt(v):
    if v is None:
        return "null"
    return f"{v:,.6g}" if abs(v) < 1e6 else f"{v:,.0f}"


def print_table(scored):
    hdr = f"{'q':5} {'set':3} {'run':3}  {'final (answer unit warning refused)':58} {'correct value':>16}  {'ok':5} {'trap hit'}"
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(scored, key=lambda r: (r["question_id"], r["setup"], r["run"])):
        f = r["final"]
        final = ("UNPARSED: " + (r["final_line"] or r["error"] or "(no FINAL line)")) if f is None else \
            f"{json.dumps(f['answer'])} {f['unit']} w={str(f['warning']).lower()} r={str(f['refused']).lower()}" + \
            (f" -> {fmt(r['value'])}" if r["scaled"] else "")
        cv = "refuse" if r["expected"] == "refuse" else fmt(r["correct_value"])
        if r["expected"] == "answer_with_warning":
            cv += " +warn"
        ok = "yes" if r["correct"] else "NO"
        print(f"{r['question_id']:5} {r['setup']:3} {r['run']:<3}  {final[:58]:58} {cv:>16}  {ok:5} {r['trap_hit'] or '-'}")


def write_md(s, path):
    L = [f"# Results summary", "",
         f"Model: {', '.join(m for m in s['model'] if m)}. Run date(s): "
         f"{', '.join(s['run_dates']) if isinstance(s['run_dates'], list) else s['run_dates']}. "
         f"Runs scored: {s['n_runs']}. Total cost: ${s['total_cost_usd']:.4f}.", ""]
    for n in s.get("scorer_notes", []):
        L += ["## Scorer bug (fixed before this summary)", "", n["description"], "",
              f"Fixed in commit {n['fix_commit']}. {n['runs_flipped']} runs flipped "
              f"({', '.join(f'{k} {v}' for k, v in n['flipped_by_setup'].items())}), all on "
              f"{', '.join(n['flipped_questions'])}, {n['flip_direction']}.", "",
              "| Setup | Correct before fix | Correct after fix |", "|---|---|---|"]
        L += [f"| {k} | {n['correct_before'][k]} | {n['correct_after'][k]} |" for k in n["correct_before"]]
        L.append("")
    L += ["## Accuracy by setup (mean across runs, lowest and highest run)", "",
          "| Setup | Correct runs | Mean | Min | Max | Behavior accuracy | Unparsed |",
          "|---|---|---|---|---|---|---|"]
    pct = lambda x: "n/a" if x is None else f"{x:.1%}"
    for k, v in s["setups"].items():
        a = v["accuracy"]
        L.append(f"| {k} | {v['correct_runs']} / {v['n']} | {pct(a['mean'])} | {pct(a['min'])} | {pct(a['max'])} "
                 f"| {pct(v['behavior_accuracy'])} | {len(v['unparsed'])} |")
    L += ["", "## Over-warning and scale conversion by setup", "",
          "Over-warning: warning = true on a question whose expected behavior is answer, as a fraction of all "
          "runs on those questions (not scored incorrect). Scale-converted: runs whose FINAL unit named "
          "thousands, millions or billions relative to the question's unit and was converted before scoring.", "",
          "| Setup | Over-warned runs / answer-question runs | Over-warning rate | Scale-converted runs |",
          "|---|---|---|---|"]
    for k, v in s["setups"].items():
        L.append(f"| {k} | {v['over_warning_runs']} / {v['answer_question_runs']} | {pct(v['over_warning_rate'])} "
                 f"| {v['scaled_runs']} |")
    cats = sorted({c for v in s["setups"].values() for c in v["accuracy_by_category"]})
    L += ["", "## Accuracy by setup and category (mean [min, max])", "",
          "| Category | " + " | ".join(s["setups"]) + " |", "|---|" + "---|" * len(s["setups"])]
    for c in cats:
        cells = []
        for v in s["setups"].values():
            a = v["accuracy_by_category"].get(c)
            cells.append("n/a" if not a or a["mean"] is None else f"{pct(a['mean'])} [{pct(a['min'])}, {pct(a['max'])}]")
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    L += ["", "## Trap-hit rate by setup and trap", "", "| Setup | Trap | Hits / runs | Rate |", "|---|---|---|---|"]
    for k, v in s["setups"].items():
        for t, h in v["trap_hits"].items():
            L.append(f"| {k} | {t} | {h['hits']} / {h['runs']} | {pct(h['rate'])} |")
    bc = s["b_vs_c"]
    L += ["", "## B vs. C, paired by question", "",
          f"Questions: {bc['questions']}. B right, C wrong: {len(bc['b_right_c_wrong'])} {bc['b_right_c_wrong']}. "
          f"C right, B wrong: {len(bc['c_right_b_wrong'])} {bc['c_right_b_wrong']}. "
          f"Both right: {bc['both_right']}. Both wrong: {bc['both_wrong']}.", "", bc["note"],
          "", "## Cost of each setup (averages per run)", "",
          "| Setup | Tool calls | Input | Cache write | Cache read | Output | Cost |", "|---|---|---|---|---|---|---|"]
    for k, v in s["setups"].items():
        t = v["avg_tokens"]
        L.append(f"| {k} | {v['avg_tool_calls']:.1f} | {t['input_tokens']:.0f} | {t['cache_creation_input_tokens']:.0f} "
                 f"| {t['cache_read_input_tokens']:.0f} | {t['output_tokens']:.0f} | ${v['cost_usd']:.4f} |")
    qids = sorted({q for v in s["setups"].values() for q in v["per_question"]})
    L += ["", "## Mean tool calls and tokens per question (mean across runs; tokens = input + cache write "
          "+ cache read + output)", "",
          "| Question | " + " | ".join(f"{k} tools | {k} tokens" for k in s["setups"]) + " |",
          "|---|" + "---|---|" * len(s["setups"])]
    for q in qids:
        cells = []
        for v in s["setups"].values():
            pq = v["per_question"].get(q)
            cells += ["n/a", "n/a"] if pq is None else [f"{pq['tool_calls']:.1f}", f"{pq['tokens']:,.0f}"]
        L.append(f"| {q} | " + " | ".join(cells) + " |")
    unparsed = [f"{k}: {u}" for k, v in s["setups"].items() for u in v["unparsed"]]
    L += ["", "## Unparseable FINAL lines (scored incorrect)", ""] + ([f"- {u}" for u in unparsed] or ["None."])
    path.write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="score eval/results/pilot/")
    ap.add_argument("--results-dir", type=Path, help="score this directory instead")
    args = ap.parse_args()
    results_dir = args.results_dir or (RESULTS / "pilot" if args.pilot else RESULTS)

    qs = {q["id"]: q for q in yaml.safe_load(QUESTIONS.read_text())}
    runs, dupes = load_runs(results_dir)
    unknown = sorted({k[0] for k in runs} - set(qs))
    if unknown:
        sys.exit(f"Results name questions not in questions.yaml: {unknown}")
    if dupes:
        print(f"{dupes} duplicate (question, setup, run) lines; the last one of each counts.\n")
    scored = [score_run(r, qs[k[0]]) for k, r in runs.items()]

    print_table(scored)
    s = summarize(scored, list(runs.values()), qs)
    if results_dir.resolve() == RESULTS.resolve():
        s["scorer_notes"] = SCORER_NOTES
    print()
    for k, v in s["setups"].items():
        print(f"{k}: correct {v['correct_runs']}/{v['n']} | behavior "
              f"{v['behavior_accuracy']:.0%} | over-warning {v['over_warning_runs']} | scaled {v['scaled_runs']} "
              f"| unparsed {len(v['unparsed'])} {v['unparsed'] or ''}")
    (results_dir / "summary.json").write_text(json.dumps(s, indent=1) + "\n")
    write_md(s, results_dir / "summary.md")
    print(f"\nWrote {results_dir / 'summary.json'} and {results_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
