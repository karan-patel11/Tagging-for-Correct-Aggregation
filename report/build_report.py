"""Phase 15a: build the static results page docs/index.html (SPEC §13.1).

Data comes only from eval/results/summary.json, eval/results/{A,B,C,D}.jsonl, eval/questions.yaml,
tags/tags.yaml and eval/verification_log.csv. report/replays.yaml picks the replays and holds the
plain-language notes; report/template.html holds the layout. Runs are scored with eval/score.py's
score_run, the same code that produced summary.json, so a replay badge always matches the summary.

The build fails loudly when an input file, a field or a number is missing, when a replay's recorded
result differs from what replays.yaml says it shows, or when the template contains a digit in its
text (numbers belong in the data, not the template).

The page is static: no backend, no API calls, no external scripts, and it opens from the file system.

Run: python report/build_report.py
"""

import csv
import html
import io
import json
import re
import sys
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import score  # noqa: E402  (scoring rules only; reads no files on import)

SUMMARY = ROOT / "eval" / "results" / "summary.json"
RESULTS = ROOT / "eval" / "results"
QUESTIONS = ROOT / "eval" / "questions.yaml"
TAGS = ROOT / "tags" / "tags.yaml"
VERIFICATION = ROOT / "eval" / "verification_log.csv"
REPLAYS = ROOT / "report" / "replays.yaml"
TEMPLATE = ROOT / "report" / "template.html"
OUT = ROOT / "docs" / "index.html"
ERROR_ANALYSIS = ROOT / "docs" / "error_analysis.md"

SETUP_NAMES = {"A": "Schema only", "B": "Prose descriptions", "C": "Tags file", "D": "Semantic tools"}
SETUP_TOOLS = {"A": "SQL", "B": "SQL", "C": "SQL", "D": "Semantic tools, no SQL"}
EXCERPT_CHARS = 420
CATEGORY_NAMES = {"time_additivity": "Balances over time", "ratios": "Ratios",
                  "ytd_calendar": "Year-to-date and fiscal calendars", "indices": "Price indices",
                  "hierarchy": "Brand hierarchy", "comparability_unanswerable": "Comparability and refusals"}


def die(msg):
    sys.exit(f"build_report: {msg}")


def need(d, *path):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            die(f"missing value {'.'.join(map(str, path))}")
        cur = cur[k]
    return cur


def read(path):
    if not path.exists():
        die(f"missing file {path.relative_to(ROOT)}")
    return path.read_text()


def e(x):
    return html.escape(str(x), quote=True)


def num(v):
    if v is None:
        return "null"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return f"{int(v):,}"


def pct(x, digits=1):
    return f"{x * 100:.{digits}f}%"


def answer_text(value, unit):
    return f"{num(value)} {unit}" if value is not None else "no number (refuse)"


def filing_url(url):
    """Link SEC archive folders to their filing index; preserve other source URLs."""
    m = re.fullmatch(r"(https://www\.sec\.gov/Archives/edgar/data/\d+/)(\d{10})(\d{2})(\d{6})/", url)
    if m:
        return f"{url}{m[2]}-{m[3]}-{m[4]}-index.htm"
    return url


# ---------- load ----------

def load():
    summary = json.loads(read(SUMMARY))
    questions = {q["id"]: q for q in yaml.safe_load(read(QUESTIONS))}
    tags = {t["id"]: t for t in yaml.safe_load(read(TAGS))}
    vlog = list(csv.DictReader(io.StringIO(read(VERIFICATION))))
    runs = {}
    for s in score.SETUPS:
        for line in read(RESULTS / f"{s}.jsonl").splitlines():
            if line.strip():
                r = json.loads(line)
                runs[(r["question_id"], r["setup"], r["run"])] = r
    replays = yaml.safe_load(read(REPLAYS))
    template = read(TEMPLATE)
    return summary, questions, tags, vlog, runs, replays, template


def check_template(template):
    text = re.sub(r"<style.*?</style>|<script.*?</script>", "", template, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{\{[A-Z_]+\}\}", " ", text)
    digits = re.findall(r"\S*\d\S*", text)
    if digits:
        die(f"template text contains numbers {digits}; numbers must come from the data")


# ---------- scoring helpers ----------

def scored(runs, questions, qid, setup, run):
    rec = runs.get((qid, setup, run)) or die(f"no recorded run {qid} {setup} run {run}")
    return rec, score.score_run(rec, questions[qid])


def outcome(sc):
    if not sc["parsed"]:
        return "unparsed"
    if sc["trap_hit"]:
        return "trap"
    return "correct" if sc["correct"] else "incorrect"


def badge(sc, q):
    o = outcome(sc)
    if o == "correct":
        return '<span class="badge ok">correct</span>'
    if o == "trap":
        return f'<span class="badge bad">wrong: trap {e(sc["trap_hit"])}</span>'
    if o == "unparsed":
        return '<span class="badge bad">wrong: no final answer</span>'
    f = sc["final"]
    if q["expected_behavior"] == "answer_with_warning" and sc["number_ok"] and not f["warning"]:
        why = "missing warning"
    elif q["expected_behavior"] != "refuse" and f["refused"]:
        why = "refused an answerable question"
    elif q["expected_behavior"] == "refuse":
        why = "answered an unanswerable question"
    else:
        why = "wrong number"
    return f'<span class="badge bad">wrong: {why}</span>'


def record(runs, questions, qid, setup):
    keys = sorted(k for k in runs if k[0] == qid and k[1] == setup)
    if not keys:
        die(f"no runs for {qid} {setup}")
    outs = [outcome(score.score_run(runs[k], questions[qid])) for k in keys]
    n_ok = outs.count("correct")
    detail = ", ".join(f"run {k[2]} {o}" for k, o in zip(keys, outs))
    return n_ok, len(keys), detail


def sources_for(vlog, qid):
    seen, out = set(), []
    for r in vlog:
        if r["question_id"] == qid and r["source_url"] not in seen:
            seen.add(r["source_url"])
            out.append(r["source_url"])
    if not out:
        die(f"no verification_log rows for {qid}")
    return out


# ---------- sections ----------

def section_problem(questions, runs, vlog, replays):
    qid = need(replays, "problem_question")
    q = questions.get(qid) or die(f"unknown problem_question {qid}")
    traps = need(q, "trap_answers")
    total = need(traps, "sum_of_4_quarter_ends")
    correct = need(q, "correct")
    n_ok = sum(score.score_run(r, q)["correct"] for k, r in runs.items() if k[0] == qid)
    n = sum(1 for k in runs if k[0] == qid)
    if not n:
        die(f"no runs for {qid}")
    link = filing_url(sources_for(vlog, qid)[0])
    result = (f"In this experiment no setup fell for it: all {n} runs on this question returned the "
              f"year-end balance." if n_ok == n else
              f"In this experiment {n_ok} of {n} runs on this question returned the year-end balance.")
    return f"""
<h2>SQL can run correctly and answer the wrong question.</h2>
<p>Total assets is a balance at a point in time. Summing quarter-end balances produces a valid SQL
result, but not annual total assets.</p>
<div class="compare">
  <div class="stat"><div class="muted small">Sum of Yum! Brands' four fiscal-year quarter-end balances
    (the trap; an illustration, not a recorded run)</div>
    <div class="big">{e(num(total))} {e(q["unit"])}</div>
    <pre>SELECT SUM(value) FROM fundamentals
WHERE ticker = 'YUM' AND metric = 'total_assets' AND fiscal_year = {e(q_fiscal_year(q))}</pre></div>
  <div class="stat"><div class="muted small">Total assets at fiscal year end, as filed (the right answer)</div>
    <div class="big">{e(num(correct))} {e(q["unit"])}</div>
    <p class="small"><a href="{e(link)}">Yum! Brands 10-K on SEC EDGAR</a></p></div>
</div>
<p class="muted">{e(result)} Other questions test quarter derivation, ratios, price indices and
brand rollups.</p>"""


def q_fiscal_year(q):
    m = re.search(r"fiscal (\d{4})", q["question"])
    return m.group(1) if m else die(f"no fiscal year in {q['id']} question text")


def bars(rows, with_range):
    """rows: (label, value, lo, hi, value_text), values 0..1. HTML bars on a zero-based scale."""
    out = ['<div class="bars" role="list">']
    for label, v, lo, hi, txt in rows:
        rng = (f'<span class="rng" style="left:{lo * 100:.2f}%;width:{(hi - lo) * 100:.2f}%" '
               f'title="lowest to highest run"></span>') if with_range and lo is not None else ""
        out.append(f'<div class="bar-row" role="listitem"><span class="bar-label">{e(label)}</span>'
                   f'<span class="track"><span class="fill{"" if with_range else " secondary"}" '
                   f'style="width:{v * 100:.2f}%"></span>{rng}</span><span class="bar-val">{e(txt)}</span></div>')
    out.append(f'<div class="bar-row axis"><span></span><span class="ticks"><span>{e(pct(0, 0))}</span>'
               f'<span>{e(pct(0.5, 0))}</span><span>{e(pct(1, 0))}</span></span><span></span></div></div>')
    return "\n".join(out)


def section_results(summary, questions):
    setups = need(summary, "setups")
    model = ", ".join(need(summary, "model"))
    dates = need(summary, "run_dates")
    if not isinstance(dates, list) or not dates:
        die("summary.run_dates not recorded")
    n_runs = len(need(summary, "runs_per_question"))
    qids = {q for v in setups.values() for q in need(v, "per_question")}
    n_q = len(qids)
    if n_q != len(questions):
        die(f"summary covers {n_q} questions, questions.yaml has {len(questions)}")
    acc_rows, ow_rows, table = [], [], []
    for s in score.SETUPS:
        v = setups.get(s) or die(f"summary has no setup {s}")
        a = need(v, "accuracy")
        mean, lo, hi = need(a, "mean"), need(a, "min"), need(a, "max")
        hits = sum(need(t, "hits") for t in need(v, "trap_hits").values())
        trap_runs = sum(need(t, "runs") for t in v["trap_hits"].values())
        ow, ow_n, ow_d = need(v, "over_warning_rate"), need(v, "over_warning_runs"), need(v, "answer_question_runs")
        label = f"{s} · {SETUP_NAMES[s]}"
        acc_rows.append((label, mean, lo, hi, pct(mean)))
        ow_rows.append((label, ow, None, None, pct(ow)))
        table.append(f"<tr><td>{e(label)}</td><td>{e(SETUP_TOOLS[s])}</td>"
                     f"<td>{need(v, 'correct_runs')} / {need(v, 'n')}</td>"
                     f"<td>{e(pct(mean))} <span class='muted'>(runs {e(pct(lo))}–{e(pct(hi))})</span></td>"
                     f"<td>{hits} / {trap_runs}</td><td>{ow_n} / {ow_d} ({e(pct(ow))})</td></tr>")
    sample = f"{n_q} questions × {n_runs} runs, {model}, run on {' and '.join(dates)} (UTC)"
    return f"""
<h2>Accuracy was close across all four setups.</h2>
<p class="muted">{e(sample)}. Bars show mean accuracy; markers show the lowest and highest run.
The axis starts at zero.</p>
{bars(acc_rows, True)}
<div class="table-wrap"><table>
<tr><th>Setup</th><th>Tools</th><th>Correct runs</th><th>Accuracy (run range)</th>
<th>Stored-trap hits / runs</th><th>Over-warning / answer-question runs</th></tr>
{''.join(table)}
</table></div>
<h3 style="margin-top:20px">Secondary metric: over-warning</h3>
<p class="muted">Warnings on questions labelled as needing an answer without a caveat. These count
separately from accuracy; the measure does not judge the wording of each caveat.</p>
{bars(ow_rows, False)}"""


def render_steps(rec):
    texts = rec.get("text") or []
    calls = rec.get("tool_calls") or []
    out = []
    for t in range(max(len(texts), 1 + max([c["turn"] for c in calls], default=-1))):
        txt = texts[t] if t < len(texts) else ""
        if txt.strip():
            out.append(f'<div class="step"><div class="tool muted">model text</div>{excerpt(txt)}</div>')
        for c in (c for c in calls if c["turn"] == t):
            inp = c["input"].get("sql") if isinstance(c["input"], dict) and "sql" in c["input"] else \
                json.dumps(c["input"], indent=1)
            err = ' <span class="badge bad">tool error</span>' if c.get("is_error") else ""
            out.append(f'<div class="step"><div class="tool">{e(c["name"])}{err}</div>'
                       f'<pre>{e(inp)}</pre><div class="muted small">returned</div>{excerpt(c["output"])}</div>')
    if not out:
        out.append('<p class="muted">No steps recorded.</p>')
    return "\n".join(out)


def excerpt(text):
    if len(text) <= EXCERPT_CHARS:
        return f"<pre>{e(text)}</pre>"
    return (f"<pre>{e(text[:EXCERPT_CHARS])}…</pre><details><summary>show full</summary>"
            f"<pre>{e(text)}</pre></details>")


def source_links(urls):
    """Answer-key sources from verification_log.csv, labelled by where they point."""
    def label(u):
        if "sec.gov" in u:
            m = re.search(r"/(\d{10})(\d{2})(\d{6})(?:/|$)", u)
            doc = "SEC exhibit" if u.endswith(".htm") and not u.endswith("-index.htm") else "SEC filing"
            return f"{doc} {m.group(1)}-{m.group(2)}-{m.group(3)}" if m else doc
        if "pageviews.wmcloud.org" in u:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            pages = qs.get("pages", ["?"])[0].replace("|", ", ")
            return f"Pageviews Analysis: {pages}, {qs.get('start', ['?'])[0]} to {qs.get('end', ['?'])[0]}"
        if "wikimedia" in u:
            m = re.search(r"/per-article/en\.wikipedia/[^/]+/[^/]+/([^/]+)/", u)
            return f"Wikimedia pageviews: {m.group(1)}" if m else "Wikimedia pageviews"
        return re.sub(r"^https?://", "", u).split("/")[0]
    items = [f'<a href="{e(filing_url(u))}">{e(label(u))}</a>' for u in urls]
    if len(items) <= 3:
        return "Answer-key sources: " + " · ".join(items)
    return (f"<details><summary>Answer-key sources ({len(items)})</summary>"
            + "<br>".join(items) + "</details>")


def pane(runs, questions, vlog, qid, setup, run):
    q = questions[qid]
    rec, sc = scored(runs, questions, qid, setup, run)
    n_ok, n, detail = record(runs, questions, qid, setup)
    f = sc["final"]
    if f:
        final = (f"{e(answer_text(f['answer'], f['unit']))} · warning {str(f['warning']).lower()} · "
                 f"refused {str(f['refused']).lower()}")
        if f["warning"]:
            final += ' <span class="badge warn">warning</span>'
    else:
        final = f"no final answer (stopped: {e(rec.get('stop_reason'))})"
    expected = ("refuse" if q["expected_behavior"] == "refuse" else
                f"{answer_text(q['correct'], q['unit'])}"
                + (" with a warning" if q["expected_behavior"] == "answer_with_warning" else ""))
    links = source_links(sources_for(vlog, qid))
    return f"""
<div class="pane" data-setup="{e(setup)}">
<h3>{e(setup)} · {e(SETUP_NAMES[setup])} <span class="muted small">run {run}</span></h3>
<details class="run-record"><summary>{n_ok} of {n} runs correct · view run results</summary>
<p class="record">{e(detail)}.</p></details>
<div class="final"><div>{badge(sc, q)}</div>
<p class="small"><b>Final answer:</b> {final}</p>
<p class="small"><b>Correct answer:</b> {e(expected)}</p>
<p class="small">{links}</p></div>
<details class="trace"><summary>View recorded steps · {len(rec.get('tool_calls') or [])} tool calls</summary>
<div class="trace-body">{render_steps(rec)}</div></details>
</div>"""


def section_replays(runs, questions, vlog, replays):
    items = need(replays, "replays")
    if len(items) != len(CATEGORY_NAMES):
        die(f"replays.yaml lists {len(items)} replays; SPEC §13.1 asks for one per category")
    cats = [questions[need(r, "question_id")]["category"] for r in items]
    if sorted(cats) != sorted(CATEGORY_NAMES):
        die(f"replays must cover each category once, got {cats}")
    buttons, blocks = [], []
    for r in items:
        qid = r["question_id"]
        q = questions.get(qid) or die(f"unknown replay question {qid}")
        shown = need(r, "runs")
        expect = need(r, "expect")
        for s in score.SETUPS:
            _, sc = scored(runs, questions, qid, s, need(shown, s))
            if outcome(sc) != need(expect, s):
                die(f"{qid} {s} run {shown[s]} scored {outcome(sc)}, replays.yaml expects {expect[s]}")
        cat = CATEGORY_NAMES[q["category"]]
        buttons.append(f'<button type="button" data-q="{e(qid)}">{e(cat)}</button>')
        left = "".join(pane(runs, questions, vlog, qid, s, shown[s]) for s in "ABC")
        tabs = "".join(f'<button type="button" data-setup="{s}">{s} · {e(SETUP_NAMES[s])}</button>' for s in "ABC")
        blocks.append(f"""
<div class="replay" data-q="{e(qid)}">
<h3>{e(cat)}: {e(q["question"])}</h3>
<div class="note small">{e(need(r, "note"))}</div>
<div class="replay-cols">
  <div class="col"><div class="tabs js-only">{tabs}</div>{left}</div>
  <div class="col">{pane(runs, questions, vlog, qid, "D", shown["D"])}</div>
</div>
</div>""")
    return f"""
<h2>Compare recorded answers.</h2>
<p class="muted">{len(items)} questions, one per category. Compare A, B or C with D. Answers and scores
appear first; expand recorded steps for the original model text and tool responses.</p>
<div class="picker js-only">{''.join(buttons)}</div>
{''.join(blocks)}"""


def section_tags(tags, replays):
    cards = []
    fields = ["semantic_type", "additive_over_time", "time_rollup", "valid_methods", "period_basis",
              "derivation", "calendar"]
    for c in need(replays, "tag_cards"):
        t = tags.get(need(c, "id")) or die(f"unknown tag {c['id']}")
        rows = "".join(f"<dt>{e(k)}</dt><dd>{e(', '.join(t[k]) if isinstance(t[k], list) else t[k])}</dd>"
                       for k in fields if k in t)
        cards.append(f'<div class="card"><h3><code>{e(t["id"])}</code></h3>'
                     f'<p>{e(need(c, "sentence"))}</p><dl>{rows}</dl></div>')
    return f"""
<h2>Rules attached to each metric.</h2>
<p class="muted">C receives the full tags file. D reads tags through describe_column; aggregate checks
which methods are allowed.</p>
<div class="cards">{''.join(cards)}</div>"""


def section_b_vs_c(summary, questions):
    bc = need(summary, "b_vs_c")
    n = need(bc, "questions")
    diff_b, diff_c = need(bc, "b_right_c_wrong"), need(bc, "c_right_b_wrong")
    same = need(bc, "both_right") + need(bc, "both_wrong")
    if same + len(diff_b) + len(diff_c) != n:
        die("b_vs_c counts do not add up")
    n_runs = len(need(summary, "runs_per_question"))
    diffs = "".join(f"<li><b>{e(q)}</b>: {e(questions[q]['question'])} ({side})</li>"
                    for qs, side in ((diff_b, "B right, C wrong"), (diff_c, "C right, B wrong")) for q in qs)
    return f"""
<div class="box">
<h2>Prose and tags gave similar results.</h2>
<p>B and C receive the same facts in different formats: sentences and structured tags.
By majority vote across {n_runs} runs, their scored outcomes agree on
<b>{same} of {n}</b> questions. The difference:</p>
<ul>{diffs or "<li>None.</li>"}</ul>
<p class="muted">This small sample does not establish that one format is better. No statistical
significance test was performed.</p>
</div>"""


def section_checks(summary, questions, vlog, replays):
    n_rows = len(vlog)
    n_yes = sum(r["matches"].strip().lower() == "yes" for r in vlog)
    hand = [r for r in vlog if "hand-read by" in r["notes"]]
    hand_q = len({r["question_id"] for r in hand})
    verified_q = len({r["question_id"] for r in vlog if r["matches"].strip().lower() == "yes"})
    per_cat = {}
    for q in questions.values():
        per_cat[q["category"]] = per_cat.get(q["category"], 0) + 1
    qpc = min(per_cat.values()) if len(set(per_cat.values())) == 1 else \
        f"{min(per_cat.values())}–{max(per_cat.values())}"
    ciks = {m.group(1) for r in vlog for m in [re.search(r"edgar/data/(\d+)/", r["source_url"])] if m}
    lims = "".join(f"<li>{e(l.format(questions_per_category=qpc, companies=len(ciks)))}</li>"
                   for l in need(replays, "limitations"))
    notes = []
    for n in need(summary, "scorer_notes"):
        by = ", ".join(f"{k} {v}" for k, v in need(n, "flipped_by_setup").items())
        before, after = need(n, "correct_before"), need(n, "correct_after")
        rows = "".join(f"<tr><td>{e(k)}</td><td>{before[k]}</td><td>{after[k]}</td></tr>" for k in before)
        notes.append(f"""
<h3>Scorer bug, found and fixed before publishing</h3>
<p>{e(need(n, "description"))}</p>
<p>The fix (commit <code>{e(need(n, "fix_commit"))}</code>) changed {need(n, "runs_flipped")} runs
({e(by)}), all on {e(", ".join(need(n, "flipped_questions")))}, all from incorrect to correct. The
scoring rule did not change.</p>
<div class="table-wrap"><table><tr><th>Setup</th><th>Correct runs before the fix</th><th>After</th></tr>{rows}</table></div>""")
    links = need(replays, "links")
    repo = need(links, "repo")
    ea_path = need(links, "error_analysis")
    ea = (f'<a href="{e(Path(ea_path).name)}">Error analysis</a>' if ERROR_ANALYSIS.exists()
          else f"Error analysis: not written yet ({e(ea_path)}).")
    return f"""
<h2>How the answers were checked</h2>
<ul>
<li>The answer key was computed with direct SQL in <code>eval/make_questions.py</code>, never with
<code>semantics.py</code>, so the code being tested did not grade itself.</li>
<li>{n_yes} of {n_rows} source values behind the {verified_q} questions were checked against the
filings and agency data and marked as matching in <code>eval/verification_log.csv</code>; {len(hand)}
of them, across {hand_q} questions, were read by hand from the filing HTML by the author.</li>
<li>The questions were frozen (git tag <code>questions-frozen</code>) before any evaluation run.</li>
<li>Total model cost of the run: ${need(summary, "total_cost_usd"):.2f}.</li>
</ul>
{''.join(notes)}
<h3>Limits of this experiment</h3>
<ul>{lims}</ul>
<p><a href="{e(repo)}">Repository</a> · {ea}</p>"""


def main():
    summary, questions, tags, vlog, runs, replays, template = load()
    check_template(template)
    model = ", ".join(need(summary, "model"))
    parts = {
        "SECTION_PROBLEM": section_problem(questions, runs, vlog, replays),
        "SECTION_RESULTS": section_results(summary, questions),
        "SECTION_REPLAYS": section_replays(runs, questions, vlog, replays),
        "SECTION_TAGS": section_tags(tags, replays),
        "SECTION_B_VS_C": section_b_vs_c(summary, questions),
        "SECTION_CHECKS": section_checks(summary, questions, vlog, replays),
        "FOOTER": e(f"Generated by report/build_report.py from the recorded runs of {model}. "
                    "A static page: no model is called."),
    }
    page = template
    for k, v in parts.items():
        if "{{" + k + "}}" not in page:
            die(f"template has no {{{{{k}}}}} placeholder")
        page = page.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    if left:
        die(f"unfilled placeholders {left}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page)
    if not ERROR_ANALYSIS.exists():
        print("note: docs/error_analysis.md does not exist yet; the page says so instead of linking it")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
