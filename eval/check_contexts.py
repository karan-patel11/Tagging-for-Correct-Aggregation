"""Phase 11 leak check: no context file may contain an answer, a trap answer, or question text.

Searches eval/contexts/{schema_only,tags,prose}.txt for every correct and trap value in
eval/questions.yaml, in several formats (raw, with commas, in millions, rounded to 1 and 2
decimals), and for each question's wording (the full text and every 8-word run of it).
A number only counts as a hit when it is not part of a longer number. Prints every hit.

Run: python eval/check_contexts.py
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FILES = ["schema_only.txt", "tags.txt", "prose.txt"]
NGRAM = 8


def formats(v):
    """Text forms an answer could take."""
    out = {repr(v), str(v)}
    for d in (1, 2):
        out.add(f"{v:.{d}f}")
        out.add(f"{v:,.{d}f}")
    if abs(v) >= 1e6:
        m = v / 1e6
        for d in (1, 2):
            out.add(f"{m:.{d}f}")
            out.add(f"{m:,.{d}f}")
    if float(v).is_integer():
        out.add(str(int(v)))
        out.add(f"{int(v):,}")
    return {s for s in out if s not in ("0", "-0", "0.0", "-0.0", "0.00", "-0.00")}


def number_hits(text, s):
    # Not preceded by a digit, '.' or ','-digit; not followed by a digit or '.'/','+digit.
    pat = r"(?<![\d.,])" + re.escape(s) + r"(?![\d]|[.,]\d)"
    return [m.start() for m in re.finditer(pat, text)]


def words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


def main():
    questions = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())
    texts = {f: (ROOT / "eval" / "contexts" / f).read_text() for f in FILES}
    hits = []
    for q in questions:
        values = {"correct": q["correct"], **{f"trap:{k}": v for k, v in q["trap_answers"].items()}}
        for label, v in values.items():
            if v is None:
                continue
            for s in sorted(formats(float(v))):
                for f, t in texts.items():
                    for pos in number_hits(t, s):
                        line = t.count("\n", 0, pos) + 1
                        hits.append(f"{q['id']} {label}={v} as '{s}' in {f}:{line}: "
                                    f"...{t[max(0, pos - 40):pos + len(s) + 40]!r}...")
        qw = words(q["question"])
        for f, t in texts.items():
            tw = " ".join(words(t))
            if " ".join(qw) in tw:
                hits.append(f"{q['id']} full question text in {f}")
            grams = {" ".join(qw[i:i + NGRAM]) for i in range(len(qw) - NGRAM + 1)}
            for g in sorted(grams):
                if g in tw:
                    hits.append(f"{q['id']} {NGRAM}-word run of the question in {f}: '{g}'")
    print(f"Checked {len(questions)} questions against {', '.join(FILES)}")
    print("\n".join(hits) if hits else "No hits.")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
