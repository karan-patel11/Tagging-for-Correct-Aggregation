"""Phase 15a: build the static results page docs/index.html (SPEC §13.1).

Data comes only from eval/results/summary.json, eval/results/{A,B,C,D}.jsonl, eval/questions.yaml,
tags/tags.yaml, eval/verification_log.csv, report/over_warning_reasons.json (written by
report/analyze_over_warnings.py from the same runs) and followup/engine_fix/replay.json (written by
followup/engine_fix/replay.py, for the engine-hardening line under "Limits"). The follow-up section
after the main results is built by report/followup_section.py from the follow-up's committed output
files (listed there). report/replays.yaml picks the replays and holds the
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
sys.path.insert(0, str(ROOT / "report"))

import score  # noqa: E402  (scoring rules only; reads no files on import)
import followup_section  # noqa: E402  (report/followup_section.py: the follow-up section)

SUMMARY = ROOT / "eval" / "results" / "summary.json"
RESULTS = ROOT / "eval" / "results"
QUESTIONS = ROOT / "eval" / "questions.yaml"
TAGS = ROOT / "tags" / "tags.yaml"
VERIFICATION = ROOT / "eval" / "verification_log.csv"
REPLAYS = ROOT / "report" / "replays.yaml"
TEMPLATE = ROOT / "report" / "template.html"
OUT = ROOT / "docs" / "index.html"
ERROR_ANALYSIS = ROOT / "docs" / "error_analysis.md"
OVER_WARNINGS = ROOT / "report" / "over_warning_reasons.json"
ENGINE_REPLAY = ROOT / "followup" / "engine_fix" / "replay.json"
OW_LABEL = "Warnings on questions whose key expects no caveat"

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
    ow = json.loads(read(OVER_WARNINGS))
    return summary, questions, tags, vlog, runs, replays, template, ow


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

def section_intro(questions, tags, replays):
    t = tags.get("fundamentals.total_assets") or die("tags.yaml has no fundamentals.total_assets")
    rule = f"additive_over_time: {str(need(t, 'additive_over_time')).lower()}, time_rollup: {need(t, 'time_rollup')}"
    counts = {}
    for q in questions.values():
        counts[q["expected_behavior"]] = counts.get(q["expected_behavior"], 0) + 1
    names = {"answer": "answer", "answer_with_warning": "answer with warning", "refuse": "refuse"}
    if set(counts) != set(names):
        die(f"unexpected expected_behavior values {sorted(counts)}")
    behaviours = ", ".join(f"<b>{e(names[k])}</b> ({counts[k]} questions)" for k in names)
    score_link = need(need(replays, "links"), "repo") + "/blob/main/eval/score.py"
    return f"""
<p class="lede">One model answered the same restaurant-finance questions in four setups. This page
replays the recorded runs. It does not call a model.</p>
<p class="lede"><b>Tag:</b> a rule attached to a metric, kept in <code>tags/tags.yaml</code>. For
example, the <code>total_assets</code> tag sets <code>{e(rule)}</code> and reads: “{e(need(t, "derivation"))}”
In plain terms: a balance; never sum it across quarters.</p>
<details class="glossary"><summary>Terms used on this page</summary>
<dl class="defs">
<dt>Setups</dt><dd>A sees only the table schema. B gets prose sentences generated from the tags. C
gets the tags file itself. D gets semantic tools that apply the tags, and no SQL.</dd>
<dt>Expected behaviour</dt><dd>Each question's answer key expects one of three: {behaviours}.</dd>
<dt>FINAL line</dt><dd>Every run ends with a FINAL line: the number, its unit and two flags.
<code>warning=true</code> means the model attached a caveat to its number;
<code>refused=true</code> means it declined to give a number.</dd>
<dt>Stored trap</dt><dd>A specific wrong answer computed in advance for a question, such as the sum
of four quarter-end balances. A run hits the trap when its number lands within tolerance of it.</dd>
<dt>Correct</dt><dd>The run's behaviour matches the key and, unless the key expects a refusal, its
number is within a per-unit tolerance defined in <a href="{e(score_link)}">eval/score.py</a>.</dd>
</dl></details>"""


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


def section_results(summary, questions, ow):
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
    # score.py checks every stored trap of every non-refuse question, so one run is checked once per trap.
    n_traps = sum(len(q.get("trap_answers") or {}) for q in questions.values()
                  if q["expected_behavior"] != "refuse")
    ow_setups = need(ow, "setups")
    n_corr = need(ow, "n_manual_corrections")
    if n_corr != len(need(ow, "manual_corrections")):
        die("over_warning_reasons.json: n_manual_corrections does not match its list")
    method = f"keyword match plus {n_corr} manual correction{'' if n_corr == 1 else 's'}"
    heads = ["Setup", "Tools", "Correct runs", "Accuracy (run range)", "Stored-trap hits / trap checks*",
             f"{OW_LABEL} / runs on those questions",
             f"Of those warnings, cite filing dates or metadata ({method})"]
    acc_rows, ow_rows, table = [], [], []
    matched_total = ow_total = 0
    for s in score.SETUPS:
        v = setups.get(s) or die(f"summary has no setup {s}")
        a = need(v, "accuracy")
        mean, lo, hi = need(a, "mean"), need(a, "min"), need(a, "max")
        hits = sum(need(t, "hits") for t in need(v, "trap_hits").values())
        trap_checks = sum(need(t, "runs") for t in v["trap_hits"].values())
        if trap_checks != n_traps * n_runs:
            die(f"{s}: {trap_checks} trap checks in summary.json, questions.yaml gives "
                f"{n_traps} stored traps x {n_runs} runs")
        ow_r, ow_n, ow_d = need(v, "over_warning_rate"), need(v, "over_warning_runs"), need(v, "answer_question_runs")
        o = ow_setups.get(s) or die(f"over_warning_reasons.json has no setup {s}")
        if need(o, "warning_runs") != ow_n:
            die(f"{s}: over_warning_reasons.json counts {o['warning_runs']} runs, summary.json {ow_n}")
        matched = need(o, "matched")
        matched_total += matched
        ow_total += ow_n
        label = f"{s} · {SETUP_NAMES[s]}"
        acc_rows.append((label, mean, lo, hi, pct(mean)))
        ow_rows.append((label, ow_r, None, None, pct(ow_r)))
        cells = [f"{e(SETUP_TOOLS[s])}", f"{need(v, 'correct_runs')} / {need(v, 'n')}",
                 f"{e(pct(mean))} <span class='muted'>(runs {e(pct(lo))}–{e(pct(hi))})</span>",
                 f"{hits} / {trap_checks}", f"{ow_n} / {ow_d} ({e(pct(ow_r))})", f"{matched} / {ow_n}"]
        table.append(f"<tr><th scope='row'>{e(label)}</th>"
                     + "".join(f'<td data-label="{e(h)}"><span>{c}</span></td>' for h, c in zip(heads[1:], cells))
                     + "</tr>")
    if 2 * matched_total <= ow_total:
        die(f"only {matched_total} of {ow_total} warning runs match the keyword pattern; "
            "the page text says most do")
    n_setup = need(setups["A"], "n")
    sample = f"{n_q} questions × {n_runs} runs, {model}, run on {' and '.join(dates)} (UTC)"
    return f"""
<h2>Accuracy was close across all four setups.</h2>
<p class="muted">{e(sample)}. Bars show mean accuracy; markers show the lowest and highest run.
The axis starts at zero.</p>
<p>The setups differ by a few runs each. That is too few to rank them on this sample. Warning rates
differ more than accuracy; they are shown below.</p>
{bars(acc_rows, True)}
<div class="table-wrap"><table class="stack">
<thead><tr>{"".join(f'<th scope="col">{e(h)}</th>' for h in heads)}</tr></thead>
<tbody>{''.join(table)}</tbody>
</table></div>
<p class="small muted"><sup>*</sup> A run on a question with several stored traps is checked once per
trap: {n_traps} stored traps × {n_runs} runs = {n_traps * n_runs} trap checks per setup, against
{n_setup} runs per setup.</p>
<h3 style="margin-top:20px">Secondary metric: {e(OW_LABEL.lower())}</h3>
<p class="muted">Runs that set warning=true on a question whose answer key expects a plain answer.
Most of these cite stored filing dates or retrieval metadata ({e(method)}, listed in the JSON;
counts in the table).
The dataset keeps the latest-filed value, so prior-year figures carry later filings' dates; the
models flagged that. These are not scored as errors, and the metric does not show that any setup
hedges more or less well.</p>
{bars(ow_rows, False)}
<p class="small muted">Classification: {e(method)} (listed in the JSON). The keyword match is a
heuristic over each run's final text (<code>report/analyze_over_warnings.py</code>); the manual
corrections are runs whose full text was read and found misclassified
(<code>report/over_warning_overrides.json</code>). Pattern, corrections and run lists are in
<code>report/over_warning_reasons.json</code>. It does not judge each caveat.</p>"""


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


def calls_label(n):
    return f"{n} tool call" + ("" if n == 1 else "s")


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
<details class="trace"><summary>View recorded steps · {calls_label(len(rec.get('tool_calls') or []))}</summary>
<div class="trace-body">{render_steps(rec)}</div></details>
</div>"""


def remedy(r):
    """An optional fix the author proposes for an observed failure. It was not run or measured."""
    text = r.get("untested_remedy")
    return (f'<div class="note small remedy"><b>Possible fix, not tested:</b> {e(text)}</div>'
            if text else "")


def section_replays(runs, questions, vlog, replays, tags):
    items = need(replays, "replays")
    dedupe = need(tags.get("fundamentals.revenue") or die("tags.yaml has no fundamentals.revenue"),
                  "lineage", "dedupe")
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
<div class="note small">{e(need(r, "note"))}</div>{remedy(r)}
<div class="replay-cols">
  <div class="col"><div class="tabs js-only">{tabs}</div>{left}</div>
  <div class="col">{pane(runs, questions, vlog, qid, "D", shown["D"])}</div>
</div>
</div>""")
    return f"""
<h2>Compare recorded answers.</h2>
<p class="muted">{len(items)} questions, one per category. Compare A, B or C with D. Answers and scores
appear first; expand recorded steps for the original model text and tool responses.</p>
<p class="small muted"><b>Filing dates in the replays.</b> The dataset rule, from the tags' lineage
and the SPEC decisions log: “{e(dedupe)}” So a stored prior-year figure for revenue, income or cash
flow can carry the accession number and filing date of a later filing that repeated it as a
comparative. This is by design. Replay text in which a model remarks on odd filing dates is
describing that rule, not corrupt data.</p>
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


def warning_line(runs, questions, qid):
    """For a B/C difference on an answer-with-warning question: who warned, and that every number was right."""
    q = questions[qid]
    if q["expected_behavior"] != "answer_with_warning":
        die(f"{qid}: B/C difference is not on an answer_with_warning question; no wording for it")
    counts = {}
    for s in score.SETUPS:
        keys = sorted(k for k in runs if k[0] == qid and k[1] == s) or die(f"no runs for {qid} {s}")
        scs = [score.score_run(runs[k], q) for k in keys]
        if not all(sc["number_ok"] for sc in scs):
            die(f"{qid} {s}: not every run's number is correct; the page says it is")
        counts[s] = (sum(bool(sc["final"]["warning"]) for sc in scs), len(scs))
    w = {s: f"{counts[s][0]}/{counts[s][1]}" for s in counts}
    return (f"B warned in {w['B']} runs, C in {w['C']} (A in {w['A']}, D in {w['D']}). "
            "The numbers were correct in all runs; only the warning differed.")


def section_b_vs_c(summary, questions, runs):
    bc = need(summary, "b_vs_c")
    n = need(bc, "questions")
    diff_b, diff_c = need(bc, "b_right_c_wrong"), need(bc, "c_right_b_wrong")
    same = need(bc, "both_right") + need(bc, "both_wrong")
    if same + len(diff_b) + len(diff_c) != n:
        die("b_vs_c counts do not add up")
    n_runs = len(need(summary, "runs_per_question"))
    majority = n_runs // 2 + 1
    diffs = "".join(f"<li><b>{e(q)}</b>: {e(questions[q]['question'])} {e(warning_line(runs, questions, q))}</li>"
                    for q in diff_b + diff_c)
    n_diff = len(diff_b) + len(diff_c)
    return f"""
<div class="box">
<h2>Prose and tags gave similar results.</h2>
<p>B and C receive the same facts in different formats: sentences and structured tags.
<b>Majority vote</b> means a setup counts as right on a question when more than half of its runs on
that question are correct ({majority} of {n_runs}). By majority vote, their scored outcomes agree on
<b>{same} of {n}</b> questions. The difference:</p>
<ul>{diffs or "<li>None.</li>"}</ul>
<p class="muted">The difference is {n_diff} question{"" if n_diff == 1 else "s"}, {n_runs} runs each.
This small sample does not establish that one format is better. No statistical significance test was
performed.</p>
</div>"""


HAND_RE = re.compile(r"hand-read by|hand spot-check by")


def source_kind(url):
    if "sec.gov" in url:
        return "SEC"
    if "census.gov" in url:
        return "Census"
    if "pageviews" in url or "wikimedia" in url:
        return "pageviews"
    if "bls.gov" in url:
        return "BLS"
    return "other"


def verification_breakdown(vlog, tags):
    """Hand-checked rows (by their notes) split by source, and whether the Census check is independent."""
    hand = [r for r in vlog if HAND_RE.search(r["notes"])]
    by_kind = {}
    for r in hand:
        by_kind.setdefault(source_kind(r["source_url"]), []).append(r)
    if set(by_kind) - {"SEC", "Census", "pageviews"}:
        die(f"hand-checked rows from unexpected sources {sorted(by_kind)}")
    sec = by_kind.get("SEC", [])
    census_file = need(tags.get("macro.food_services_sales") or die("no macro.food_services_sales tag"),
                       "lineage", "file")
    census = [r for r in vlog if source_kind(r["source_url"]) == "Census"]
    if not census or not all(census_file in r["notes"] for r in census):
        die("Census verification notes do not all name the ingested workbook; page wording needs review")
    b = {"total": len(vlog), "hand": len(hand), "hand_sec": len(sec),
         "hand_sec_questions": len({r["question_id"] for r in sec}),
         "hand_census": len(by_kind.get("Census", [])), "hand_pageviews": len(by_kind.get("pageviews", [])),
         "census_rows": len(census), "census_file": census_file}
    b["hand_non_sec"] = b["hand_census"] + b["hand_pageviews"]
    b["rest"] = b["total"] - b["hand"]
    print(f"verification_log.csv: {b['total']} rows; hand-checked per notes: {b['hand']} "
          f"(SEC {b['hand_sec']} rows across {b['hand_sec_questions']} questions; non-SEC "
          f"{b['hand_non_sec']}: Census {b['hand_census']}, pageviews {b['hand_pageviews']}); "
          f"rest {b['rest']}. Census rows: {b['census_rows']}, all compared against {census_file}")
    return b


def section_checks(summary, questions, vlog, replays, tags):
    n_rows = len(vlog)
    n_yes = sum(r["matches"].strip().lower() == "yes" for r in vlog)
    vb = verification_breakdown(vlog, tags)
    verified_q = len({r["question_id"] for r in vlog if r["matches"].strip().lower() == "yes"})
    per_cat = {}
    for q in questions.values():
        per_cat[q["category"]] = per_cat.get(q["category"], 0) + 1
    qpc = min(per_cat.values()) if len(set(per_cat.values())) == 1 else \
        f"{min(per_cat.values())}–{max(per_cat.values())}"
    ciks = {m.group(1) for r in vlog for m in [re.search(r"edgar/data/(\d+)/", r["source_url"])] if m}
    if not ENGINE_REPLAY.exists():
        die(f"missing {ENGINE_REPLAY.relative_to(ROOT)}; run followup/engine_fix/replay.py")
    rp = json.loads(ENGINE_REPLAY.read_text())
    fmt = {"questions_per_category": qpc, "companies": len(ciks),
           "results_commit": need(rp, "results_commit"), "replay_calls": need(rp, "hand", "calls"),
           "replay_identical": need(rp, "hand", "identical")}
    lims = "".join(f"<li>{e(l.format(**fmt))}</li>" for l in need(replays, "limitations"))
    notes = []
    for n in need(summary, "scorer_notes"):
        by = ", ".join(f"{k} {v}" for k, v in need(n, "flipped_by_setup").items())
        before, after = need(n, "correct_before"), need(n, "correct_after")
        rows = "".join(f"<tr><td>{e(k)}</td><td>{before[k]}</td><td>{after[k]}</td></tr>" for k in before)
        notes.append(f"""
<h3>Scorer bug, found and fixed before publishing</h3>
<p>{e(need(n, "description"))}</p>
<p>The fix (commit <code>{e(need(n, "fix_commit"))}</code>) changed {need(n, "runs_flipped")} runs
({e(by)}), all on {e(", ".join(need(n, "flipped_questions")))}, all from incorrect to correct.</p>
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
<li><code>eval/verification_log.csv</code> has {n_rows} rows covering the {verified_q} questions;
{n_yes} are marked as matching. The author read {vb["hand"]} of them by hand: {vb["hand_sec"]} SEC
rows across {vb["hand_sec_questions"]} questions from the filing HTML, {vb["hand_pageviews"]} pageview
totals in Pageviews Analysis and {vb["hand_census"]} Census months in the live table. The remaining
{vb["rest"]} rows were compared by script or with AI assistance (SPEC §15, “Verification
provenance”).</li>
<li>The {vb["census_rows"]} Census rows were compared against <code>{e(vb["census_file"])}</code>, the
same downloaded workbook that was ingested, so that comparison is not independent; {vb["hand_census"]}
Census months were checked by hand in the live table.</li>
<li>The questions were frozen (git tag <code>questions-frozen</code>) before any evaluation run.</li>
<li>Total model cost of the run: ${need(summary, "total_cost_usd"):.2f}.</li>
</ul>
{''.join(notes)}
<h3>Limits of this experiment</h3>
<ul>{lims}</ul>
<p><a href="{e(repo)}">Repository</a> · {ea}</p>"""


def main():
    summary, questions, tags, vlog, runs, replays, template, ow = load()
    check_template(template)
    model = ", ".join(need(summary, "model"))
    parts = {
        "INTRO": section_intro(questions, tags, replays),
        "SECTION_PROBLEM": section_problem(questions, runs, vlog, replays),
        "SECTION_RESULTS": section_results(summary, questions, ow),
        "FOLLOWUP_TOPLINE": followup_section.top_line(),
        "SECTION_FOLLOWUP": followup_section.section(followup_section.load(),
                                                     need(replays, "links", "repo")),
        "SECTION_REPLAYS": section_replays(runs, questions, vlog, replays, tags),
        "SECTION_TAGS": section_tags(tags, replays),
        "SECTION_B_VS_C": section_b_vs_c(summary, questions, runs),
        "SECTION_CHECKS": section_checks(summary, questions, vlog, replays, tags),
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
