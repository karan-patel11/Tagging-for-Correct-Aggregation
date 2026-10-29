"""Per-record scoring of setup D runs with the frozen eval/score.py (score_run), and the check that
this path reproduces the hand-tag D result before any paid run (PREREG design decision 7).

eval/score.py's CLI only reads {A,B,C,D}.jsonl, so D_autotag.jsonl is scored by applying its
score_run to each record, with its rule that the last line of a (question, setup, run) counts.

Run: python followup/autotag/score_d.py --check
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "eval") not in sys.path:
    sys.path.insert(0, str(ROOT / "eval"))

import yaml  # noqa: E402

import score  # noqa: E402  (frozen eval/score.py; imports nothing from semantics.py)

HAND_D = ROOT / "eval" / "results" / "D.jsonl"
HAND_SUMMARY = ROOT / "eval" / "results" / "summary.json"


def questions():
    return {q["id"]: q for q in yaml.safe_load(score.QUESTIONS.read_text())}


def load_records(path):
    """Records keyed by (question_id, run); the last line of a key counts, as in score.load_runs."""
    runs = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            runs[(r["question_id"], r["run"])] = r
    return runs


def score_records(path):
    qs = questions()
    runs = load_records(path)
    scored = {k: score.score_run(r, qs[k[0]]) for k, r in runs.items()}
    return scored, runs, qs


def correct_by_question(scored):
    out = defaultdict(int)
    for (qid, _), s in scored.items():
        out[qid] += s["correct"]
    return dict(out)


def _cli_outcomes():
    """Per-run correct flags for setup D as printed by eval/score.py itself, run on a scratch copy
    of eval/results (so nothing under eval/ is written)."""
    with tempfile.TemporaryDirectory() as tmp:
        for s in score.SETUPS:
            shutil.copy(ROOT / "eval" / "results" / f"{s}.jsonl", Path(tmp) / f"{s}.jsonl")
        out = subprocess.run([sys.executable, str(ROOT / "eval" / "score.py"), "--results-dir", tmp],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
    flags = {}
    for line in out.splitlines():
        m = re.match(r"^(q\d{3})\s+D\s+(\d+)\s", line)
        if m:
            flags[(m[1], int(m[2]))] = line.rstrip().split()[-2] == "yes"
    return flags


def check_scoring_path():
    scored, runs, qs = score_records(HAND_D)
    n, correct = len(scored), sum(s["correct"] for s in scored.values())
    print(f"per-record path on eval/results/D.jsonl: {correct}/{n} correct")
    assert (correct, n) == (124, 126), f"expected 124/126, got {correct}/{n}"

    # Every D statistic in the published summary, recomputed from the per-record scores.
    mine = score.summarize(list(scored.values()), list(runs.values()), qs)["setups"]["D"]
    published = json.loads(HAND_SUMMARY.read_text())["setups"]["D"]
    mine = json.loads(json.dumps(mine))
    diffs = [k for k in published if mine.get(k) != published[k]]
    print(f"summary.json setups.D: {len(published)} fields compared, {len(diffs)} differ {diffs or ''}")
    assert not diffs, f"summary fields differ: {diffs}"

    # Per-run outcomes against eval/score.py's own per-run table.
    cli = _cli_outcomes()
    mine_flags = {k: s["correct"] for k, s in scored.items()}
    assert len(cli) == 126, f"score.py printed {len(cli)} D runs"
    mismatched = sorted(k for k in cli if cli[k] != mine_flags.get(k))
    print(f"per-run outcomes vs eval/score.py table: {len(cli)} runs compared, {len(mismatched)} differ")
    assert not mismatched, f"per-run outcomes differ: {mismatched}"

    wrong = sorted(f"{q} run {r}" for (q, r), s in scored.items() if not s["correct"])
    print(f"incorrect runs: {wrong}")
    print(f"unparsed (summary.md lists 'D: q030 run 1'): {mine['unparsed']}")
    per_q = correct_by_question(scored)
    print("questions with fewer than 3 correct runs: "
          f"{ {q: c for q, c in sorted(per_q.items()) if c < 3} }")
    return scored


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="reproduce hand-tag D (124/126)")
    args = ap.parse_args()
    if args.check:
        check_scoring_path()
        print("SCORING PATH CHECK: PASS")
