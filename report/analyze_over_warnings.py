"""Why did runs warn on questions whose answer key expects no caveat? A keyword heuristic.

For each setup, takes the runs with warning = true on questions whose expected_behavior is "answer"
(the runs eval/score.py counts as over-warning) and checks whether the run's final model text (the
last non-empty text block, which holds the FINAL line) matches PATTERN, a fixed list of words that
refer to filing dates, accession numbers, comparatives or retrieval metadata.

This is a keyword heuristic, not a judgement of each caveat: a match means the text mentions one of
these words, not that the warning is about them alone, and a non-match is not checked further.

Reads eval/results/{A,B,C,D}.jsonl and eval/questions.yaml. Writes report/over_warning_reasons.json.
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
    out = {"method": ("Keyword heuristic, not a judgement of each caveat. Runs: warning = true on a "
                      "question whose expected_behavior is 'answer'. Text: the run's last non-empty "
                      "model text block (it holds the FINAL line). A run is 'matched' if that text "
                      "matches the pattern (case-insensitive)."),
           "pattern": PATTERN, "setups": {}}
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
                matched.append({**row, "keyword": word, "sentence": sentence})
            else:
                unmatched.append(row)
        n = len(matched) + len(unmatched)
        recorded = summary["setups"][s]["over_warning_runs"]
        if n != recorded:
            sys.exit(f"{s}: {n} warning runs on answer questions, summary.json records {recorded}")
        out["setups"][s] = {"warning_runs": n, "matched": len(matched), "unmatched": len(unmatched),
                            "matched_runs": matched, "unmatched_runs": unmatched}
        print(f"{s}: {len(matched)} of {n} warning runs match the pattern")
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
