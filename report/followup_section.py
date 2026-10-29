"""The results page's follow-up section: can a model write the tags? (built by build_report.py).

Every number and quoted text comes from committed files, read here and nowhere else:
  followup/autotag/results/D_autotag.jsonl, results/score_tags.json, drafts/draft_{1,2,3}.yaml and
  drafts/draft_*_meta.json; followup/engine_fix/replay.json; eval/results/D.jsonl (hand-tag setup D),
  tags/tags.yaml (hand rules), eval/questions.yaml (question text). Runs are scored with the frozen
  eval/score.py through followup/autotag/score_d.py, and lost runs are grouped with
  followup/autotag/root_causes.py's run_causes/primary_cause; those modules are imported, not changed.
The PREREG commit is the commit that added followup/autotag/PREREG.md, read from git.
"""
import html
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AUTOTAG = ROOT / "followup" / "autotag"
ENGINE_REPLAY = ROOT / "followup" / "engine_fix" / "replay.json"
HAND_TAGS = ROOT / "tags" / "tags.yaml"
QUESTIONS = ROOT / "eval" / "questions.yaml"
DRAFTS = ["draft_1", "draft_2", "draft_3"]
EXAMPLE_TAG, EXAMPLE_Q = "fundamentals.op_cash_flow", "q012"

sys.path.insert(0, str(AUTOTAG))
import m4  # noqa: E402
import root_causes  # noqa: E402
import score_d  # noqa: E402

# Root-cause groups in display order: (cause from root_causes.py, label, plain note, css class).
GROUPS = [
    (root_causes.REPORTED_Q, "Tagging judgment: time_rollup on flows",
     "The draft's rule reads the reported value as is, so the tool looked for reported fiscal "
     "quarters that the filings do not have.",
     "judgment"),
    (root_causes.LINEAGE, "Missing source URL in the inputs",
     "An input gap, not a model error: the input packets for the two macro series held no URL, so "
     "the draft could not supply one and the tool refused.", "inputgap"),
    (root_causes.HIERARCHY, "Missing hierarchy, and the engine crashed",
     "The draft left the brand-to-parent hierarchy empty; the engine at the time raised an error on "
     "it instead of refusing cleanly.", "crash"),
    (root_causes.METHOD, "Method missing from the draft",
     "The draft's valid_methods left out a method the question needed.", "method"),
    (root_causes.NONE, "No tag involved",
     "Only tool errors not tied to a tag difference (wrong metric names or periods).", "none"),
]


def die(msg):
    sys.exit(f"followup_section: {msg}")


def e(x):
    return html.escape(str(x), quote=True)


def _yaml(path):
    return yaml.safe_load(Path(path).read_text())


def _json(path):
    if not Path(path).exists():
        die(f"missing {Path(path).relative_to(ROOT)}")
    return json.loads(Path(path).read_text())


def prereg_commit():
    out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%h", "--",
                          "followup/autotag/PREREG.md"], cwd=ROOT, capture_output=True, text=True)
    commits = out.stdout.split()
    if out.returncode or len(commits) != 1:
        die(f"cannot find the commit that added PREREG.md (git said {out.stdout!r} {out.stderr!r})")
    return commits[0]


def sentence_with(text, word):
    hits = [s for s in re.split(r"(?<=[.!?])\s+", text) if word in s]
    if len(hits) != 1:
        die(f"expected one sentence containing {word!r}, found {len(hits)}")
    return hits[0]


def load():
    hand_list = _yaml(HAND_TAGS)
    hand = {t["id"]: t for t in hand_list}
    drafts = {n: _yaml(AUTOTAG / "drafts" / f"{n}.yaml") for n in DRAFTS}
    d1 = {t["id"]: t for t in drafts["draft_1"]}
    metas = {n: _json(AUTOTAG / "drafts" / f"{n}_meta.json") for n in DRAFTS}
    st = _json(AUTOTAG / "results" / "score_tags.json")
    replay = _json(ENGINE_REPLAY)
    questions = {q["id"]: q for q in _yaml(QUESTIONS)}

    hand_scored, _, _ = score_d.score_records(score_d.HAND_D)
    draft_path = AUTOTAG / "results" / "D_autotag.jsonl"
    draft_scored, draft_runs, _ = score_d.score_records(draft_path)
    lost = sorted(k for k, s in draft_scored.items() if not s["correct"])
    classes = Counter(m4.classify(draft_runs[k]) for k in lost)

    groups = {}
    for k in lost:
        cause, _ = root_causes.primary_cause(root_causes.run_causes(draft_runs[k], hand, d1))
        groups.setdefault(cause, []).append(k)
    unknown = set(groups) - {g[0] for g in GROUPS}
    if unknown:
        die(f"root causes without a label: {unknown}")

    # Worked example: op_cash_flow in draft 1, the hand rule, and the tool's refusal in a q012 run.
    dt, ht = d1[EXAMPLE_TAG], hand[EXAMPLE_TAG]
    refusal = None
    for (qid, run), rec in sorted(draft_runs.items()):
        if qid != EXAMPLE_Q:
            continue
        for tc in rec["tool_calls"]:
            text = json.loads(tc["output"]).get("explanation") or ""
            if tc["is_error"] and text.startswith("insufficient data"):
                refusal = {"run": run, "tool": tc["name"], "input": tc["input"], "text": text}
                break
        if refusal:
            break
    if refusal is None:
        die(f"no insufficient-data refusal in the {EXAMPLE_Q} draft-1 runs")

    return {
        "prereg_commit": prereg_commit(),
        "tagging_model": metas["draft_1"]["model"],
        "hand_correct": sum(s["correct"] for s in hand_scored.values()), "hand_runs": len(hand_scored),
        "draft_correct": sum(s["correct"] for s in draft_scored.values()), "draft_runs": len(draft_scored),
        "lost": len(lost), "silent": classes.get(m4.SILENT, 0),
        "runs_per_question": max(r for _, r in draft_scored),
        "questions_tested": len({q for q, _ in draft_scored}),
        "m3_pass": {n: st["drafts"][n]["m3"]["pass"] for n in DRAFTS},
        "dangerous": {n: sum(len(v) for v in st["drafts"][n]["m2"].values()) for n in DRAFTS},
        "measures": len(st["drafts"]["draft_1"]["m1"]),
        "minutes": {n: metas[n]["wall_clock_seconds_this_process"] / 60 for n in DRAFTS},
        "cost": {n: metas[n]["cost_usd"] for n in DRAFTS},
        "groups": [(c, label, note, css, sorted({q for q, _ in groups.get(c, [])}), len(groups.get(c, [])))
                   for c, label, note, css in GROUPS if groups.get(c)],
        "example": {"question": questions[EXAMPLE_Q]["question"],
                    "sentence": sentence_with(dt["description"], "cumulative"),
                    "draft": {f: dt.get(f) for f in ("additive_over_time", "time_rollup", "valid_methods")},
                    "hand": {f: ht.get(f) for f in ("additive_over_time", "time_rollup", "valid_methods")},
                    "hand_derivation": ht.get("derivation"), "refusal": refusal},
        "verdicts": st["verdicts"],
        "replay": replay,
    }


# ---------- rendering ----------

STYLE = """<style>
#followup h3 { margin-top: 28px; }
#followup .fu-steps { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; gap: 10px; align-items: stretch; margin: 16px 0; }
#followup .fu-step { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
#followup .fu-step b { display: block; }
#followup .fu-step.now { border: 2px solid var(--accent); background: var(--accent-soft); }
#followup .fu-arrow { align-self: center; color: var(--muted); font-size: 1.2rem; }
#followup .fu-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 12px 0 20px; }
#followup .fu-card { border: 1px solid var(--line); border-radius: 10px; padding: 14px; min-width: 0; }
#followup .fu-card .big { font-size: 1.45rem; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.25; }
#followup .fu-card .lbl { font-size: 0.85rem; color: var(--muted); margin-bottom: 4px; }
#followup .fu-card .sub { font-size: 0.85rem; color: var(--muted); margin-top: 6px; }
#followup .fu-stack { display: flex; height: 28px; border-radius: 6px; overflow: hidden; margin: 12px 0 8px; border: 1px solid var(--line); }
#followup .fu-seg { height: 100%; }
#followup .fu-seg + .fu-seg { border-left: 2px solid var(--surface); }
#followup .judgment { background: var(--warn); }
#followup .inputgap { background: repeating-linear-gradient(45deg, var(--muted) 0 6px, var(--line) 6px 10px); }
#followup .crash { background: var(--bad); }
#followup .method { background: var(--accent); }
#followup .none { background: var(--line); }
#followup .fu-legend { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 6px 16px; list-style: none; padding: 0; margin: 0 0 12px; font-size: 0.9rem; }
#followup .fu-legend li { display: flex; gap: 8px; align-items: baseline; margin: 0; }
#followup .sw { flex: none; width: 12px; height: 12px; border-radius: 3px; border: 1px solid var(--line); transform: translateY(1px); }
#followup .fu-example { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 10px 0; }
#followup .fu-example .col { overflow-wrap: anywhere; }
#followup .fu-example .col.full { grid-column: 1 / -1; }
#followup blockquote { margin: 6px 0; padding: 6px 12px; border-left: 3px solid var(--accent); background: var(--code); border-radius: 0 6px 6px 0; }
#followup .tag-input { display: inline-block; background: var(--code); border-radius: 6px; padding: 1px 6px; }
#followup .box ul { margin-bottom: 0; }
@media (max-width: 600px) {
  #followup .fu-steps { grid-template-columns: 1fr; }
  #followup .fu-arrow { transform: rotate(90deg); justify-self: center; }
  #followup .fu-cards, #followup .fu-example, #followup .fu-legend { grid-template-columns: 1fr; }
}
</style>"""


def money(x):
    return f"${x:.2f}"


def rule_text(r):
    return (f"additive_over_time: {str(r['additive_over_time']).lower()}, "
            f"time_rollup: {r['time_rollup']}, valid_methods: [{', '.join(r['valid_methods'])}]")


def links(repo):
    base = f"{repo}/blob/main/followup"
    return {"results": f"{base}/autotag/RESULTS.md", "replay": f"{base}/engine_fix/REPLAY.md",
            "prereg": f"{base}/autotag/PREREG.md", "deviations": f"{base}/autotag/PREREG_DEVIATIONS.md"}


def top_line():
    return ('\n    <p class="lede small"><a href="#followup">Follow-up: model-drafted tags and engine '
            'hardening</a></p>')


def section(d, repo):
    L = links(repo)
    rp = d["replay"]
    if d["lost"] != d["draft_runs"] - d["draft_correct"] or sum(g[5] for g in d["groups"]) != d["lost"]:
        die("root-cause groups do not add up to the lost runs")
    passing = sum(d["m3_pass"].values())
    dangerous = ", ".join(f"{d['dangerous'][n]}" for n in DRAFTS)
    per_draft = "; ".join(f"draft {n.split('_')[1]}: {d['minutes'][n]:.1f} min, {money(d['cost'][n])}"
                          for n in DRAFTS)
    prereg_at = f"{repo}/blob/{d['prereg_commit']}/followup/autotag/PREREG.md"

    cards = [
        ("Setup D, correct runs",
         f"{d['hand_correct']}/{d['hand_runs']} → {d['draft_correct']}/{d['draft_runs']}",
         "hand tags → draft-1 tags"),
        ("Silent wrong answers on the questions tested", f"{d['silent']}",
         "permissive methods not exercised, see below"),
        ("Drafts passing the validator", f"{passing} of {len(DRAFTS)}",
         f"dangerous errors per draft: {dangerous}"),
        ("Time and cost per draft", f"{d['minutes']['draft_1']:.1f} min, {money(d['cost']['draft_1'])}",
         per_draft),
        ("Replay of the main study's tool calls",
         f"{rp['hand']['identical']}/{rp['hand']['calls']} identical", "on the hardened engine"),
    ]
    cards_html = "".join(f'<div class="fu-card"><div class="lbl">{e(a)}</div><div class="big">{e(b)}</div>'
                         f'<div class="sub">{e(c)}</div></div>' for a, b, c in cards)

    total = d["lost"]
    segs = "".join(f'<div class="fu-seg {css}" style="width:{n / total * 100:.4f}%" title="{e(label)}: {n}"></div>'
                   for _, label, _, css, _, n in d["groups"])
    legend = "".join(f'<li><span class="sw {css}" aria-hidden="true"></span><span><b>{n}</b> {e(label)}'
                     f'{" (input gap, not a model error)" if css == "inputgap" else ""}</span></li>'
                     for _, label, _, css, _, n in d["groups"])
    aria = "; ".join(f"{label}: {n} runs" for _, label, _, _, _, n in d["groups"])
    rows = "".join(f'<tr><th scope="row">{e(label)}</th><td data-label="What happened">{e(note)}</td>'
                   f'<td data-label="Questions">{e(", ".join(qs))}</td><td data-label="Runs">{n}</td></tr>'
                   for _, label, note, _, qs, n in d["groups"])

    x = d["example"]
    ref = x["refusal"]
    verdict_rows = "".join(
        f'<tr><th scope="row"><code>{e(f)}</code></th>'
        f'<td data-label="Entries scored per draft">{e(v["entries_per_draft"]["draft_1"])}</td>'
        f'<td data-label="Verdict"><span class="badge {"ok" if v["verdict"] == "safe to auto-draft" else "warn"}">'
        f'{e(v["verdict"])}</span></td></tr>' for f, v in d["verdicts"].items())
    safe = sum(v["verdict"] == "safe to auto-draft" for v in d["verdicts"].values())

    if rp["permissive"]["numbers_after"] != 1:
        die("the text about the one remaining number no longer matches replay.json")
    hard_rows = [
        ("Engine exceptions on draft 1's recorded tool calls",
         rp["draft_1"]["old_exceptions"], rp["draft_1"]["new_exceptions"]),
        ("Numbers returned for a method the code path does not implement or the hand tag forbids "
         "(permissive pairs and the counterfactual)",
         rp["permissive"]["numbers_before"], rp["permissive"]["numbers_after"]),
        ("Main-study tool calls with identical output",
         f"{rp['hand']['calls']} recorded", f"{rp['hand']['identical']} of {rp['hand']['calls']}"),
    ]
    hard_html = "".join(f'<tr><th scope="row">{e(a)}</th><td data-label="Before">{e(b)}</td>'
                        f'<td data-label="After">{e(c)}</td></tr>' for a, b, c in hard_rows)

    return f"""

<section id="followup">
{STYLE}
  <div class="kicker">Follow-up</div>
<h2>Follow-up: can a model write the tags?</h2>
<p>A pre-registered follow-up (<a href="{e(prereg_at)}">PREREG.md</a>, commit
<code>{e(d['prereg_commit'])}</code>), run after the main study, asked {e(d['tagging_model'])} to draft
the tags from vendor-side inputs only; it does not change the main results above.</p>
<ol class="fu-steps" style="list-style:none;padding:0">
<li class="fu-step"><b>Measure</b><span class="small muted">Main study: hand-written tags, four setups.</span></li>
<li class="fu-arrow" aria-hidden="true">→</li>
<li class="fu-step now"><b>Auto-tag</b><span class="small muted">Follow-up: a model drafts the tags; setup D reruns on them.</span></li>
<li class="fu-arrow" aria-hidden="true">→</li>
<li class="fu-step"><b>Harden</b><span class="small muted">Engine fix: refuse what the code does not implement.</span></li>
</ol>
<div class="fu-cards">{cards_html}</div>

<h3>Why {d['lost']} runs were lost</h3>
<p class="small muted">Each lost draft-1 run gets one root cause, read from its tool outputs
(<code>followup/autotag/root_causes.py</code>).</p>
<div class="fu-stack" role="img" aria-label="{e(aria)}">{segs}</div>
<ul class="fu-legend">{legend}</ul>
<div class="table-wrap"><table class="stack"><thead><tr><th scope="col">Cause</th><th scope="col">What happened</th>
<th scope="col">Questions</th><th scope="col">Runs</th></tr></thead><tbody>{rows}</tbody></table></div>

<h3>One worked example: <code>{e(EXAMPLE_TAG)}</code></h3>
<p class="small muted">{e(EXAMPLE_Q)}: “{e(x['question'])}”</p>
<div class="fu-example">
<div class="col"><div class="small muted">Draft 1's own description</div><blockquote>{e(x['sentence'])}</blockquote></div>
<div class="col"><div class="small muted">Draft 1's rule</div><p><code>{e(rule_text(x['draft']))}</code></p></div>
<div class="col"><div class="small muted">Hand rule</div><p><code>{e(rule_text(x['hand']))}</code></p>
<p class="small muted">{e(x['hand_derivation'])}</p></div>
<div class="col"><div class="small muted">The tool's refusal (run {e(ref['run'])}, <code>{e(ref['tool'])}</code>
<span class="tag-input">{e(json.dumps(ref['input']))}</span>)</div><blockquote>{e(ref['text'])}</blockquote></div>
</div>
<p class="small">The draft says the values are cumulative, then gives a rule that reads the reported
value as is. A fiscal quarter after the first exists only as a difference of two cumulative rows, so the
tool finds no reported quarter and refuses.</p>

<h3>Which fields can be auto-drafted</h3>
<p class="small muted">“Safe to auto-draft” only if all {len(DRAFTS)} drafts match the hand tag on every entry
scored for the field ({safe} of {len(d['verdicts'])} fields). From <code>followup/autotag/results/score_tags.json</code>.</p>
<div class="table-wrap"><table class="stack"><thead><tr><th scope="col">Field</th>
<th scope="col">Entries scored per draft</th><th scope="col">Verdict</th></tr></thead><tbody>{verdict_rows}</tbody></table></div>

<h3>Engine hardening, before and after</h3>
<div class="table-wrap"><table class="stack"><thead><tr><th scope="col"></th><th scope="col">Before</th>
<th scope="col">After</th></tr></thead><tbody>{hard_html}</tbody></table></div>
<p class="small">The remaining number is a correctly labelled mean that the draft tag allowed and the
hand tag forbids. That is a policy question for tags and their reviewers, not an engine bug. The new
validator rules catch {rp['validator']['caught']} of the {rp['validator']['errors']} draft errors; they
were derived from these same drafts, so this is not a test on new data.</p>

<div class="box"><h3>Limits of the follow-up</h3><ul>
<li>The hand tags are the ground truth, and they were written by the author.</li>
<li>{d['measures']} measures, one domain, one tagging model.</li>
<li>The root-cause analysis and the engine hardening came after the results and were not pre-registered.</li>
<li>{d['runs_per_question']} runs per question.</li>
</ul></div>
<p class="small"><a href="{e(L['results'])}">RESULTS.md</a> · <a href="{e(L['replay'])}">REPLAY.md</a> ·
<a href="{e(L['prereg'])}">PREREG.md</a> · <a href="{e(L['deviations'])}">PREREG_DEVIATIONS.md</a></p>
</section>"""
