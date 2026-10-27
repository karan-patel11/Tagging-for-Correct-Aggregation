"""Phase 10: recompute each question's answer from the hand-entered value_seen column of
eval/verification_log.csv, compare it with eval/questions.yaml using the SPEC.md §11.6
tolerances, write matches = yes/no back to the log, and print mismatches and verified counts.

Uses only the log and questions.yaml. It must not import semantics.py, make_questions.py or
anything in src/, and it never opens the database.

Formulas, chosen from each row's piece tag (the bracket at the start of where_in_source):
  [sec:...]        one piece: the value; two pieces of one metric: larger period minus smaller
                   (FY - YTD9, YTD9 - YTD6, YTD6 - Q); operating_income + revenue pieces:
                   sum(operating income) / sum(revenue) * 100. Capex uses absolute values.
  [comps:...]      CMG minus WING.
  [cpi:...]        index_points: mean of the months; percent: (last / first - 1) * 100.
  [census722:...]  sum of the months.
  [views:...]      views: sum; percent: KFC views / all pieces * 100.
  [absent:...]     matches when value_seen is 0.

A question is verified when every one of its rows has value_seen filled and the recomputed
answer is within tolerance. matches stays blank for rows of questions not yet fully filled.

Run: python eval/check_verification.py [path/to/log.csv]
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval" / "verification_log.csv"
QUESTIONS = ROOT / "eval" / "questions.yaml"
CATEGORIES = ["time_additivity", "ratios", "ytd_calendar", "indices", "hierarchy",
              "comparability_unanswerable"]
MIN_TOTAL, MIN_PER_CATEGORY, TARGET_PER_CATEGORY = 36, 6, 7
BASIS_ORDER = {"Q": 1, "YTD6": 2, "YTD9": 3, "FY": 4}
TAG = re.compile(r"^\[([^\]]+)\]")


def tolerance(q):
    """Absolute tolerance from SPEC §11.6."""
    unit, correct = q["unit"], q["correct"]
    if unit in ("USD", "USD millions"):
        return 0.005 * abs(correct)
    if unit == "USD/shares":
        return 0.01
    if unit == "views":
        return 0.001 * abs(correct)
    if unit == "percent" and q["category"] == "indices":
        return 0.05
    if unit in ("percent", "percentage_points"):
        return 0.1
    if unit == "index_points":
        return 0.1
    raise ValueError(f"no tolerance rule for unit {unit!r} ({q['id']})")


def parse_number(s):
    s = s.strip().replace(",", "").replace("$", "").replace("%", "")
    neg = s.startswith("(") and s.endswith(")")
    v = float(s.strip("()"))
    return -v if neg else v


def recompute(q, rows):
    pieces = [(TAG.match(r["where_in_source"]).group(1).split(":"), parse_number(r["value_seen"]))
              for r in rows]
    kind = pieces[0][0][0]
    if any(p[0][0] != kind for p in pieces):
        raise ValueError("mixed piece kinds")

    if kind == "absent":
        return pieces[0][1]
    if kind == "sec":
        metrics = {p[0][2] for p in pieces}
        if metrics == {"operating_income", "revenue"}:
            oi = sum(v for t, v in pieces if t[2] == "operating_income")
            rev = sum(v for t, v in pieces if t[2] == "revenue")
            return oi / rev * 100
        if len(metrics) != 1:
            raise ValueError(f"unexpected metrics {metrics}")
        vals = [(BASIS_ORDER.get(t[3], 0), abs(v) if t[2] == "capex" else v) for t, v in pieces]
        if len(vals) == 1:
            return vals[0][1]
        if len(vals) == 2:
            vals.sort()
            return vals[1][1] - vals[0][1]
        raise ValueError("more than two pieces for one metric")
    if kind == "comps":
        by = {t[1]: v for t, v in pieces}
        if set(by) != {"CMG", "WING"}:
            raise ValueError(f"comps pieces {set(by)}")
        return by["CMG"] - by["WING"]
    if kind == "cpi":
        vals = [v for _, v in sorted(pieces, key=lambda p: p[0][1])]
        if q["unit"] == "index_points":
            return sum(vals) / len(vals)
        return (vals[-1] / vals[0] - 1) * 100
    if kind == "census722":
        return sum(v for _, v in pieces)
    if kind == "views":
        total = sum(v for _, v in pieces)
        if q["unit"] == "views":
            return total
        return sum(v for t, v in pieces if t[1] == "KFC") / total * 100
    raise ValueError(f"unknown piece kind {kind}")


def main():
    questions = yaml.safe_load(QUESTIONS.read_text())
    with LOG.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        log = list(reader)

    by_q = defaultdict(list)
    for r in log:
        by_q[r["question_id"]].append(r)

    # The same source number can appear under several questions; flag disagreements.
    seen = defaultdict(set)
    for r in log:
        if r["value_seen"].strip():
            seen[TAG.match(r["where_in_source"]).group(1)].add(r["value_seen"].strip())
    inconsistent = {k: v for k, v in seen.items() if len(v) > 1}

    verified = defaultdict(int)
    mismatches, pending, errors = [], [], []
    for q in questions:
        rows = by_q.get(q["id"], [])
        if not rows:
            errors.append(f"{q['id']}: no rows in the log")
            continue
        blanks = sum(1 for r in rows if not r["value_seen"].strip())
        if blanks:
            for r in rows:
                r["matches"] = ""
            pending.append(f"{q['id']}: {blanks} of {len(rows)} rows blank")
            continue
        try:
            got = recompute(q, rows)
        except (ValueError, ZeroDivisionError) as e:
            errors.append(f"{q['id']}: {e}")
            for r in rows:
                r["matches"] = "no"
            continue
        if q["expected_behavior"] == "refuse":
            ok = got == 0
            expected, tol = 0, 0
        else:
            expected, tol = q["correct"], tolerance(q)
            ok = abs(got - expected) <= tol
        for r in rows:
            r["matches"] = "yes" if ok else "no"
        if ok:
            verified[q["category"]] += 1
        else:
            mismatches.append(f"{q['id']} ({q['category']}): recomputed {got:,.6f}, "
                              f"questions.yaml {expected:,.6f}, tolerance {tol:,.6f} {q['unit']}")

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(log)

    print("=== Mismatches ===")
    print("\n".join(mismatches) if mismatches else "None.")
    if errors:
        print("\n=== Errors ===")
        print("\n".join(errors))
    if inconsistent:
        print("\n=== Same source number entered differently in different rows ===")
        for k, v in sorted(inconsistent.items()):
            print(f"{k}: {sorted(v)}")
    print(f"\n=== Not yet fully filled: {len(pending)} questions ===")
    for p in pending:
        print(p)

    print("\n=== Verified per category (minimum 6 each, target 7) ===")
    counts = defaultdict(int)
    for q in questions:
        counts[q["category"]] += 1
    for cat in CATEGORIES:
        n = verified[cat]
        flag = "OK" if n >= MIN_PER_CATEGORY else f"below minimum by {MIN_PER_CATEGORY - n}"
        print(f"{cat:27s} {n} of {counts[cat]} in file  {flag}")
    total = sum(verified.values())
    print(f"{'total':27s} {total} of {len(questions)} in file  "
          f"{'OK' if total >= MIN_TOTAL else f'below minimum of {MIN_TOTAL}'}")
    ready = total >= MIN_TOTAL and all(verified[c] >= MIN_PER_CATEGORY for c in CATEGORIES)
    print(f"\nReady to freeze (>= {MIN_TOTAL} total and >= {MIN_PER_CATEGORY} per category): "
          f"{'yes' if ready else 'no'}")


if __name__ == "__main__":
    main()
