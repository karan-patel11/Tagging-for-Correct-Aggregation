"""The problem-first story above the "Full detail" divider of docs/index.html, and the follow-up
sections below it (auto-tag follow-up and engine hardening).

Every number comes from a committed file, read here:
  eval/results/summary.json, eval/results/D.jsonl     main results (setups A-D)
  eval/questions.yaml                                 answer key (the worked example)
  eval/verification_log.csv                           company count (as in build_report.py)
  followup/autotag/results/D_autotag.jsonl            setup D on AI-drafted rules (draft 1)
  followup/autotag/results/score_tags.json            per-field scores and validation (M1-M3)
  followup/autotag/drafts/draft_{1,2,3}.yaml          the AI-drafted rules
  followup/autotag/drafts/draft_{1,2,3}_meta.json     drafting time and cost per draft
  followup/autotag/inputs/*.json                      what the drafting model was given
  followup/engine_fix/replay.json                     engine-hardening replay counts
Runs are scored with eval/score.py's score_run (through followup/autotag/score_d.py) and root causes
come from followup/autotag/root_causes.py's own functions, imported unchanged. report/replays.yaml
picks the worked examples. Wording is fixed here; values are not.

story_data() returns every value the story shows, so tests/test_report.py can check each one
against its source file.
"""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTOTAG = ROOT / "followup" / "autotag"
ENGINE_FIX = ROOT / "followup" / "engine_fix"
for p in (ROOT / "eval", AUTOTAG, ENGINE_FIX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import yaml  # noqa: E402

import m4  # noqa: E402  (followup/autotag, unchanged)
import replay  # noqa: E402  (followup/engine_fix, unchanged; constants only)
import root_causes as rc  # noqa: E402  (followup/autotag, unchanged)
import score  # noqa: E402
import score_d  # noqa: E402
import score_tags  # noqa: E402

D_AUTOTAG = AUTOTAG / "results" / "D_autotag.jsonl"
SCORE_TAGS = AUTOTAG / "results" / "score_tags.json"
DRAFTS = AUTOTAG / "drafts"
ENGINE_REPLAY = ENGINE_FIX / "replay.json"
REPLAY_MD = ENGINE_FIX / "REPLAY.md"
PREREG = "followup/autotag/PREREG.md"
DIVIDER_ID = "full-detail"

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
         9: "nine", 10: "ten"}
COMPANY = {"CMG": "Chipotle", "WING": "Wingstop", "YUM": "Yum! Brands", "DRI": "Darden"}
SETUP_PLAIN = {"A": "Only the database layout", "B": "A written description of the rules",
               "C": "A rules file", "D": "Tools that enforce the rules"}

# Root causes (followup/autotag/root_causes.py), in the order the bar shows them, in plain words.
CAUSE_PLAIN = [
    (rc.REPORTED_Q, "Rule error by the AI",
     "It marked cash flow, capital spending and revenue as “do not add up”, which blocks working out "
     "one quarter from year-to-date totals.", "seg-ai"),
    (rc.LINEAGE, "Source links missing from what I gave the AI",
     "My input gap, not the AI's fault: the vendor files I supplied had no source web address for "
     "the two government series.", "seg-input"),
    (rc.HIERARCHY, "A missing parent/brand rule, plus a crash in my engine",
     "The AI left out which brands belong to which parent company, and my engine crashed instead of "
     "refusing.", "seg-engine"),
    (rc.NONE, "Unrelated to the rules",
     "The AI asked for a metric name or period format the tools do not have.", "seg-other"),
]

# The validator rules added in src/tags.py (followup/engine_fix/replay.py RULE_FIELDS keys).
RULE_TEXT = {
    "flow": "A flow (semantic_type flow) needs additive_over_time true and time_rollup sum.",
    "sum_over_time": "sum_over_time in valid_methods needs additive_over_time true.",
    "sum_across_entities": "sum_across_entities in valid_methods needs additive_over_entities true.",
    "hierarchy": "A measure on a table with a parent_* column needs a hierarchy.",
    "lineage": "A measure on macro_monthly needs lineage.url; on brand_attention_daily, "
               "lineage.url_template (the keys src/semantics.py reads).",
}


def die(msg):
    sys.exit(f"build_report (story): {msg}")


def need(d, *path):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            die(f"missing value {'.'.join(map(str, path))}")
        cur = cur[k]
    return cur


def read_json(path):
    if not path.exists():
        die(f"missing file {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def word(n):
    return WORDS.get(n) or str(n)


def usd(v):
    return f"${int(v):,}"


def pct0(x):
    return f"{round(x * 100)}%"


def first_commit(rel_path):
    """Short hash of the commit that added a file (the pre-registration commit)."""
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%h", "--abbrev=7", "--",
                              rel_path], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        die(f"cannot read git history for {rel_path}: {exc}")
    hashes = out.split()
    if not hashes:
        die(f"no commit adds {rel_path}")
    return hashes[-1]


def sentence_with(text, phrase):
    for s in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if phrase in s:
            return s
    die(f"no sentence containing {phrase!r}")


# ---------- data ----------

def story_data(summary, questions, vlog, replays):
    cfg = need(replays, "story")
    d = {}

    # Main results.
    setups = need(summary, "setups")
    d["model"] = ", ".join(need(summary, "model"))
    d["n_models"] = len(need(summary, "model"))
    d["n_questions"] = len(questions)
    d["runs_per_question"] = len(need(summary, "runs_per_question"))
    d["setups"] = {s: {"mean": need(setups, s, "accuracy", "mean"), "correct": need(setups, s, "correct_runs"),
                       "n": need(setups, s, "n")} for s in score.SETUPS}
    d["n_answers"] = sum(v["n"] for v in d["setups"].values())
    d["acc_min"] = min(v["mean"] for v in d["setups"].values())
    d["acc_max"] = max(v["mean"] for v in d["setups"].values())
    d["trap_hits"] = sum(need(t, "hits") for s in score.SETUPS for t in need(setups, s, "trap_hits").values())
    ciks = {m.group(1) for r in vlog for m in [re.search(r"edgar/data/(\d+)/", r["source_url"])] if m}
    d["n_companies"] = len(ciks)

    # The worked example (answer key).
    q = questions.get(need(cfg, "problem_question")) or die("unknown story.problem_question")
    traps = need(q, "trap_answers")
    d["problem"] = {"question": q["question"], "correct": need(q, "correct"),
                    "full_year": need(traps, "used_fy_value"), "nine_months": need(traps, "used_ytd9_value")}
    if d["problem"]["full_year"] - d["problem"]["nine_months"] != d["problem"]["correct"]:
        die("problem question: full year minus nine months does not equal the answer key")

    # Auto-tag follow-up: setup D on draft 1, scored with eval/score.py.
    scored, runs, _ = score_d.score_records(D_AUTOTAG)
    wrong = sorted(k for k, s in scored.items() if not s["correct"])
    classes = Counter(m4.classify(runs[k]) for k in wrong)
    numeric_wrong = sum(1 for k in wrong if isinstance((runs[k].get("final") or {}).get("answer"), (int, float))
                        and not isinstance(runs[k]["final"]["answer"], bool))
    d["autotag"] = {"hand_correct": d["setups"]["D"]["correct"], "hand_n": d["setups"]["D"]["n"],
                    "draft_correct": len(scored) - len(wrong), "draft_n": len(scored), "wrong": len(wrong),
                    "refused": sum(1 for k in wrong if (runs[k].get("final") or {}).get("refused") is True),
                    "no_answer": sum(1 for k in wrong if not runs[k].get("parsed")),
                    "numeric_wrong": numeric_wrong, "classes": dict(classes)}
    if d["autotag"]["refused"] + d["autotag"]["no_answer"] + numeric_wrong != len(wrong):
        die("wrong draft-1 runs are not all refusals, missing answers or numbers")

    metas = [read_json(DRAFTS / f"{n}_meta.json") for n in score_tags.DRAFT_NAMES]
    tagger = {need(m, "model") for m in metas}
    if len(tagger) != 1:
        die(f"drafts used different models {tagger}")
    st = read_json(SCORE_TAGS)
    d["drafts"] = {
        "tagger": tagger.pop(), "n": len(metas),
        "passed": sum(bool(need(st, "drafts", n, "m3", "pass")) for n in score_tags.DRAFT_NAMES),
        "min_s": min(need(m, "wall_clock_seconds_this_process") for m in metas),
        "max_s": max(need(m, "wall_clock_seconds_this_process") for m in metas),
        "min_cost": min(need(m, "cost_usd") for m in metas), "max_cost": max(need(m, "cost_usd") for m in metas),
    }

    # Root causes, with root_causes.py's own rules.
    hand_list = score_tags.read_entries(score_tags.HAND_PATH)
    hand = {e["id"]: e for e in hand_list}
    d1 = {e["id"]: e for e in score_tags.read_entries(DRAFTS / "draft_1.yaml")}
    groups = {}
    for k in wrong:
        cause, tid = rc.primary_cause(rc.run_causes(runs[k], hand, d1))
        g = groups.setdefault(cause, {"runs": [], "tags": set()})
        g["runs"].append(k)
        if tid:
            g["tags"].add(tid)
    unknown = set(groups) - {c for c, *_ in CAUSE_PLAIN}
    if unknown:
        die(f"root causes with no plain-language label: {sorted(unknown)}")
    d["causes"] = [{"cause": c, "label": lab, "detail": det, "cls": cls,
                    "runs": len(groups.get(c, {"runs": []})["runs"]),
                    "tags": sorted(groups.get(c, {"tags": set()})["tags"]),
                    "questions": sorted({qq for qq, _ in groups.get(c, {"runs": []})["runs"]}),
                    "values": {t: rc.field_values(c, t, hand, d1) for t in sorted(groups.get(c, {"tags": set()})["tags"])}}
                   for c, lab, det, cls in CAUSE_PLAIN]
    if sum(c["runs"] for c in d["causes"]) != d["autotag"]["draft_n"] - d["autotag"]["draft_correct"]:
        die("root-cause groups do not sum to the wrong draft-1 runs")
    lineage = next(c for c in d["causes"] if c["cause"] == rc.LINEAGE)
    d["packet_urls"] = {t: len(rc.packet_urls(t)) for t in lineage["tags"]}
    if any(d["packet_urls"].values()):
        die("a lineage input packet contains a URL; the 'input gap' wording would be wrong")

    # The clearest example: the AI's description, the rule it wrote, what happened.
    ex = need(cfg, "autotag_example")
    tid, qid, run = need(ex, "tag"), need(ex, "question_id"), need(ex, "run")
    entry = d1.get(tid) or die(f"draft_1 has no {tid}")
    rec = runs.get((qid, run)) or die(f"no draft-1 run {qid} {run}")
    if scored[(qid, run)]["correct"] or not rec["final"]["refused"]:
        die(f"example run {qid} {run} is not a refusal")
    errs = [rc.explanation(tc["output"]) for tc in rec["tool_calls"] if tc.get("is_error")]
    tool_msg = next((t for t in errs if t.startswith("insufficient data: no reported Q")), None) or \
        die(f"example run {qid} {run} has no 'no reported quarter' tool error")
    if (entry.get("additive_over_time"), entry.get("time_rollup")) != (False, "reported_fy_value"):
        die(f"draft_1 {tid} rule changed; the plain-language rule text no longer fits")
    hand_runs = score_d.load_records(score_d.HAND_D)
    hq = [score.score_run(r, questions[qid])["correct"] for (q_, _), r in hand_runs.items() if q_ == qid]
    final_text = next(t for t in reversed(rec["text"]) if t.strip())
    d["example"] = {
        "question": questions[qid]["question"], "correct": questions[qid]["correct"],
        "description": sentence_with(entry["description"], need(ex, "description_phrase")),
        "rule": (entry["additive_over_time"], entry["time_rollup"]), "tool_message": tool_msg,
        "reply": final_text.strip().split("\n")[0].strip(), "hand_ok": sum(hq), "hand_n": len(hq),
        "tag": tid, "qid": qid, "run": run, "record": rec,
        "derivation": hand[tid]["derivation"],
    }

    # Engine hardening.
    rp = read_json(ENGINE_REPLAY)
    d["engine"] = {
        "results_commit": need(rp, "results_commit"),
        "hand_calls": need(rp, "hand", "calls"), "hand_identical": need(rp, "hand", "identical"),
        "draft_calls": need(rp, "draft_1", "calls"),
        "crashes_before": need(rp, "draft_1", "old_exceptions"), "crashes_after": need(rp, "draft_1", "new_exceptions"),
        "transitions": need(rp, "draft_1", "pairs"),
        "forbidden_before": need(rp, "permissive", "numbers_before"),
        "forbidden_after": need(rp, "permissive", "numbers_after"),
        "permissive_pairs": need(rp, "permissive", "pairs"), "permissive_calls": need(rp, "permissive", "calls_per_engine"),
        "rule_errors": need(rp, "validator", "errors"), "rule_caught": need(rp, "validator", "caught"),
        "hand_violations": need(rp, "validator", "hand_violations"),
    }
    # The one number left after the hardening is a correctly labelled mean (REPLAY.md (c)).
    md = REPLAY_MD.read_text() if REPLAY_MD.exists() else die("missing followup/engine_fix/REPLAY.md")
    m = re.search(r"Numbers after the hardening: (.+?)\. Each is", md)
    if not m or d["engine"]["forbidden_after"] != 1 or "mean_over_time" not in m.group(1) \
            or "Mean of" not in m.group(1):
        die("REPLAY.md no longer shows a single correctly labelled mean after the hardening")
    d["engine"]["remaining"] = m.group(1)
    if set(replay.RULE_FIELDS) != set(RULE_TEXT):
        die(f"validator rules changed: {sorted(replay.RULE_FIELDS)}")
    d["rules"] = [(k, RULE_TEXT[k]) for k in replay.RULE_FIELDS]

    # Per-field scores (M1/M1b), verdicts and validation (M3), from score_tags.json.
    fields = list(need(st, "verdicts"))
    per_field = []
    for f in fields:
        cells = []
        for n in score_tags.DRAFT_NAMES:
            if f == "semantic_type (dimension/identifier)":
                rows = need(st, "drafts", n, "m1b").values()
                cells.append((sum(r["match"] for r in rows), len(rows)))
            else:
                rows = [r[f] for r in need(st, "drafts", n, "m1").values() if f in r]
                cells.append((sum(r["match"] for r in rows), len(rows)))
        per_field.append((f, cells, need(st, "verdicts", f, "verdict")))
    d["per_field"] = per_field
    d["m3"] = {n: need(st, "drafts", n, "m3") for n in score_tags.DRAFT_NAMES}
    d["m2"] = {n: sum(len(v) for v in need(st, "drafts", n, "m2").values()) for n in score_tags.DRAFT_NAMES}
    d["prereg_commit"] = first_commit(PREREG)
    return d


# ---------- rendering helpers ----------

def card(big, meaning, src_href, src_label, e, extra_cls=""):
    return (f'<div class="rcard{extra_cls}"><div class="rbig">{big}</div><p class="rmean">{meaning}</p>'
            f'<p class="rsrc"><a href="{e(src_href)}">Source: {e(src_label)}</a></p></div>')


def stack_table(heads, rows, e):
    """A table that stacks into cards on narrow screens (the .stack style); cells are HTML."""
    body = "".join(f"<tr><th scope='row'>{r[0]}</th>"
                   + "".join(f'<td data-label="{e(h)}"><span>{c}</span></td>' for h, c in zip(heads[1:], r[1:]))
                   + "</tr>" for r in rows)
    return (f'<div class="table-wrap"><table class="stack"><thead><tr>'
            f'{"".join(f"<th scope=\"col\">{e(h)}</th>" for h in heads)}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def blob(repo, path, ref="main"):
    return f"{repo}/blob/{ref}/{path}"


# ---------- sections above the divider ----------

def section_hero(d, e):
    p = d["problem"]
    a = d["autotag"]
    return f"""
<div class="hero">
  <div class="hero-text">
    <div class="kicker">A small experiment</div>
    <h1>AI can calculate a financial number correctly and still answer the wrong question.</h1>
    <p class="lede-lg">Analysts increasingly ask AI tools questions about company data, and the tool
    writes and runs the calculation itself. The calculation can run without any error and still be
    wrong, for example by adding four quarter-end balances into a meaningless “annual” total. An
    analyst who cannot read the query cannot catch it.</p>
    <dl class="didfound">
      <dt>What I did</dt>
      <dd>I asked an AI model {d["n_questions"]} questions about {word(d["n_companies"])} restaurant
      companies, with and without rules for each metric, and checked all {d["n_answers"]} answers.</dd>
      <dt>What I found</dt>
      <dd>Rules barely moved accuracy ({e(pct0(d["acc_min"]))}–{e(pct0(d["acc_max"]))} correct
      everywhere); AI-written rules cut correct answers from {a["hand_correct"]} to
      {a["draft_correct"]} of {a["draft_n"]}, mostly by refusing to answer.</dd>
    </dl>
    <nav class="jump" aria-label="Jump to">
      <a href="#idea">1-minute summary</a><a href="#measure">How I tested it</a><a href="#{DIVIDER_ID}">Full detail</a>
    </nav>
  </div>
  <figure class="example" aria-labelledby="example-cap">
    <figcaption id="example-cap" class="ex-q"><span class="muted small">The question</span>
      <span class="ex-qtext">{e(p["question"])}</span></figcaption>
    <div class="ex-row ex-wrong">
      <div class="ex-label"><span class="mark" aria-hidden="true">✕</span> A plausible wrong answer</div>
      <div class="ex-num">{e(usd(p["full_year"]))}</div>
      <p class="ex-why">This is Darden's whole fiscal year, all four quarters together. The question asks
      for one quarter.</p>
    </div>
    <div class="ex-row ex-right">
      <div class="ex-label"><span class="mark" aria-hidden="true">✓</span> The right answer</div>
      <div class="ex-num">{e(usd(p["correct"]))}</div>
      <p class="ex-why">The full year minus the first nine months ({e(usd(p["nine_months"]))}), which
      is also a plausible wrong answer.</p>
    </div>
  </figure>
</div>"""


def section_idea(tags_by_id, e):
    t = tags_by_id.get("fundamentals.revenue") or die("tags.yaml has no fundamentals.revenue")
    if (t.get("semantic_type"), t.get("additive_over_time"), t.get("calendar")) != ("flow", True, "fiscal"):
        die("revenue tag changed; the plain-language rules no longer fit")
    if "Q4 = FY - YTD9" not in t.get("derivation", ""):
        die("revenue tag derivation changed; the plain-language rules no longer fit")
    fye = re.search(r"DRI's fiscal year ends in ([^.;]+)", t.get("description", "")) or \
        die("revenue tag description no longer names Darden's fiscal year end")
    return f"""
<h2 class="q">What if every metric carried its own rules?</h2>
<p>A tag is a label attached to a metric that says how its numbers may be combined. It records
whether values can be added up over time, which fiscal calendar applies and which rows are parent
totals. A research data team writes the rules once, and every AI answer can follow them.</p>
<div class="tagcard" role="group" aria-label="Example: the rules on revenue">
  <div class="tag-name">Revenue</div>
  <ol class="rules">
    <li><b>Add up over time?</b> Yes. Revenue is earned over a period, so quarters add up to a year.</li>
    <li><b>Which calendar?</b> Each company's own fiscal year. Darden's fiscal year ends in {e(fye.group(1))}.</li>
    <li><b>One quarter from a yearly report?</b> The fourth quarter is the full year minus the first nine months.</li>
  </ol>
</div>"""


def section_measure(d, e, repo):
    s = d["setups"]
    rows = "".join(
        f'<li class="setup"><span class="setup-name">{e(SETUP_PLAIN[k])}</span>'
        f'<span class="track" aria-hidden="true"><span class="fill" style="width:{s[k]["mean"] * 100:.2f}%"></span></span>'
        f'<span class="setup-val">{s[k]["mean"] * 100:.1f}%</span></li>' for k in score.SETUPS)
    n_runs = d["runs_per_question"]
    return f"""
<h2 class="q">Do the rules help the AI answer correctly?</h2>
<p>If rules raise accuracy, a research data team has a reason to write and maintain them. One AI
model ({e(d["model"])}) answered {d["n_questions"]} questions {word(n_runs)} times in each of
{word(len(s))} setups. Each answer was compared with an answer key checked against the companies'
filings and agency data.</p>
<p class="small muted">What the AI was given in each setup, and the share of its answers that were
correct:</p>
<ol class="setups">{rows}</ol>
<p class="small muted">Bars start at zero.</p>
<div class="rcards one">
{card(f'{e(pct0(d["acc_min"]))}–{e(pct0(d["acc_max"]))}',
      f'All {word(len(s))} setups answered correctly this often. They are too close to rank on this sample.',
      blob(repo, "eval/results/summary.md"), "eval/results/summary.md", e)}
</div>
<p>The model rarely fell for the traps here. It gave a plausible wrong answer
{"once" if d["trap_hits"] == 1 else word(d["trap_hits"]) + " times"} in {d["n_answers"]} answers.</p>"""


def stacked_bar(causes, total, e):
    segs = "".join(f'<span class="seg {c["cls"]}" style="width:{c["runs"] / total * 100:.3f}%"></span>'
                   for c in causes if c["runs"])
    desc = "; ".join(f'{c["label"]}: {c["runs"]}' for c in causes)
    legend = "".join(
        f'<li><span class="sw {c["cls"]}" aria-hidden="true"></span><span class="lg-n">{c["runs"]}</span>'
        f'<span class="lg-t"><b>{e(c["label"])}.</b> {e(c["detail"])}</span></li>' for c in causes)
    return (f'<div class="stack-bar" role="img" aria-label="{e(desc)}">{segs}</div>'
            f'<ul class="legend">{legend}</ul>')


def rule_plain(rule):
    additive, rollup = rule
    if additive is False and rollup == "reported_fy_value":
        return "Do not add these values up over time. Use only a figure reported for that exact period."
    die(f"no plain wording for rule {rule}")


def section_autotag(d, e, repo):
    a, dr, ex = d["autotag"], d["drafts"], d["example"]
    prereg = blob(repo, PREREG, d["prereg_commit"])
    runs = blob(repo, "followup/autotag/results/D_autotag.jsonl")
    total = a["draft_n"] - a["draft_correct"]
    mins = f'{dr["min_s"] / 60:.1f}–{dr["max_s"] / 60:.1f} min'
    cost = f'${dr["min_cost"]:.2f}–${dr["max_cost"]:.2f}'
    return f"""
<h2 class="q">Can an AI write the rules itself?</h2>
<p>Writing tags by hand doesn't scale to dozens of vendor datasets. So I asked a stronger model
({e(dr["tagger"])}) to draft them using only what a vendor would supply: column names, sample rows
and the vendor's documentation. I wrote down the test and what would count as success before
running it (<a href="{e(prereg)}">pre-registration</a>). The main results above are unchanged.</p>
<p>Then the same answering model used the AI-written rules through tools that enforce the rules, on
the same {d["n_questions"]} questions.</p>
<div class="rcards">
{card(f'{a["hand_correct"]} → {a["draft_correct"]}',
      f'Correct answers out of {a["draft_n"]}: with my hand-written rules, then with the AI-written rules.',
      runs, "followup/autotag/results/D_autotag.jsonl", e)}
{card(f'{a["numeric_wrong"]} wrong numbers',
      f'On the questions tested, the failures were refusals ({a["refused"]}) or no final answer '
      f'({a["no_answer"]}), not wrong numbers.', runs, "followup/autotag/results/D_autotag.jsonl", e)}
{card(f'{dr["passed"]} of {dr["n"]} drafts',
      'AI drafts that passed the automatic checks that existed at the time.',
      blob(repo, "followup/autotag/results/score_tags.json"), "followup/autotag/results/score_tags.json", e)}
{card(f'{e(mins)}<span class="rbig-sub">{e(cost)}</span>',
      f'Time and cost for the AI to draft one full set of rules ({word(dr["n"])} drafts).',
      blob(repo, "followup/autotag/drafts/draft_1_meta.json"), "followup/autotag/drafts/*_meta.json", e)}
</div>
<h3 class="q3">Why did the AI-written rules fail?</h3>
<p>Each of the {total} answers it did not get right was traced to the first rule-related error in
its record. They fall into four groups.</p>
{stacked_bar(d["causes"], total, e)}
<h3 class="q3">The clearest example</h3>
<p class="muted">The question: “{e(ex["question"])}” The right answer is {e(usd(ex["correct"]))}. With
my hand-written rules, {ex["hand_ok"]} of {ex["hand_n"]} attempts got it.</p>
<div class="triple">
  <div class="tcol"><div class="tlabel">What the AI wrote about the data</div>
    <blockquote>“{e(ex["description"])}”</blockquote>
    <p class="small muted">Correct: these figures run from the start of the fiscal year.</p></div>
  <div class="tcol"><div class="tlabel">The rule it wrote</div>
    <blockquote>{e(rule_plain(ex["rule"]))}</blockquote>
    <p class="small muted">Wrong: one quarter is a year-to-date total minus the previous one.</p></div>
  <div class="tcol"><div class="tlabel">What happened</div>
    <blockquote>The tool found no reported quarterly figure and refused. The AI replied: “{e(ex["reply"])}”</blockquote>
    <p class="small muted"><a href="#example-trace">See the recorded steps</a></p></div>
</div>"""


def section_harden(d, e, repo):
    g = d["engine"]
    rp = blob(repo, "followup/engine_fix/replay.json")
    return f"""
<h2 class="q">The test showed my engine trusted the rules blindly.</h2>
<p>My engine is the code that turns the rules into numbers. A research data team needs it to refuse
rather than return a number nobody asked for. When a rule allowed something the engine could not
compute, it crashed or returned a different calculation under the requested name. Now it refuses
instead.</p>
<p>To check the change, I re-ran every recorded tool request from both tests on the changed engine,
with no AI model involved.</p>
<div class="rcards">
{card(f'{g["crashes_before"]} → {g["crashes_after"]}',
      f'Crashes, out of {g["draft_calls"]:,} recorded requests made with the AI-written rules.', rp,
      "followup/engine_fix/replay.json", e)}
{card(f'{g["forbidden_before"]} → {g["forbidden_after"]}',
      'Results for a calculation my hand-written rules forbid. The one left is a correctly labelled '
      'average the AI\'s rule allowed; deciding what is allowed is the reviewer\'s job.', rp,
      "followup/engine_fix/replay.json", e)}
{card(f'{g["hand_identical"]} of {g["hand_calls"]}',
      'Recorded requests from the main results that give identical output on the changed engine. '
      'The main results are unchanged.', rp, "followup/engine_fix/replay.json", e)}
{card(f'{g["rule_caught"]} of {g["rule_errors"]}',
      'AI rule errors that the new automatic checks catch. Derived from the same drafts, not tested on '
      'new data.', rp, "followup/engine_fix/replay.json", e, " caveat")}
</div>"""


def section_suggests(d, e):
    g, dr = d["engine"], d["drafts"]
    if not all(d["m2"].values()):
        die("a draft has no dangerous errors; the first suggestion's evidence no longer holds")
    return f"""
<div class="label-pill">Suggested by this evidence</div>
<h2 class="q">What does this suggest for a research data team?</h2>
<p>These are three practices this small test points to, not proven rules.</p>
<ol class="suggest">
  <li><b>Let AI draft the rules, but have a person sign off on how numbers combine.</b>
    All {word(dr["passed"])} AI drafts passed the existing automatic checks, yet each had errors in how
    numbers combine.</li>
  <li><b>Add automatic checks for rule combinations that cannot both be true.</b>
    {word(len(d["rules"])).capitalize()} such checks catch {g["rule_caught"]} of {g["rule_errors"]} errors in these drafts.</li>
  <li><b>Make the engine refuse anything it does not implement.</b>
    On the same recorded requests, crashes fell from {g["crashes_before"]} to {g["crashes_after"]}.</li>
</ol>"""


def section_limits(d, e):
    return f"""
<h2 class="q">How far can these results be trusted?</h2>
<p>Knowing the limits tells a research data team how much weight to put on these numbers.</p>
<ul class="limits">
  <li>The sample is small: {d["n_questions"]} questions, {d["n_companies"]} companies and
  {word(d["n_models"])} answering model.</li>
  <li>I wrote the questions, the system and the reference rules myself.</li>
  <li>The cause analysis and the engine fix came after the results, not before.</li>
  <li>The AI-written rules were tested on one kind of data with one drafting model.</li>
</ul>"""


# ---------- sections below the divider ----------

def section_followup_detail(d, e, repo, render_steps):
    a, g = d["autotag"], d["engine"]
    per_field = stack_table(["Field", *score_tags.DRAFT_NAMES, "Verdict"],
                            [[f"<code>{e(f)}</code>", *(f"{m}/{n}" for m, n in cells), e(v)]
                             for f, cells, v in d["per_field"]], e)
    m3 = stack_table(["Draft", "load_tags", "Entries failing alone", "DB problems", "Result"],
                     [[e(n), "ok" if v["load_tags_ok"] else "failed", len(v["entry_errors"]),
                       len(v["db_problems"]), "pass" if v["pass"] else "fail"] for n, v in d["m3"].items()], e)
    cls = "".join(f"<li>{e(k)}: {v}</li>" for k, v in sorted(a["classes"].items()))
    causes = stack_table(
        ["Cause", "Tag ids", "Questions", "Runs", "Hand → draft_1 value"],
        [[f"{e(c['label'])}<br><span class='muted small'>{e(c['cause'])}</span>",
          e(", ".join(c["tags"]) or "-"), e(", ".join(c["questions"])), c["runs"],
          e("; ".join(f"{t}: {json.dumps(h)} → {json.dumps(v)}" for t, (h, v) in c["values"].items()) or "-")]
         for c in d["causes"]]
        + [["Total", "", "", sum(c["runs"] for c in d["causes"]), f"= {a['draft_n']} − {a['draft_correct']}"]], e)
    trans = stack_table(["Recorded output → current output (draft_1 calls)", "Calls"],
                        [[e(k), v] for k, v in g["transitions"].items()], e)
    rules = "".join(f"<li><code>{e(k)}</code>: {e(t)}</li>" for k, t in d["rules"])
    ex = d["example"]
    m2 = ", ".join(f"{n} {v}" for n, v in d["m2"].items())
    prereg = blob(repo, PREREG, d["prereg_commit"])
    links = " · ".join(f'<a href="{e(h)}">{e(t)}</a>' for t, h in [
        ("followup/autotag/RESULTS.md", blob(repo, "followup/autotag/RESULTS.md")),
        ("followup/engine_fix/REPLAY.md", blob(repo, "followup/engine_fix/REPLAY.md")),
        (f"followup/autotag/PREREG.md (commit {d['prereg_commit']})", prereg),
        ("followup/autotag/PREREG_DEVIATIONS.md", blob(repo, "followup/autotag/PREREG_DEVIATIONS.md"))])
    return f"""
<h2>Follow-up: AI-drafted tags and engine hardening</h2>
<p class="muted">Tagging model {e(d["drafts"]["tagger"])}; answering model {e(d["model"])}, setup D. Three
drafts ({e(", ".join(score_tags.DRAFT_NAMES))}), one call per tag id; draft_1 was fixed in advance as the
draft used end to end. Pre-registered at commit <code>{e(d["prereg_commit"])}</code>. Hand tags
(<code>tags/tags.yaml</code>) are the reference. Sources: {links}.</p>

<h3>Per-field match and verdict (M1, M1b; <code>score_tags.json</code>)</h3>
<p class="small muted">Cells: matches / entries scored. “Safe to auto-draft” only if all three drafts match
the hand tag on every scored entry (a threshold chosen in PREREG.md, not an industry standard).</p>
{per_field}
<p class="small muted">Dangerous errors (M2) per draft: {e(m2)}.</p>

<h3>Validation at the time (M3)</h3>
{m3}

<h3>End to end (M4)</h3>
<p>Setup D on hand tags: {a["hand_correct"]}/{a["hand_n"]} correct. On draft_1: {a["draft_correct"]}/{a["draft_n"]}.
Of the {a["wrong"]} incorrect draft_1 runs, {a["refused"]} set refused=true and {a["no_answer"]} ended
without a FINAL line (tool-turn limit); {a["numeric_wrong"]} returned a number. M4 classes
(<code>followup/autotag/m4.py</code>, all incorrect runs):</p><ul>{cls}</ul>

<h3>Root causes of the incorrect draft_1 runs (post-run, not pre-registered)</h3>
<p class="small muted">Computed here with <code>followup/autotag/root_causes.py</code>'s
<code>run_causes</code> and <code>primary_cause</code>: each incorrect run gets the first tag-driven tool
error in its record, checked in the order of the table. The input packets for the lineage tags contain
{sum(d["packet_urls"].values())} URLs ({e(", ".join(f"{t}: {n}" for t, n in d["packet_urls"].items()))}).</p>
{causes}

<h3>Example run: {e(ex["qid"])} run {ex["run"]} on draft_1</h3>
<p class="small">Tag <code>{e(ex["tag"])}</code> in draft_1: additive_over_time
<code>{e(str(ex["rule"][0]).lower())}</code>, time_rollup <code>{e(ex["rule"][1])}</code>; hand tag:
additive_over_time <code>true</code>, time_rollup <code>sum</code>, derivation “{e(ex["derivation"])}”
Tool error: <code>{e(ex["tool_message"])}</code>. Hand-tag D on {e(ex["qid"])}: {ex["hand_ok"]}/{ex["hand_n"]}.</p>
<details class="trace" id="example-trace"><summary>View recorded steps</summary>
<div class="trace-body">{render_steps(ex["record"])}</div></details>

<h3>Engine hardening: replay (no model calls)</h3>
<p>Main results were produced at <code>{e(g["results_commit"])}</code>. Re-executing the {g["hand_calls"]}
recorded setup D tool calls on the hardened engine: {g["hand_identical"]} of {g["hand_calls"]} identical.
Re-executing the {g["draft_calls"]} draft_1 tool calls: exceptions {g["crashes_before"]} recorded,
{g["crashes_after"]} now.</p>
{trans}

<h3>Permissive methods</h3>
<p>The {g["permissive_pairs"]} tag/method pairs that a draft allows and the hand tag forbids, called directly
({g["permissive_calls"]} calls per engine, on the drafts and on a counterfactual draft_1 with the hand
tags' lineage and hierarchy). Calls that returned a number: {g["forbidden_before"]} before the hardening,
{g["forbidden_after"]} after. The remaining one: {e(g["remaining"])}. The engine follows the tags it is
given, so a permissive tag that names an implemented method still needs review.</p>

<h3>Validator rules added to <code>src/tags.py</code></h3>
<ul>{rules}</ul>
<p>Hand tags violating a rule: {g["hand_violations"]}. Draft errors (M2 errors plus a missing lineage key)
caught: {g["rule_caught"]} of {g["rule_errors"]}. The rules were derived from these same drafts' errors,
so this is not a test on new data.</p>"""
