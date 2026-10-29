"""Why did runs warn on questions whose answer key expects no caveat? A keyword heuristic.

For each setup, takes the runs with warning = true on questions whose expected_behavior is "answer"
(the runs eval/score.py counts as over-warning) and checks whether the run's final model text (the
last non-empty text block, which holds the FINAL line) matches PATTERN, a fixed list of words that
refer to filing dates, accession numbers, comparatives or retrieval metadata.

This is a keyword heuristic, not a judgement of each caveat: a match means the text mentions one of
these words, not that the warning is about them alone. report/over_warning_overrides.json lists
manual corrections: runs whose full final text was read and found to be misclassified by the
pattern. Each correction is applied and recorded in the output; a correction that does not change
the keyword result, or names a run that is not a warning run, fails the script.

Reads eval/results/{A,B,C,D}.jsonl, eval/questions.yaml and report/over_warning_overrides.json.
Writes report/over_warning_reasons.json.
Fails if its run counts differ from the over_warning_runs recorded in eval/results/summary.json.

Run: python report/analyze_over_warnings.py
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
QUESTIONS = ROOT / "eval" / "questions.yaml"
SUMMARY = RESULTS / "summary.json"
OUT = ROOT / "report" / "over_warning_reasons.json"
OVERRIDES = ROOT / "report" / "over_warning_overrides.json"
SETUPS = ["A", "B", "C", "D"]

PATTERN = (r"accession|filing date|filed date|filing metadata|dated (after|later|in 2026)|later filing"
           r"|comparative|restat|lineage|source metadata|retrieved_on")
RE = re.compile(PATTERN, re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def final_text(rec):
    texts = [t for t in rec.get("text") or [] if t.strip()]
    return texts[-1] if texts else ""


def matched_sentence(text):
    """The first sentence (or line) of text that contains a keyword match."""
    for s in SENTENCE_END.split(text):
        m = RE.search(s)
        if m:
            return s.strip(), m.group(0)
    return None, None


def main():
    questions = {q["id"]: q for q in yaml.safe_load(QUESTIONS.read_text())}
    summary = json.loads(SUMMARY.read_text())
    overrides = {(o["setup"], o["question_id"], o["run"]): o for o in json.loads(OVERRIDES.read_text())}
    used = set()
    out = {"method": ("Keyword heuristic, not a judgement of each caveat. Runs: warning = true on a "
                      "question whose expected_behavior is 'answer'. Text: the run's last non-empty "
                      "model text block (it holds the FINAL line). A run is 'matched' if that text "
                      "matches the pattern (case-insensitive), unless a manual correction in "
                      "manual_corrections overrides it after reading the full text."),
           "pattern": PATTERN, "manual_corrections": [], "setups": {}}
    for s in SETUPS:
        runs = {}
        for line in (RESULTS / f"{s}.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                runs[(r["question_id"], r["run"])] = r  # last line wins, as in score.py
        matched, unmatched = [], []
        for (qid, run), r in sorted(runs.items()):
            if questions[qid]["expected_behavior"] != "answer" or not r.get("parsed"):
                continue
            if r["final"].get("warning") is not True:
                continue
            sentence, word = matched_sentence(final_text(r))
            row = {"question_id": qid, "run": run}
            if sentence:
                row.update(keyword=word, sentence=sentence)
            is_match = sentence is not None
            o = overrides.get((s, qid, run))
            if o:
                if o["matched"] == is_match:
                    sys.exit(f"override {s} {qid} run {run} does not change the keyword result")
                used.add((s, qid, run))
                is_match = o["matched"]
                row.update(manual_correction=o["reason"])
                out["manual_corrections"].append({**o, "keyword_result": sentence is not None})
            (matched if is_match else unmatched).append(row)
        n = len(matched) + len(unmatched)
        recorded = summary["setups"][s]["over_warning_runs"]
        if n != recorded:
            sys.exit(f"{s}: {n} warning runs on answer questions, summary.json records {recorded}")
        out["setups"][s] = {"warning_runs": n, "matched": len(matched), "unmatched": len(unmatched),
                            "matched_runs": matched, "unmatched_runs": unmatched}
        print(f"{s}: {len(matched)} of {n} warning runs matched (keyword match plus manual corrections)")
    unused = set(overrides) - used
    if unused:
        sys.exit(f"overrides name runs that are not warning runs on answer questions: {sorted(unused)}")
    out["n_manual_corrections"] = len(out["manual_corrections"])
    print(f"manual corrections applied: {out['n_manual_corrections']}")
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
