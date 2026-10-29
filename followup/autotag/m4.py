"""M4 changed outcomes (PREREG design decision 9).

A question's outcome changed if its number of correct runs out of 3 differs between hand-tag D
(eval/results/D.jsonl) and draft-1 D (results/D_autotag.jsonl), both scored with the frozen
eval/score.py score_run through score_d.py. Each incorrect draft-1 run on a changed question is
classified, in this order:
  unparsed or API error                                  -> other
  refused = true                                         -> tool error/refusal
  no numeric answer, and a tool call returned an error   -> tool error/refusal
  warning = true                                         -> warning raised
  otherwise                                              -> silent
It is linked to every tag id its tool calls named (metric_id, or get_metric's short metric name
mapped through the fundamentals filter) whose draft entry differs from the hand entry on a scored
field.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import score_tags  # noqa: E402

OTHER, REFUSAL, WARNING, SILENT = "other", "tool error/refusal", "warning raised", "silent"
CLASSES = [SILENT, REFUSAL, WARNING, OTHER]


def classify(rec):
    final = rec.get("final")
    if not rec.get("parsed") or rec.get("error") or not isinstance(final, dict):
        return OTHER
    if final.get("refused") is True:
        return REFUSAL
    ans = final.get("answer")
    numeric = isinstance(ans, (int, float)) and not isinstance(ans, bool)
    if not numeric and any(tc.get("is_error") for tc in rec.get("tool_calls", [])):
        return REFUSAL
    if final.get("warning") is True:
        return WARNING
    return SILENT


def named_tag_ids(rec, short_to_id, include_denominator=False):
    """Tag ids named by a run's tool calls: metric_id, or metric (a short fundamentals name). With
    include_denominator, also aggregate's denominator_id (the secondary count declared in
    PREREG_DEVIATIONS.md; the pre-registered count leaves it out)."""
    out = []
    for tc in rec.get("tool_calls", []):
        args = tc.get("input") or {}
        if isinstance(args.get("metric_id"), str):
            out.append(args["metric_id"])
        if isinstance(args.get("metric"), str):
            out.append(short_to_id.get(args["metric"], args["metric"]))
        if include_denominator and isinstance(args.get("denominator_id"), str):
            out.append(args["denominator_id"])
    return sorted(set(out))


def short_metric_map(hand_entries):
    return {e["filter"]["metric"]: e["id"] for e in hand_entries
            if e["table"] == "fundamentals" and isinstance((e.get("filter") or {}).get("metric"), str)}


def linked_fields(rec, hand_entries, draft_entries, include_denominator=False):
    """{tag id: [differing scored fields]} for the tag ids the run named that differ."""
    hand = {e["id"]: e for e in hand_entries}
    draft = {e["id"]: e for e in draft_entries if isinstance(e, dict) and "id" in e}
    out = {}
    for tid in named_tag_ids(rec, short_metric_map(hand_entries), include_denominator):
        if tid not in hand:
            continue  # a name the run made up; it has no tag in either file
        diff = score_tags.scored_fields_differ(hand[tid], draft.get(tid))
        if diff:
            out[tid] = diff
    return out


def changed_outcomes(hand_scored, draft_scored, draft_runs, hand_entries, draft_entries):
    """Per changed question: hand and draft correct counts, and each incorrect draft run's class and
    linked tag fields."""
    def per_q(scored):
        c = {}
        for (qid, _), s in scored.items():
            c[qid] = c.get(qid, 0) + int(s["correct"])
        return c

    hq, dq = per_q(hand_scored), per_q(draft_scored)
    out = {}
    for qid in sorted(set(hq) | set(dq)):
        if hq.get(qid, 0) == dq.get(qid, 0):
            continue
        runs = []
        for (q, r), s in sorted(draft_scored.items()):
            if q != qid or s["correct"]:
                continue
            rec = draft_runs[(q, r)]
            runs.append({"run": r, "class": classify(rec), "final_line": rec.get("final_line"),
                         "linked": linked_fields(rec, hand_entries, draft_entries)})
        out[qid] = {"hand_correct": hq.get(qid, 0), "draft_correct": dq.get(qid, 0),
                    "incorrect_draft_runs": runs}
    return out
