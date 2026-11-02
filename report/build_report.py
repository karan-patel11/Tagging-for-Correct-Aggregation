"""Phase 15a: build the static results page docs/index.html (SPEC §13.1).

The page is one argument in ten sections (SECTIONS below). Every number, model ID, date, count and
source link on it is read at build time from these inputs, and nothing else:

  eval/results/summary.json, eval/results/{A,B,C,D}.jsonl, eval/questions.yaml, tags/tags.yaml,
  src/tool_specs.py, eval/verification_log.csv, eval/verification_ai.csv, docs/error_analysis.md,
  report/replays.yaml, and git metadata (commit dates, the questions-frozen tag, pytest collection).

eval/results/A_raw.jsonl is optional (exploratory setup A_raw, SPEC §15, added after seeing the main
results). If it exists, summary.json must carry its "exploratory" block (written by eval/score.py),
the exploratory section follows Results, the q017 replay gets an A_raw tab, and the headline and Next
steps add one sentence each, by the same sign-test rule as B vs C. The removed columns are read from
the diff of eval/contexts/schema_only.txt and eval/contexts/schema_raw.txt. If A_raw.jsonl is absent,
Next steps says it was not run.

eval/make_questions.py is also read, only to confirm that the answer key does not import
semantics.py. Runs are scored with eval/score.py's score_run, the same code that produced
summary.json, so a badge always matches the summary.

The build fails, naming what is missing, when a file, key, replay question or run is missing; when a
replay's recorded outcome differs from what replays.yaml says; when setup A answered the default
replay correctly in every run; when the template or replays.yaml prose contains a digit; when the
page contains a banned word; when a section has no reader question, evidence or bridge (the story
audit); or when the page is over 2 MB.

Run:  python report/build_report.py            build docs/index.html and report/links_to_check.txt
      python report/build_report.py --check    build to a temp dir, validate, print the audit only
"""

import argparse
import csv
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "src"))

import score  # noqa: E402  (scoring rules only; reads no files on import)
import tool_specs  # noqa: E402  (tool names and descriptions; no I/O)

MAX_BYTES = 2_000_000
EXCERPT_CHARS = 360
BANNED = ["solves", "eliminates", "production", "state-of-the-art", "significantly",
          "Jefferies", "Databricks", "your team"]
CATEGORY_NAMES = {"time_additivity": "Balances over time", "ratios": "Ratios",
                  "ytd_calendar": "Year-to-date and fiscal calendars", "indices": "Price indices",
                  "hierarchy": "Brand hierarchy", "comparability_unanswerable": "Comparability and refusals"}
SETUP_NAMES = {"A": "Schema only", "B": "Prose", "C": "Structured tags", "D": "Enforcing tools",
               "A_raw": "Raw tables (exploratory)"}
X = "A_raw"  # the exploratory setup
SETUP_TOOLS = {"A": [tool_specs.RUN_SQL_SPEC], "B": [tool_specs.RUN_SQL_SPEC],
               "C": [tool_specs.RUN_SQL_SPEC], "D": tool_specs.TOOL_SPECS}
NUMBER_WORDS = {n: w for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
BADGES = {  # outcome code -> (label, colour class)
    "correct": ("Correct", "ok"), "correct_refusal": ("Correct refusal", "ok"),
    "trap": ("Trap", "bad"), "missing_warning": ("Missing warning", "warn"),
    "wrong_other": ("Wrong (other)", "bad"), "unparsed": ("Unparseable", "bad")}


class BuildError(Exception):
    pass


def die(msg):
    raise BuildError(msg)


@dataclass(frozen=True)
class Paths:
    results: Path = ROOT / "eval" / "results"
    questions: Path = ROOT / "eval" / "questions.yaml"
    tags: Path = ROOT / "tags" / "tags.yaml"
    tool_specs: Path = ROOT / "src" / "tool_specs.py"
    vlog: Path = ROOT / "eval" / "verification_log.csv"
    vlog_ai: Path = ROOT / "eval" / "verification_ai.csv"
    error_analysis: Path = ROOT / "docs" / "error_analysis.md"
    replays: Path = ROOT / "report" / "replays.yaml"
    template: Path = ROOT / "report" / "template.html"
    make_questions: Path = ROOT / "eval" / "make_questions.py"
    failure_types: Path = ROOT / "report" / "failure_types.yaml"
    autotag_runs: Path = ROOT / "followup" / "autotag" / "results" / "D_autotag.jsonl"
    autotag_scores: Path = ROOT / "followup" / "autotag" / "results" / "score_tags.json"
    contexts: Path = ROOT / "eval" / "contexts"
    out: Path = ROOT / "docs" / "index.html"
    links: Path = ROOT / "report" / "links_to_check.txt"
    values: Path = ROOT / "report" / "page_values_to_check.csv"


def rel(p):
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def read(path):
    if not Path(path).exists():
        die(f"missing file {rel(path)}")
    return Path(path).read_text()


def e(x):
    return html.escape(str(x), quote=True)


def need(d, *path):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            die(f"missing key {'.'.join(map(str, path))}")
        cur = cur[k]
    return cur


def num(v):
    if v is None:
        return "null"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return f"{int(v):,}"


def pct(x, digits=1):
    return f"{x * 100:.{digits}f}%"


def word(n):
    return NUMBER_WORDS.get(n) or die(f"no number word for {n}")


def inline_md(text):
    """Escape, then render `code` spans and **bold** from error_analysis.md text."""
    t = e(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)


# ---------- evidence tracking (the story audit) ----------

class Evidence:
    """Holds the loaded inputs. Reading one through `ev` records its file for the current section."""

    def __init__(self, data, files):
        self._data, self._files = data, files
        self.section = None
        self.used = {}

    def __call__(self, name):
        if name not in self._data:
            die(f"internal: unknown input {name}")
        self.used.setdefault(self.section, set()).add(self._files[name])
        return self._data[name]


# ---------- git ----------

def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        die(f"git {' '.join(args)} failed: {r.stderr.strip() or 'no output'}"
            + (" (run git fetch --tags)" if "questions-frozen" in args else ""))
    return r.stdout.strip()


def commit_date(rev):
    """UTC date of a commit."""
    return git("log", "-1", "--format=%cd", "--date=format-local:%Y-%m-%d", rev)


def first_commit_date(path):
    return git("log", "--reverse", "--format=%cd", "--date=format-local:%Y-%m-%d", "--", path).splitlines()[0]


@lru_cache(maxsize=1)
def pytest_passed():
    """Run the test suite and return the number of tests passed; the build fails if any test fails or
    errors. Returns None when this build is itself running inside pytest (the tests build the page),
    so the suite never runs itself recursively."""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("BUILD_REPORT_IN_PYTEST"):
        return None
    env = {**os.environ, "BUILD_REPORT_IN_PYTEST": "1"}
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True, timeout=900, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        die(f"pytest could not run during the build: {exc}")
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    passed = re.search(r"(\d+) passed", tail)
    if r.returncode != 0 or not passed or re.search(r"\b(failed|error|errors)\b", tail):
        die(f"pytest failed during the build: {tail or r.stderr.strip()[-300:]}")
    return int(passed.group(1))


# ---------- load and validate ----------

SUMMARY_TOP = ["model", "run_dates", "total_cost_usd", "n_runs", "runs_per_question", "setups",
               "b_vs_c", "scorer_notes"]
SETUP_KEYS = ["n", "correct_runs", "accuracy", "accuracy_by_category", "behavior_accuracy",
              "over_warning_rate", "over_warning_runs", "answer_question_runs", "scaled_runs",
              "trap_hits", "unparsed", "avg_tool_calls", "avg_tokens", "cost_usd", "per_question"]
RANGE_KEYS = ["mean", "min", "max"]
TOKEN_KEYS = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"]
BVC_KEYS = ["questions", "b_right_c_wrong", "c_right_b_wrong", "both_right", "both_wrong", "note"]
EXPL_KEYS = ["note", "setups", "a_vs_a_raw"]
EXPL_SETUP_KEYS = SETUP_KEYS + ["model", "run_dates", "runs_per_question"]
AVX_KEYS = ["questions", "a_right_a_raw_wrong", "a_raw_right_a_wrong", "both_right", "both_wrong",
            "discordant", "sign_test_p", "test", "rule", "note"]
NOTE_KEYS = ["id", "found", "fix_commit", "description", "runs_flipped", "flipped_by_setup",
             "flipped_questions", "flip_direction", "correct_before", "correct_after"]


def has(d, path, keys):
    if not isinstance(d, dict):
        die(f"summary.json: {path} is not an object")
    for k in keys:
        if k not in d or d[k] is None:
            die(f"summary.json: missing key {path + '.' if path else ''}{k}")


def validate_summary(s, questions):
    has(s, "", SUMMARY_TOP)
    if not isinstance(s["run_dates"], list) or not s["run_dates"]:
        die("summary.json: run_dates not recorded")
    if not isinstance(s["model"], list) or not s["model"]:
        die("summary.json: model not recorded")
    setups = s["setups"]
    has(setups, "setups", score.SETUPS)
    covered = set()
    for st in score.SETUPS:
        has(setups[st], f"setups.{st}", ["per_question"])
        covered |= set(setups[st]["per_question"])
    if not covered or covered - set(questions):
        die(f"summary.json: per_question has unknown questions {sorted(covered - set(questions))}")
    cats = {questions[q]["category"] for q in covered}
    traps = {t for q in covered if questions[q]["expected_behavior"] != "refuse"
             for t in (questions[q].get("trap_answers") or {})}
    for st in score.SETUPS:
        p, v = f"setups.{st}", setups[st]
        has(v, p, SETUP_KEYS)
        has(v["accuracy"], f"{p}.accuracy", RANGE_KEYS)
        has(v["accuracy_by_category"], f"{p}.accuracy_by_category", sorted(cats))
        for c in cats:
            has(v["accuracy_by_category"][c], f"{p}.accuracy_by_category.{c}", RANGE_KEYS)
        has(v["trap_hits"], f"{p}.trap_hits", sorted(traps))
        for t in traps:
            has(v["trap_hits"][t], f"{p}.trap_hits.{t}", ["hits", "runs", "rate"])
        has(v["avg_tokens"], f"{p}.avg_tokens", TOKEN_KEYS)
        has(v["per_question"], f"{p}.per_question", sorted(covered))
        for q in covered:
            has(v["per_question"][q], f"{p}.per_question.{q}", ["tool_calls", "tokens"])
    has(s["b_vs_c"], "b_vs_c", BVC_KEYS)
    for i, n in enumerate(s["scorer_notes"]):
        has(n, f"scorer_notes.{i}", NOTE_KEYS)
    if sum(setups[st]["n"] for st in score.SETUPS) != s["n_runs"]:
        die("summary.json: n_runs does not equal the sum of the setups' n")
    if "exploratory" in s:
        validate_exploratory(s["exploratory"], cats, traps, covered)
    return covered


def validate_exploratory(x, cats, traps, covered):
    has(x, "exploratory", EXPL_KEYS)
    has(x["setups"], "exploratory.setups", [X])
    v, p = x["setups"][X], f"exploratory.setups.{X}"
    has(v, p, EXPL_SETUP_KEYS)
    has(v["accuracy"], f"{p}.accuracy", RANGE_KEYS)
    has(v["accuracy_by_category"], f"{p}.accuracy_by_category", sorted(cats))
    for c in cats:
        has(v["accuracy_by_category"][c], f"{p}.accuracy_by_category.{c}", RANGE_KEYS)
    has(v["trap_hits"], f"{p}.trap_hits", sorted(traps))
    for t in traps:
        has(v["trap_hits"][t], f"{p}.trap_hits.{t}", ["hits", "runs", "rate"])
    has(v["avg_tokens"], f"{p}.avg_tokens", TOKEN_KEYS)
    has(v["per_question"], f"{p}.per_question", sorted(covered))
    for q in covered:
        has(v["per_question"][q], f"{p}.per_question.{q}", ["tool_calls", "tokens"])
    has(x["a_vs_a_raw"], "exploratory.a_vs_a_raw", AVX_KEYS)


def schema_columns(text):
    """table -> [column] from a DESCRIBE context file (TABLE name, then indented 'column TYPE' lines)."""
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("TABLE "):
            cur = out.setdefault(line.split()[1], [])
        elif line.strip() and cur is not None:
            cur.append(line.split()[0])
    return out


def removed_columns(full, raw):
    """table -> [column in the full schema but not the raw one], in schema order; dies on any other change."""
    a, b = schema_columns(full), schema_columns(raw)
    if set(a) != set(b):
        die(f"schema_raw.txt and schema_only.txt list different tables: {sorted(set(a) ^ set(b))}")
    out = {}
    for t in a:
        if [c for c in a[t] if c in b[t]] != b[t]:
            die(f"schema_raw.txt adds or reorders columns in {t}")
        gone = [c for c in a[t] if c not in b[t]]
        if gone:
            out[t] = gone
    return out or die("schema_raw.txt removes no columns")


def load(paths):
    summary = json.loads(read(paths.results / "summary.json"))
    questions = {q["id"]: q for q in yaml.safe_load(read(paths.questions))}
    covered = validate_summary(summary, questions)
    tags = {t["id"]: t for t in yaml.safe_load(read(paths.tags))}
    read(paths.tool_specs)  # imported above; must exist as a file
    vlog = list(csv.DictReader(io.StringIO(read(paths.vlog))))
    for col in ["question_id", "source_url", "where_in_source", "matches", "notes"]:
        if vlog and col not in vlog[0]:
            die(f"verification_log.csv has no column {col}")
    vlog_ai = list(csv.DictReader(io.StringIO(read(paths.vlog_ai))))
    for col in ["input_key", "status", "matches", "revision"]:
        if vlog_ai and col not in vlog_ai[0]:
            die(f"verification_ai.csv has no column {col}")
    runs = {}
    for st in score.SETUPS:
        for line in read(paths.results / f"{st}.jsonl").splitlines():
            if line.strip():
                r = json.loads(line)
                runs[(r["question_id"], r["setup"], r["run"])] = r
    a_raw_path = paths.results / "A_raw.jsonl"
    a_raw = None
    if a_raw_path.exists():
        a_raw = {}
        for line in read(a_raw_path).splitlines():
            if line.strip():
                r = json.loads(line)
                a_raw[(r["question_id"], r["run"])] = r
    raw_schema = None
    if a_raw is None and "exploratory" in summary:
        die("summary.json has an exploratory block but eval/results/A_raw.jsonl is missing")
    if a_raw is not None:
        if "exploratory" not in summary:
            die("summary.json: missing key exploratory (eval/results/A_raw.jsonl exists; run python eval/score.py)")
        check_exploratory(summary, questions, runs, a_raw)
        raw_schema = removed_columns(read(paths.contexts / "schema_only.txt"), read(paths.contexts / "schema_raw.txt"))
    autotag = {}
    for line in read(paths.autotag_runs).splitlines():
        if line.strip():
            r = json.loads(line)
            autotag[(r["question_id"], r["run"])] = r
    autotag_scores = json.loads(read(paths.autotag_scores))
    replays = yaml.safe_load(read(paths.replays))
    ea = read(paths.error_analysis)
    template = read(paths.template)
    failure_types = check_failure_types(yaml.safe_load(read(paths.failure_types)), questions, runs)
    data = {"summary": summary, "questions": questions, "tags": tags, "vlog": vlog, "vlog_ai": vlog_ai,
            "runs": runs, "a_raw": a_raw, "raw_schema": raw_schema, "failure_types": failure_types,
            "autotag": {"runs": autotag, "scores": autotag_scores},
            "replays": replays, "error_analysis": ea, "tool_specs": tool_specs,
            "make_questions": read(paths.make_questions), "git": git}
    files = {"summary": rel(paths.results / "summary.json"), "questions": rel(paths.questions),
             "tags": rel(paths.tags), "vlog": rel(paths.vlog), "vlog_ai": rel(paths.vlog_ai),
             "runs": rel(paths.results / "{A,B,C,D}.jsonl"), "a_raw": rel(a_raw_path) + ("" if a_raw is not None else " (absent)"),
             "raw_schema": rel(paths.contexts / "schema_only.txt") + " vs " + rel(paths.contexts / "schema_raw.txt"),
             "replays": rel(paths.replays), "error_analysis": rel(paths.error_analysis),
             "failure_types": rel(paths.failure_types),
             "autotag": rel(paths.autotag_runs) + ", " + rel(paths.autotag_scores),
             "tool_specs": rel(paths.tool_specs), "make_questions": rel(paths.make_questions),
             "git": "git metadata"}
    return Evidence(data, files), template, covered


def check_exploratory(summary, questions, runs, a_raw):
    """The exploratory block in summary.json must match the A_raw transcripts scored now."""
    x = summary["exploratory"]
    v = x["setups"][X]
    sc = [score.score_run(r, questions.get(k[0]) or die(f"A_raw run for unknown question {k[0]}"))
          for k, r in a_raw.items()]
    if (sum(r["correct"] for r in sc), len(sc)) != (v["correct_runs"], v["n"]):
        die("summary.json exploratory.setups.A_raw does not match eval/results/A_raw.jsonl; run python eval/score.py")
    a = majority_by_question({(k[0], k[2]): rec for k, rec in runs.items() if k[1] == "A"}, questions)
    r = majority_by_question(a_raw, questions)
    a_only, raw_only, both, neither = paired(a, r)
    pc = x["a_vs_a_raw"]
    if (a_only, raw_only, both, neither) != (pc["a_right_a_raw_wrong"], pc["a_raw_right_a_wrong"],
                                             pc["both_right"], pc["both_wrong"]):
        die("summary.json exploratory.a_vs_a_raw does not match the transcripts; run python eval/score.py")
    if abs(mcnemar_p(len(a_only), len(raw_only)) - pc["sign_test_p"]) > 1e-12:
        die("summary.json exploratory.a_vs_a_raw.sign_test_p does not match the exact sign test")


FAILURE_TYPES = ("missed_warning", "period_misread", "execution_slip", "tool_interface")


def check_failure_types(doc, questions, runs):
    """report/failure_types.yaml must list exactly the runs score.py scores incorrect, each with one of
    FAILURE_TYPES. Returns (setup, question_id, run) -> entry."""
    entries = (doc or {}).get("failures") or die("report/failure_types.yaml has no 'failures' list")
    typed = {}
    for x in entries:
        k = (x.get("setup"), x.get("question_id"), x.get("run"))
        if k in typed:
            die(f"report/failure_types.yaml lists {k} twice")
        if x.get("type") not in FAILURE_TYPES:
            die(f"report/failure_types.yaml {k}: type {x.get('type')!r} is not one of {', '.join(FAILURE_TYPES)}")
        if not str(x.get("note") or "").strip():
            die(f"report/failure_types.yaml {k}: no note")
        typed[k] = x
    wrong = {(k[1], k[0], k[2]) for k, rec in runs.items() if not score.score_run(rec, questions[k[0]])["correct"]}
    if set(typed) != wrong:
        die("report/failure_types.yaml keys do not match the wrong runs in the results: "
            f"missing {sorted(wrong - set(typed))}, not wrong {sorted(set(typed) - wrong)}")
    return typed


# ---------- scoring ----------

def scored(ev, qid, setup, run):
    rec = ev("runs").get((qid, setup, run)) or die(f"no recorded run {qid} setup {setup} run {run}")
    return rec, score.score_run(rec, ev("questions")[qid])


def outcome(sc):
    if not sc["parsed"]:
        return "unparsed"
    if sc["trap_hit"]:
        return "trap"
    f = sc["final"]
    if sc["correct"]:
        return "correct_refusal" if sc["expected"] == "refuse" else "correct"
    if sc["expected"] == "answer_with_warning" and sc["number_ok"] and not f["warning"] and not f["refused"]:
        return "missing_warning"
    return "wrong_other"


def is_ok(o):
    return o in ("correct", "correct_refusal")


def badge(sc):
    o = outcome(sc)
    label, cls = BADGES[o]
    if o == "trap":
        label = f"Trap: {sc['trap_hit'].replace('_', ' ')}"
    return f'<span class="badge {cls}">{e(label)}</span>'


def scored_any(ev, qid, setup, run):
    """Like scored(), also for the exploratory setup (its records live in ev("a_raw"))."""
    if setup != X:
        return scored(ev, qid, setup, run)
    raw = ev("a_raw") or die("replays.yaml names an A_raw run but eval/results/A_raw.jsonl is absent")
    rec = raw.get((qid, run)) or die(f"no recorded run {qid} setup A_raw run {run}")
    return rec, score.score_run(rec, ev("questions")[qid])


def record_any(ev, qid, setup):
    if setup != X:
        return record(ev, qid, setup)
    raw = ev("a_raw")
    outs = [(k[1], outcome(score.score_run(raw[k], ev("questions")[qid]))) for k in sorted(raw) if k[0] == qid]
    outs or die(f"no A_raw runs for {qid}")
    return sum(is_ok(o) for _, o in outs), len(outs), outs


def run_keys(ev, qid, setup):
    keys = sorted(k for k in ev("runs") if k[0] == qid and k[1] == setup)
    return keys or die(f"no runs for {qid} setup {setup}")


def record(ev, qid, setup):
    outs = [(k[2], outcome(score.score_run(ev("runs")[k], ev("questions")[qid]))) for k in run_keys(ev, qid, setup)]
    return sum(is_ok(o) for _, o in outs), len(outs), outs


def tab_setups(item, ev):
    """Setups with a tab in a replay: A-D always; A_raw when replays.yaml names a run for it and A_raw.jsonl exists."""
    return score.SETUPS + ([X] if X in (item.get("runs") or {}) and ev("a_raw") is not None else [])


# ---------- sources ----------

SEC_RE = re.compile(r"https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})(?:/.*)?$")


def sec_link(url):
    """SPEC §9.2: https://www.sec.gov/Archives/edgar/data/{CIK without leading zeros}/{accession without dashes}/"""
    m = SEC_RE.fullmatch(url)
    return f"https://www.sec.gov/Archives/edgar/data/{int(m[1])}/{m[2]}/" if m else None


def tsv_rows(text):
    """Rows of a tab-separated tool output with a header line, as dicts."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or "\t" not in lines[0]:
        return []
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.count("\t") == len(head) - 1]


def as_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def sources(ev, qid):
    """(label, url or None) per distinct answer-key source in verification_log.csv."""
    seen, out = set(), []
    for r in ev("vlog"):
        if r["question_id"] != qid:
            continue
        u = r["source_url"].strip()
        link = sec_link(u) or (u if u.startswith("https://") else None)
        key = link or u
        if key in seen:
            continue
        seen.add(key)
        if link and "sec.gov" in link:
            acc = SEC_RE.fullmatch(u)[2]
            form = re.search(r"\b(10-K|10-Q|8-K)\b", r["where_in_source"])
            label = f"{form[1] + ' · ' if form else 'SEC filing · '}{acc[:10]}-{acc[10:12]}-{acc[12:]}"
        elif link and "pageviews" in link:
            label = "Wikimedia Pageviews Analysis"
        elif link and "bls.gov" in link:
            label = "BLS series page"
        elif link and "census.gov" in link:
            label = "Census retail trade"
        elif link:
            label = re.sub(r"^https://", "", link).split("/")[0]
        else:
            label = u
        out.append((label, link))
    return out or die(f"no verification_log rows for {qid}")


def source_html(ev, qid, limit=3):
    items = [f'<a href="{e(u)}">{e(l)}</a>' if u else f"<span>{e(l)}</span>" for l, u in sources(ev, qid)]
    if len(items) <= limit:
        return " · ".join(items)
    return (f'{" · ".join(items[:limit])} <details class="more"><summary>all {len(items)} sources</summary>'
            + "<br>".join(items[limit:]) + "</details>")


# ---------- charts ----------

def hidden_table(caption, heads, rows):
    body = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<table class="sr-only"><caption>{e(caption)}</caption><tr>'
            + "".join(f"<th scope='col'>{e(h)}</th>" for h in heads) + f"</tr>{body}</table>")


def svg_bars(rows, label, ranges):
    """rows: (setup label, value, lo, hi). Zero-based 0–100% axis; whiskers mark lo–hi when ranges."""
    w, left, right, bar_h, gap, top = 560, 150, 70, 18, 12, 6
    plot = w - left - right
    h = top + len(rows) * (bar_h + gap) + 22
    x = lambda v: left + v * plot  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}" class="chart">']
    for t in (0, 0.5, 1):
        out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{h - 18}" class="grid"/>'
                   f'<text x="{x(t):.1f}" y="{h - 4}" class="tick" text-anchor="middle">{e(pct(t, 0))}</text>')
    for i, (name, v, lo, hi) in enumerate(rows):
        y = top + i * (bar_h + gap)
        out.append(f'<text x="{left - 8}" y="{y + bar_h - 4}" class="lab" text-anchor="end">{e(name)}</text>'
                   f'<rect x="{left}" y="{y}" width="{max(v * plot, 1):.1f}" height="{bar_h}" class="bar" rx="2"/>')
        if ranges:
            cy = y + bar_h / 2
            out.append(f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{cy}" y2="{cy}" class="whisker"/>'
                       f'<line x1="{x(lo):.1f}" x2="{x(lo):.1f}" y1="{y + 3}" y2="{y + bar_h - 3}" class="whisker"/>'
                       f'<line x1="{x(hi):.1f}" x2="{x(hi):.1f}" y1="{y + 3}" y2="{y + bar_h - 3}" class="whisker"/>')
        out.append(f'<text x="{x(1) + 8:.1f}" y="{y + bar_h - 4}" class="val">{e(pct(v))}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- claims ----------

def mcnemar_p(b, c):
    """Exact two-sided sign test on discordant pairs: 2 × P(X ≤ min(b, c)), X ~ Bin(b + c, ½), capped at 1."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def b_vs_c_verdict(b_right_c_wrong, c_right_b_wrong):
    """(verdict sentence, p). Rule §3: p < 0.05 names the better format; otherwise no detectable difference."""
    b, c = b_right_c_wrong, c_right_b_wrong
    p = mcnemar_p(b, c)
    if p < 0.05:
        if c > b:
            return (f"C (structured tags) outperformed B (prose with the same facts) on {c} of {b + c} "
                    "questions where they disagreed."), p
        return (f"B (prose with the same facts) outperformed C (structured tags) on {b} of {b + c} "
                "questions where they disagreed."), p
    return (f"No detectable difference between structured tags and prose with the same facts "
            f"({b} vs {c} discordant questions; too few to separate from noise)."), p


MIN_DISCORDANT = 6  # an exact two-sided sign test cannot reach p < 0.05 with fewer discordant questions
TOO_FEW = "too few discordant questions to separate from noise"


def sign_test_text(n_discordant, p):
    """'p = x.xx', or the too-few phrase when the discordant count is below MIN_DISCORDANT."""
    return TOO_FEW if n_discordant < MIN_DISCORDANT else f"p = {p:.2f}"


def overlaps(r1, r2):
    return r1[0] <= r2[1] and r2[0] <= r1[1]


def _ends(vals):
    """(lowest value, setups at it, highest value, setups at it), ties named together."""
    lo, hi = min(vals.values()), max(vals.values())
    at = lambda v: ", ".join(s for s in sorted(vals) if vals[s] == v)  # noqa: E731
    return lo, at(lo), hi, at(hi)


def accuracy_claim(acc):
    """acc: setup -> (mean, lo, hi). Rule §3: a difference is real only if the run ranges don't overlap."""
    order = sorted(acc, key=lambda s: (acc[s][0], s))
    apart = [(a, b) for i, a in enumerate(order) for b in order[i + 1:]
             if not overlaps(acc[a][1:], acc[b][1:]) and acc[b][0] > acc[a][0]]
    if not apart:
        lo, lo_s, hi, hi_s = _ends({s: v[0] for s, v in acc.items()})
        return f"Accuracy ran from {pct(lo)} ({lo_s}) to {pct(hi)} ({hi_s}), with overlapping run-to-run ranges."
    parts = [f"{b} above {a} ({pct(acc[b][0])} vs {pct(acc[a][0])})" for a, b in apart]
    return "Run ranges do not overlap for " + "; ".join(parts) + "; every other pair has overlapping run-to-run ranges."


def trap_claim(trap_totals):
    """trap_totals: setup -> {trap: (hits, runs)}."""
    hits = {(s, t): h for s, d in trap_totals.items() for t, (h, _) in d.items() if h}
    checks = sum(r for d in trap_totals.values() for _, r in d.values())
    total = sum(hits.values())
    if not total:
        return f"No setup hit a stored trap in {checks:,} trap checks."
    where = "; ".join(f"setup {s}, {t.replace('_', ' ')}: {h}" for (s, t), h in sorted(hits.items()))
    return f"Stored traps were hit in {total} of {checks:,} trap checks across all setups ({where})."


def d_claim(d_answerable, d_refuse):
    """d_answerable / d_refuse: (correct runs, runs). Rule §3 for a perfect D on answerable questions."""
    ok, n = d_answerable
    if n and ok == n:
        rok, rn = d_refuse
        return ("D's tools were built for these categories; its real test is the unanswerable and "
                f"out-of-coverage questions, where D's behavior was correct in {rok} of {rn} runs.")
    return None


def behavior_claim(beh):
    lo, lo_s, hi, hi_s = _ends(beh)
    return (f"Behavior accuracy (a warning when one is needed, a refusal when the data doesn't exist) "
            f"ran from {pct(lo)} ({lo_s}) to {pct(hi)} ({hi_s}).")


FEW_ERRORS = 0.05  # a setup "made few errors" when at most this share of its runs were wrong


def headline_claim(model, wrong, bvc_p, a_raw=None):
    """wrong: setup -> (wrong runs, runs). The plain result, by rule: few errors only if every setup is at
    or under FEW_ERRORS; B vs C named only if the sign test gives p < 0.05. a_raw: (A right A_raw wrong,
    A_raw right A wrong) when the exploratory run exists; same sign-test rule."""
    rates = {s: w / n for s, (w, n) in wrong.items()}
    lo, hi = min(w for w, _ in wrong.values()), max(w for w, _ in wrong.values())
    sizes = {n for _, n in wrong.values()}
    per = f" out of {sizes.pop()} per setup" if len(sizes) == 1 else ""
    if max(rates.values()) <= FEW_ERRORS:
        first = f"With these tables and this model ({model}), every setup made few errors: {lo} to {hi} wrong runs{per}."
    else:
        first = f"With these tables and this model ({model}), wrong runs per setup ranged from {lo} to {hi}{per}."
    second = ("B vs. C (prose vs. structured tags with the same facts) showed no detectable difference."
              if bvc_p >= 0.05 else
              f"B vs. C (prose vs. structured tags with the same facts) differed (exact sign test, p = {bvc_p:.2f}).")
    out = [first, second]
    if rates["A"] <= FEW_ERRORS:
        out.append(f"Setup A, with no tags at all, was already {pct(1 - rates['A'])} correct, so tagging had few "
                   "errors to remove here.")
    if a_raw is not None:
        out.append(a_raw_headline(*a_raw))
    return out


def a_raw_verdict(a_only, raw_only):
    """(verdict sentence, p) for A vs A_raw by question. Same rule as B vs C: a direction only if p < 0.05."""
    p = mcnemar_p(a_only, raw_only)
    n = a_only + raw_only
    if p < 0.05:
        if raw_only > a_only:
            return (f"A_raw (raw tables) was right where A was wrong on {raw_only} of {n} questions where they "
                    f"disagreed (exact sign test, p = {p:.2f})."), p
        return (f"A (schema with meaning columns) was right where A_raw was wrong on {a_only} of {n} questions "
                f"where they disagreed (exact sign test, p = {p:.2f})."), p
    test = TOO_FEW if n < MIN_DISCORDANT else f"exact sign test, p = {p:.2f}"
    return f"No detectable difference between A and A_raw ({a_only} vs {raw_only} discordant questions; {test}).", p


def a_raw_headline(a_only, raw_only):
    _, p = a_raw_verdict(a_only, raw_only)
    lead = "In an exploratory run added after seeing the main results, setup A on raw tables without the meaning columns"
    if p >= 0.05:
        return f"{lead} showed no detectable difference from setup A (exact sign test, p = {p:.2f})."
    better = "A_raw" if raw_only > a_only else "A"
    return f"{lead} differed from setup A ({better} ahead; exact sign test, p = {p:.2f})."


def a_raw_next_step(a_only, raw_only):
    n, p = a_only + raw_only, mcnemar_p(a_only, raw_only)
    test = TOO_FEW if n < MIN_DISCORDANT else f"exact sign test, p = {p:.2f}"
    if p >= 0.05:
        return ("Meaning that lives only in columns: removing the meaning columns made no detectable difference "
                f"to setup A (exploratory; {test}). Every removed column can be recomputed "
                "from columns that stayed, so a harder test needs data whose meaning cannot be recovered from "
                "other columns.")
    return ("Meaning that lives only in columns: removing the meaning columns changed setup A's results "
            f"(exploratory; {test}); test the same on a second dataset before relying on it.")


VKEY = re.compile(r"^\[([^\]]+)\]")
HAND_RE = re.compile(r"hand-read by|hand spot-check by")
REVISED_SERIES = {"cpi": "BLS", "census722": "Census"}


def verification_counts(vlog, vlog_ai):
    """Counts per distinct answer-key input (the [key] at the start of where_in_source).

    Hand checks come from verification_log.csv notes (a key counts if any of its rows records one);
    the AI-assisted read, mismatches and revisions from verification_ai.csv."""
    keys = set()
    hand = set()
    for r in vlog:
        m = VKEY.match(r["where_in_source"]) or die(f"verification_log.csv row for {r['question_id']} has no [input key]")
        keys.add(m[1])
        if HAND_RE.search(r["notes"]):
            hand.add(m[1])
    ai = {}
    for r in vlog_ai:
        if r["input_key"] in ai:
            die(f"verification_ai.csv lists {r['input_key']} twice")
        ai[r["input_key"]] = r
    missing = sorted(keys - set(ai))
    if missing:
        die(f"verification_ai.csv has no row for logged inputs {missing[:5]}")
    unsourced = {k for k in keys if ai[k]["status"] == "n/a"}
    sourced = keys - unsourced
    if hand & unsourced:
        die(f"inputs marked hand-checked have no source in verification_ai.csv: {sorted(hand & unsourced)}")
    labelled = {k for k, r in ai.items() if r["status"] == "hand_checked_reread"}
    hand_rows = sum(1 for r in vlog if HAND_RE.search(r["notes"]))
    if len(labelled) != len(hand):
        die(f"hand checks disagree, counts differ: verification_ai.csv status hand_checked_reread = {len(labelled)}; "
            f"distinct verification_log.csv inputs whose notes record a hand read = {len(hand)} ({hand_rows} rows)")
    if labelled != hand:
        die("hand checks disagree: verification_log.csv notes vs verification_ai.csv status hand_checked_reread "
            f"(log only: {sorted(hand - labelled)[:5]}; ai only: {sorted(labelled - hand)[:5]})")
    verdict = {k: ai[k]["matches"].strip().lower() for k in sourced}
    unread = sorted(k for k, v in verdict.items() if v not in ("yes", "no"))
    if unread:
        die(f"verification_ai.csv: logged inputs not read from a source: {unread[:5]}")
    revised = [r for r in vlog_ai if r["revision"].strip() not in ("", "none")]
    rev_checked = [r for r in vlog_ai if r["revision"].strip() != ""]
    series = sorted({REVISED_SERIES.get(r["input_key"].split(":")[0]) or
                     die(f"revision recorded for unexpected input {r['input_key']}") for r in rev_checked})
    return {"inputs": len(keys), "unsourced": len(unsourced), "sourced": len(sourced), "hand": len(hand),
            "ai_read": len(verdict), "mismatches": sum(v == "no" for v in verdict.values()),
            "trap_only": sum(r["status"] == "trap_only" for r in vlog_ai),
            "revisions": len(revised), "revision_checked": len(rev_checked), "revision_series": series}


def verification_claims(v):
    ai = f"all {v['ai_read']}" if v["ai_read"] == v["sourced"] else f"{v['ai_read']}"
    out = [f"The answer key rests on {v['inputs']} distinct input values; {v['unsourced']} record that the data "
           f"does not exist and have no source to check.",
           f"The other {v['sourced']} were checked against primary sources: {v['hand']} by the author by hand, and "
           f"{ai} by an AI-assisted read of the source; {v['mismatches']} mismatches.",
           f"Revisions found: {v['revisions']}, among the {v['revision_checked']} inputs from series that get revised "
           f"({' and '.join(v['revision_series'])})."]
    if v["trap_only"]:
        out.append(f"A further {v['trap_only']} values used only to compute trap answers were also read from the source.")
    return out


def majority_by_question(recs, questions):
    """recs: (qid, run) -> record. qid -> True when more than half of its runs score correct."""
    by_q = {}
    for (qid, _), rec in recs.items():
        q = questions.get(qid) or die(f"run for unknown question {qid}")
        by_q.setdefault(qid, []).append(score.score_run(rec, q)["correct"])
    return {qid: sum(v) * 2 > len(v) for qid, v in by_q.items()}


def paired(x, y):
    """x, y: qid -> majority correct, same questions. (x right y wrong, y right x wrong, both right, both wrong)."""
    if set(x) != set(y):
        die(f"paired comparison: question sets differ ({sorted(set(x) ^ set(y))[:5]})")
    xs = sorted(q for q in x if x[q] and not y[q])
    ys = sorted(q for q in x if y[q] and not x[q])
    return xs, ys, sum(x[q] and y[q] for q in x), sum(not x[q] and not y[q] for q in x)


# ---------- sections ----------

A_RAW_NOT_RUN = ("Not run: setup A on the raw tables. eval/results/A_raw.jsonl does not exist; if it is added, "
                 "the page compares it with A question by question, with an exact sign test, labelled exploratory "
                 "because it comes after seeing the main results.")
EXPLORATORY = ("exploratory", "Why the baseline was so strong",
               "Was setup A accurate only because the meaning was already in the columns?",
               "Where it still breaks.")
EXPLORATORY_IN = "So why was the baseline so strong?"  # bridge from B vs C when the exploratory run exists

FAILURE_ORDER = ["D", "A", "B", "C"]  # D first: where enforcement itself broke

# Three parts plus a footer. Each section: id, rail name, reader question, bridge into the next section.
PARTS = [
    ("part-problem", "Problem", [
        ("problem", "The question", "What's the problem?",
         "The same kind of unstated rule turns up in {n_traps} places in this data."),
        ("traps", "{n_traps} traps", "How common or broad is this?",
         "So what would a model need to know to avoid these?"),
    ]),
    ("part-approach", "Approach", [
        ("fix", "The fix", "What's the proposed solution?",
         "Does any of this actually change what the model gets right?"),
        ("experiment", "The experiment", "How was it tested fairly?", "Here's what happened."),
    ]),
    ("part-results", "Results", [
        ("results", "Overview", "Did it work, and where?",
         "Numbers hide how. Watch the same question go wrong and right."),
        ("replay", "Replay", "What does failure actually look like?",
         "The headline question was format: prose vs. structured tags."),
        ("b-vs-c", "B vs C", "Should tagging effort go into structure, or is good documentation enough?",
         "Where it still breaks."),
        ("failures", "Where it fails", "Is this honest?", "What the score itself cannot see."),
        ("misses", "What the score misses", "What does a correct score not tell you?",
         "So what does it all add up to?"),
    ]),
    ("part-conclusion", "Conclusion", [
        ("conclusion", "Conclusion", "If I read only one section, what did this experiment find?",
         "How the answers were checked."),
    ]),
    ("part-footer", None, [
        ("checks", "How it was checked", "How were the answers checked?", "What this can and cannot show."),
        ("limits", "Limits", "What can't this show?", "What this would mean on real research data."),
        ("next", "Next steps", "What would this mean on real research data?", "{closing}"),
    ]),
]
SECTIONS = [x for _, _, secs in PARTS for x in secs]


def plural(n, one, many):
    return one if n == 1 else many


def qid_list(ids):
    return ", ".join(dict.fromkeys(ids))


def breakdown_claim(f, trap_phrase):
    """The wrong-run breakdown by failure type, singular or plural to match each count. trap_phrase adds
    ', the one stored-trap hit' after the period_misread IDs (the caller verifies it holds)."""
    n, q = f["n"], f["qids"]
    mis = f"{n['period_misread']} answered for the full year instead of the requested quarter ({q['period_misread']}"
    mis += (", the one stored-trap hit" if trap_phrase else "") + ")"
    return (f"Of the wrong runs, {n['missed_warning']} missed a calendar warning ({q['missed_warning']}), {mis}, "
            f"{n['execution_slip']} {plural(n['execution_slip'], 'made an arithmetic slip', 'made arithmetic slips')} "
            f"after correct retrieval ({q['execution_slip']}), and {n['tool_interface']} "
            f"{plural(n['tool_interface'], 'was a failure', 'were failures')} of the enforcing tools' own interface "
            f"({q['tool_interface']}).")


class Page:
    def __init__(self, ev):
        self.ev = ev
        self.claims = []  # (section, rule, sentence)
        self.notes = []   # build warnings

    def claim(self, rule, text):
        self.claims.append((self.ev.section, rule, text))
        return text

    def facts(self):
        """Counts shared by the hero and the Results lead, each read from summary.json, the transcripts or
        report/failure_types.yaml. Dies if a sentence the page states about them would no longer hold."""
        if getattr(self, "_facts", None):
            return self._facts
        ev = self.ev
        s, questions, ft = ev("summary"), ev("questions"), ev("failure_types")
        st_ = s["setups"]
        total = sum(st_[x]["n"] for x in score.SETUPS)
        wrong = sum(st_[x]["n"] - st_[x]["correct_runs"] for x in score.SETUPS)
        if wrong != len(ft):
            die(f"summary.json counts {wrong} wrong runs but report/failure_types.yaml lists {len(ft)}")
        hits = sum(t["hits"] for x in score.SETUPS for t in st_[x]["trap_hits"].values())
        checks = sum(t["runs"] for x in score.SETUPS for t in st_[x]["trap_hits"].values())
        acc_a = st_["A"]["accuracy"]["mean"]
        if 1 - acc_a > FEW_ERRORS:
            die(f"setup A is {pct(acc_a)} correct; 'already ... correct, so this experiment can't show tags helping' "
                f"needs at most {FEW_ERRORS:.0%} wrong")
        if hits / checks > FEW_ERRORS:
            die("stored traps fired in more than a few checks; 'the traps rarely fired' no longer holds")
        by = {t: [k for k, x in sorted(ft.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])) if x["type"] == t]
              for t in FAILURE_TYPES}
        for k in by["missed_warning"]:
            if "calendar" not in (questions[k[1]].get("notes") or ""):
                die(f"{k}: missed_warning, but the question's notes don't name a calendar warning")
        trap_runs = {(k[1], k[0], k[2]) for k, rec in ev("runs").items()
                     if score.score_run(rec, questions[k[0]])["trap_hit"]}
        for k in by["period_misread"]:
            sc = score.score_run(ev("runs")[(k[1], k[0], k[2])], questions[k[1]])
            if sc["trap_hit"] != "used_fy_value":
                die(f"{k}: period_misread, but its stored trap is {sc['trap_hit']!r}, not the full-year value")
        bc = s["b_vs_c"]
        _, bvc_p = b_vs_c_verdict(len(bc["b_right_c_wrong"]), len(bc["c_right_b_wrong"]))
        if bvc_p < 0.05:
            die("B vs C differs (p < 0.05); the hero sentence 'no detectable difference' no longer holds")
        self._facts = {
            "total": total, "wrong": wrong, "hits": hits, "checks": checks, "acc_a": acc_a,
            "n": {t: len(v) for t, v in by.items()},
            "qids": {t: qid_list(k[1] for k in v) for t, v in by.items()},
            "trap_phrase": trap_runs == set(by["period_misread"]),
        }
        return self._facts

    # S1
    def problem(self):
        ev = self.ev
        r, s = ev("replays"), ev("summary")
        hero = need(r, "hero")
        qid = need(hero, "question_id")
        q = ev("questions").get(qid) or die(f"replays.yaml hero.question_id {qid} not in questions.yaml")
        trap_name, part_name = need(hero, "trap"), need(hero, "minus")
        trap, part = need(q, "trap_answers", trap_name), need(q, "trap_answers", part_name)
        if trap - part != q["correct"]:
            die(f"{qid}: {trap_name} minus {part_name} does not equal the answer key")
        # Every recorded run on the hero question, scored; the trap runs are counted, never typed.
        scored_runs = [(k, score.score_run(rec, q)) for k, rec in sorted(ev("runs").items()) if k[0] == qid]
        if not scored_runs:
            die(f"no recorded runs for hero question {qid}")
        hits = [k for k, sc in scored_runs if sc["trap_hit"] == trap_name]
        if not hits:
            die(f"no recorded run on {qid} hit {trap_name}; pick a hero question with a real failure")
        n, n_ok = len(scored_runs), sum(sc["correct"] for _, sc in scored_runs)
        shown = ev("runs")[hits[0]]
        call, row = next(((c, rw) for c in shown.get("tool_calls") or [] for rw in tsv_rows(str(c["output"]))
                          if as_float(rw.get("value")) == trap), (None, None))
        if call is None:
            die(f"{qid} setup {hits[0][1]} run {hits[0][2]}: no tool output row holds the trap value")
        sql = call["input"].get("sql") if isinstance(call["input"], dict) else None
        sql = sql or die(f"{qid} setup {hits[0][1]} run {hits[0][2]}: the trap row did not come from SQL")
        # Filing links: one per answer-key input, labelled by the period it covers.
        links = []
        for vr in ev("vlog"):
            if vr["question_id"] != qid:
                continue
            key = VKEY.match(vr["where_in_source"]) or die(f"verification_log.csv {qid} row has no input key")
            basis = key[1].split(":")[3] if key[1].startswith("sec:") else None
            label = {"FY": "full fiscal year", "YTD9": "first nine months"}.get(basis) \
                or die(f"hero source {key[1]}: no label for period {basis}")
            form = re.search(r"\b(10-K|10-Q)\b", vr["where_in_source"]) or die(f"hero source {key[1]}: no form")
            link = sec_link(vr["source_url"].strip()) or die(f"hero source {key[1]}: not an SEC archive link")
            links.append((basis, f'<a href="{e(link)}">{e(form[1])} on SEC EDGAR</a> ({e(label)})'))
        by = dict(links)
        if set(by) != {"FY", "YTD9"}:
            die(f"hero {qid}: expected a full-year and a nine-month filing, got {sorted(by)}")
        where = ", ".join(f"setup {k[1]}, run {k[2]}" for k in hits)
        rest = (f"The other {n - len(hits)} were correct." if n_ok == n - len(hits) else
                f"Of the other {n - len(hits)}, {n_ok} were correct.")
        rec = self.claim("hero trap count: recorded runs on the hero question whose score hits the hero trap (score.py over the jsonl)",
                         f"{len(hits)} of {n} recorded runs on this question fell into this trap ({where}). {rest}")
        said = " ".join(shown.get("text") or [])
        if not (re.search(r"full year is the figure you asked about", said) and "cross-check" in said):
            die(f"{qid} setup {hits[0][1]} run {hits[0][2]}: the transcript no longer says the full year was the "
                "figure asked about with the quarter as a cross-check; the hero wording depends on it")
        row_desc = self.claim("hero row: the trap value's row in the recorded tool output; the run's text says the "
                              "full year was the figure asked about and gives the quarter as a cross-check",
                              f"In that run the full-year row came back with period_basis {row.get('period_basis')} "
                              f"and fiscal_quarter {row.get('fiscal_quarter')}. The model said the full year was the "
                              "figure asked about, computed the quarter only as a cross-check, and put the full-year "
                              "value in its final answer.")
        f = self.facts()
        boxes = [
            self.claim("hero box: wrong runs and stored-trap hits summed over setups (summary.json)",
                       f"{f['wrong']} wrong runs out of {f['total']}; the stored traps were hit in {f['hits']} "
                       f"of {f['checks']} checks."),
            self.claim(f"hero box: setup A mean accuracy (summary.json); stated only if A is at most {FEW_ERRORS:.0%} wrong",
                       f"Setup A, with no tags, was already {pct(f['acc_a'])} correct, so this experiment can't show "
                       "tags helping."),
            self.claim("hero box: wrong runs by type from report/failure_types.yaml",
                       breakdown_claim(f, trap_phrase=False)),
            self.claim("hero box: B vs C exact sign test, stated only if p >= 0.05",
                       "Prose vs. structured tags with the same facts: no detectable difference."),
        ]
        return f"""
<h1>Do tags help an AI agent aggregate financial data correctly?</h1>
<p class="lede"><b>The trap: valid SQL, wrong answer.</b> A query can run without error and still produce the wrong number.
Here the table held every row needed. The model read the question as asking for the full year, computed the
quarter only as a cross-check, and reported the full-year figure.</p>
<p class="q">“{e(q["question"])}”</p>
<div class="compare">
  <div class="stat bad-edge"><div class="stat-k">The trap: the full fiscal year</div>
    <div class="big">{e(num(trap))} <span class="unit">{e(q["unit"])}</span></div>
    <div class="small muted">The query a recorded run wrote (setup {e(hits[0][1])}, run {hits[0][2]}):</div>
    <pre class="sql">{e(sql)}</pre>
    <div class="small muted">{e(row_desc)}</div>
    <div class="small">Source: {by["FY"]}</div></div>
  <div class="stat ok-edge"><div class="stat-k">The correct answer: the fourth quarter</div>
    <div class="big">{e(num(q["correct"]))} <span class="unit">{e(q["unit"])}</span></div>
    <div class="small">Full year {e(num(trap))} minus the first nine months {e(num(part))}.</div>
    <div class="small">Sources: {by["FY"]} · {by["YTD9"]}</div></div>
</div>
<p class="trapcount"><b>{e(rec)}</b></p>
<div class="headline"><div class="stat-k">The result</div>
  <div class="result-grid">{"".join(f'<p class="result-box">{e(t)}</p>' for t in boxes)}</div></div>
<p class="small muted">Both numbers come from the answer key; the trap count is scored from the recorded runs.</p>"""

    # S2
    def traps(self):
        ev = self.ev
        r = ev("replays")
        tags = ev("tags")
        cards = []
        replay_by_cat = {ev("questions")[x["question_id"]]["category"]: x for x in need(r, "replays")}
        per_cat = {}
        for t in need(r, "traps"):
            per_cat[need(t, "category")] = per_cat.get(t["category"], 0) + 1
        for t in need(r, "traps"):
            cat = need(t, "category")
            rp = replay_by_cat.get(cat) or die(f"no replay for category {cat} (trap card {t.get('name')})")
            srcs = []
            for tid in need(t, "tags"):
                tag = tags.get(tid) or die(f"trap card {t['name']}: unknown tag {tid}")
                srcs.append(need(tag, "lineage", "source"))
            wrong = runs = 0
            for qid, q in ev("questions").items():
                if q["category"] != cat:
                    continue
                for st in score.SETUPS:
                    k, m, _ = record(ev, qid, st)
                    wrong, runs = wrong + m - k, runs + m
            failing = [st for st in score.SETUPS
                       if not is_ok(outcome(scored(ev, rp["question_id"], st, need(rp, "runs", st))[1]))]
            left = next((s for s in failing if s != "D"), "A")
            right = "D" if left != "D" else "A"
            href = f"#replay?q={rp['question_id']}&left={left}&right={right}"
            link = ("see it fail" if failing else "see the replay (no setup failed it)")
            cards.append(f"""
<article class="card trap">
  <h3>{e(need(t, "name"))}</h3>
  <p>{e(need(t, "rule"))}</p>
  <p class="small"><span class="pill">{e(need(t, "source"))}</span> <span class="muted">{e(" · ".join(dict.fromkeys(srcs)))}</span></p>
  <p class="small muted">{e(CATEGORY_NAMES[cat]) + (" (shared category)" if per_cat[cat] > 1 else "")}: {wrong} of {runs} runs wrong{"" if per_cat[cat] > 1 else " across all setups"}.</p>
  <a class="jump" href="{e(href)}">{e(link)} →</a>
</article>""")
        return f"""
<h2>{word(len(need(r, "traps"))).capitalize()} traps in real data</h2>
<p class="muted">Each trap is a rule the schema doesn't state. The questions cover {word(len(CATEGORY_NAMES))}
categories; year-to-date basis and fiscal calendars share one.</p>
<div class="grid-traps">{"".join(cards)}</div>
<p class="caption">{e(need(r, "proxy_caption"))}</p>"""

    # S3
    def fix(self):
        ev = self.ev
        r, tags, ts = ev("replays"), ev("tags"), ev("tool_specs")
        fields = ["semantic_type", "additive_over_time", "additive_over_entities", "time_rollup",
                  "period_basis", "derivation", "calendar"]
        cards = []
        for c in need(r, "tag_cards"):
            t = tags.get(need(c, "id")) or die(f"tags.yaml has no {c['id']}")
            rows = "".join(f"<dt>{e(k)}</dt><dd>{e(str(need(t, k)).lower() if isinstance(t[k], bool) else t[k])}</dd>"
                           for k in fields)
            lin = need(t, "lineage")
            rows += (f"<dt>lineage</dt><dd>{e(need(lin, 'source'))}; retrieved {e(need(lin, 'retrieved_on'))}. "
                     f"{e(need(lin, 'dedupe'))}</dd>")
            cards.append(f'<article class="card tag"><h3><code>{e(t["id"])}</code></h3>'
                         f'<p class="prevents">{e(need(c, "prevents"))}</p><dl class="fields">{rows}</dl></article>')
        desc = ts.DESCRIPTIONS
        for n in ("describe_column", "get_metric", "aggregate"):
            if n not in desc:
                die(f"src/tool_specs.py has no tool {n}")
        flow = f"""
<ol class="flow" aria-label="How setup D answers a question">
  <li class="node"><b>Analyst question</b><span class="small muted">in plain language</span></li>
  <li class="node"><code>describe_column</code><span class="small">{e(desc["describe_column"])}</span></li>
  <li class="node"><span><code>get_metric</code> / <code>aggregate</code></span><span class="small">{e(desc["get_metric"])}</span>
    <span class="small">{e(desc["aggregate"])}</span></li>
  <li class="node"><b>Answer + filing links</b><span class="small muted">every value carries its source</span></li>
</ol>"""
        return f"""
<h2>The fix: tag each metric, then enforce the tags</h2>
<p class="muted">A tag states what a metric is and how it may be combined. Two of the tags from
<code>tags/tags.yaml</code>, as stored:</p>
<div class="grid-tags">{"".join(cards)}</div>
<h3 class="sub">Enforcement: the tools read the tags and refuse what they forbid</h3>
{flow}
<p class="small muted">This is a minimal semantic layer (Kimball semi-additive measures, dbt MetricFlow,
metric views). The contribution is the measurement.</p>"""

    # S4
    def experiment(self):
        ev = self.ev
        s, r = ev("summary"), ev("replays")
        steps = []
        for i, st in enumerate(score.SETUPS):
            cfg = need(r, "setups", st)
            names = [t["name"] for t in SETUP_TOOLS[st]]
            tools = ", ".join(f"<code>{e(n)}</code>" for n in names)
            used = {c["name"] for k, rec in ev("runs").items() if k[1] == st for c in rec.get("tool_calls") or []}
            if used - set(names):
                die(f"setup {st} called tools {sorted(used - set(names))} outside its tool list")
            steps.append(f"""
<li class="step-card{' last' if st == 'D' else ''}">
  <div class="step-head"><span class="setup-tag">{e(st)}</span> {e(SETUP_NAMES[st])}</div>
  <p class="small"><b>Receives:</b> {e(need(cfg, "receives"))}</p>
  <p class="small"><b>Tools:</b> {tools}</p>
  <p class="small changed"><b>{"Starting point" if i == 0 else "Changes from " + score.SETUPS[i - 1]}:</b> {e(need(cfg, "changed"))}</p>
</li>""")
        n_q = len({q for v in s["setups"].values() for q in v["per_question"]})
        n_r = len(s["runs_per_question"])
        sample = self.claim("sample line: summary.json per_question, runs_per_question, model, run_dates, total_cost_usd",
                            f"{n_q} questions × {n_r} runs per setup, {', '.join(s['model'])}, run on "
                            f"{' and '.join(s['run_dates'])} (UTC), total cost ${s['total_cost_usd']:.2f}.")
        return f"""
<h2>The experiment: four setups, each adds one thing</h2>
<p class="muted">Same model, same instructions, same final-answer format. Only the context and tools change.</p>
<ol class="ladder">{"".join(steps)}</ol>
<p class="sample">{e(sample)}</p>"""

    # S5
    def results(self):
        ev = self.ev
        s, questions, r = ev("summary"), ev("questions"), ev("replays")
        st_ = s["setups"]
        acc = {x: (st_[x]["accuracy"]["mean"], st_[x]["accuracy"]["min"], st_[x]["accuracy"]["max"])
               for x in score.SETUPS}
        acc_rows = [(f"{x} · {SETUP_NAMES[x]}", *acc[x]) for x in score.SETUPS]
        acc_svg = svg_bars(acc_rows, "Accuracy by setup with lowest and highest run: " + "; ".join(
            f"{x} {pct(m)} (runs {pct(lo)} to {pct(hi)})" for x, (m, lo, hi) in acc.items()), True)
        acc_tab = hidden_table("Accuracy by setup", ["Setup", "Mean", "Lowest run", "Highest run"],
                               [[x, pct(m), pct(lo), pct(hi)] for x, (m, lo, hi) in acc.items()])
        beh = {x: st_[x]["behavior_accuracy"] for x in score.SETUPS}
        beh_svg = svg_bars([(f"{x} · {SETUP_NAMES[x]}", beh[x], None, None) for x in score.SETUPS],
                           "Behavior accuracy by setup: " + "; ".join(f"{x} {pct(v)}" for x, v in beh.items()), False)
        beh_tab = hidden_table("Behavior accuracy by setup", ["Setup", "Behavior accuracy"],
                               [[x, pct(v)] for x, v in beh.items()])
        # heatmap: rows = stored traps grouped by category, columns = setups
        replay_q = {questions[x["question_id"]]["category"]: x["question_id"] for x in need(r, "replays")}
        trap_cat = {}
        for q in questions.values():
            if q["id"] in st_["A"]["per_question"] and q["expected_behavior"] != "refuse":
                for t in q.get("trap_answers") or {}:
                    trap_cat.setdefault(t, q["category"])
        order = sorted(trap_cat, key=lambda t: (list(CATEGORY_NAMES).index(trap_cat[t]), t))
        rows, totals = [], {x: {} for x in score.SETUPS}
        for t in order:
            cells = []
            for x in score.SETUPS:
                th = st_[x]["trap_hits"][t]
                totals[x][t] = (th["hits"], th["runs"])
                left, right = (x, "D") if x != "D" else ("A", "D")
                href = f"#replay?q={replay_q[trap_cat[t]]}&left={left}&right={right}"
                hot = th["hits"] > 0
                cells.append(f'<td><a class="cell{" hot" if hot else ""}" style="--a:{min(1, th["rate"] * 4):.2f}" '
                             f'href="{e(href)}" aria-label="Setup {e(x)}, {e(t.replace("_", " "))}: {th["hits"]} of '
                             f'{th["runs"]} runs ({e(pct(th["rate"]))}); open the {e(CATEGORY_NAMES[trap_cat[t]])} replay">'
                             f'{th["hits"]}/{th["runs"]}</a></td>')
            rows.append(f'<tr><th scope="row"><span class="cat">{e(CATEGORY_NAMES[trap_cat[t]])}</span>'
                        f'{e(t.replace("_", " "))}</th>{"".join(cells)}</tr>')
        heat = (f'<table class="heat"><caption class="sr-only">Stored-trap hits by setup: hits / runs. '
                f'Each cell opens that category\'s replay.</caption><thead><tr><th scope="col">Trap</th>'
                + "".join(f'<th scope="col">{e(x)}</th>' for x in score.SETUPS)
                + f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')
        cost_rows = []
        for x in score.SETUPS:
            tok = sum(st_[x]["avg_tokens"][k] for k in TOKEN_KEYS)
            cost_rows.append(f"<tr><th scope='row'>{e(x)} · {e(SETUP_NAMES[x])}</th><td>{st_[x]['avg_tool_calls']:.1f}</td>"
                             f"<td>{tok:,.0f}</td><td>${st_[x]['cost_usd']:.3f}</td></tr>")
        cost = ("<table class='cost'><thead><tr><th scope='col'>Setup</th><th scope='col'>Tool calls per question</th>"
                "<th scope='col'>Tokens per question</th><th scope='col'>Total cost</th></tr></thead><tbody>"
                + "".join(cost_rows) + "</tbody></table>")
        f = self.facts()
        lead = [
            self.claim("results lead: wrong runs and stored-trap hits summed over setups (summary.json)",
                       f"On this data the traps rarely fired: {f['wrong']} wrong runs out of {f['total']}, and "
                       f"{f['hits']} stored-trap {plural(f['hits'], 'hit', 'hits')} in {f['checks']} checks."),
            self.claim(f"results lead: setup A mean accuracy; stated only if A is at most {FEW_ERRORS:.0%} wrong",
                       f"Setup A, with no tags, scored {pct(f['acc_a'])}, so the experiment sits near its ceiling "
                       "and can't show tags helping."),
            self.claim("results lead: wrong runs by type from report/failure_types.yaml; 'the one stored-trap hit' "
                       "only if the stored-trap-hit runs equal the period_misread runs",
                       breakdown_claim(f, trap_phrase=f["trap_phrase"])),
        ]
        if not f["trap_phrase"]:
            self.notes.append("stored-trap-hit runs differ from the period_misread runs; "
                              "'the one stored-trap hit' omitted from the Results lead")
        return f"""
<h2>Results at a glance</h2>
<p class="takeaway">{" ".join(e(t) for t in lead)}</p>
<div class="results-grid">
  <div class="panel"><h3>Accuracy by setup <span class="muted small">bar = mean, whiskers = lowest–highest run</span></h3>{acc_svg}{acc_tab}
    <h3>Behavior accuracy <span class="muted small">warn when needed, refuse when unanswerable</span></h3>{beh_svg}{beh_tab}</div>
  <div class="panel"><h3>Cost per setup <span class="muted small">means per question</span></h3>{cost}</div>
</div>
{self.trust_badges()}
<h3 class="sub">Stored-trap hits <span class="muted small">hits / runs; select a cell to open its replay</span></h3>
{heat}"""

    def trust_badges(self):
        ev = self.ev
        s = ev("summary")
        if re.search(r"^\s*(from|import)\s+semantics\b", ev("make_questions"), re.M):
            die("eval/make_questions.py imports semantics; the page says the answer key is independent")
        v = verification_counts(ev("vlog"), ev("vlog_ai"))
        frozen, first_run = commit_date("questions-frozen"), min(s["run_dates"])
        tests = pytest_passed()
        cost = f"${s['total_cost_usd']:.2f} to rerun"
        if tests is None:
            self.notes.append("pytest not run inside this build (it is itself running under pytest)")
        self.test_line = (f"{tests} tests pass · {cost}" if tests is not None
                          else f"Tests run when the page is published · {cost}")
        cards = [
            self.claim("trust badge: eval/make_questions.py does not import semantics.py",
                       "Answer key computed without semantics.py"),
            self.claim("trust badge: distinct sourced inputs (verification_log.csv), hand checks from "
                       "verification_ai.csv status hand_checked_reread, mismatches from verification_ai.csv",
                       f"{v['sourced']} inputs checked against primary sources ({v['hand']} by hand), "
                       f"{v['mismatches']} {plural(v['mismatches'], 'mismatch', 'mismatches')}"),
            self.claim("trust badge: git tag questions-frozen commit date; first run date in summary.json",
                       f"Questions frozen {frozen}; first run {first_run}"),
            self.claim("trust badge: pytest run during the build (passed count); summary.json total_cost_usd",
                       self.test_line),
        ]
        return ('<ul class="trust-grid" aria-label="How far to trust these numbers">'
                + "".join(f'<li class="trust">{e(c)}</li>' for c in cards) + "</ul>")

    # S5b, only when eval/results/A_raw.jsonl exists
    def exploratory(self):
        ev = self.ev
        s, q, raw = ev("summary"), ev("questions"), ev("a_raw")
        gone = ev("raw_schema")
        x = s["exploratory"]
        a, v, pc = s["setups"]["A"], x["setups"][X], x["a_vs_a_raw"]
        a_only, raw_only = pc["a_right_a_raw_wrong"], pc["a_raw_right_a_wrong"]
        verdict, p = a_raw_verdict(len(a_only), len(raw_only))
        self.claim("exploratory: A vs A_raw majority vote by question (summary.json exploratory.a_vs_a_raw), "
                   "exact two-sided sign test, a direction only if p < 0.05", verdict)
        removed = "; ".join(f"{t}: {', '.join(cs)}" for t, cs in gone.items())
        rows = [(f"{k} · {SETUP_NAMES[k].replace(' (exploratory)', '')}", w["accuracy"]["mean"], w["accuracy"]["min"], w["accuracy"]["max"])
                for k, w in (("A", a), (X, v))]
        bars = svg_bars(rows, "Accuracy, A vs A_raw, with lowest and highest run: " + "; ".join(
            f"{n} {pct(m)} (runs {pct(lo)} to {pct(hi)})" for n, m, lo, hi in rows), True)
        ranges = " · ".join(f"{e(n.split(' · ')[0])}: runs {e(pct(lo))} to {e(pct(hi))}" for n, _, lo, hi in rows)

        def traps(w):
            return sum(t["hits"] for t in w["trap_hits"].values()), sum(t["runs"] for t in w["trap_hits"].values())

        def tok(w):
            return sum(w["avg_tokens"][k] for k in TOKEN_KEYS)

        def rng(r):
            return f"{pct(r['mean'])} [{pct(r['min'])}, {pct(r['max'])}]"
        metrics = [
            ("Correct runs", lambda w: f"{w['correct_runs']} of {w['n']}"),
            ("Accuracy, mean [lowest, highest run]", lambda w: rng(w["accuracy"])),
            ("Behavior accuracy", lambda w: pct(w["behavior_accuracy"])),
            ("Stored-trap hits", lambda w: "{} of {}".format(*traps(w))),
            ("Unparseable final lines", lambda w: str(len(w["unparsed"]))),
            ("Over-warned runs (not scored wrong)", lambda w: f"{w['over_warning_runs']} of {w['answer_question_runs']}"),
            ("Tool calls per question", lambda w: f"{w['avg_tool_calls']:.1f}"),
            ("Tokens per question", lambda w: f"{tok(w):,.0f}"),
            ("Total cost", lambda w: f"${w['cost_usd']:.3f}"),
        ]
        body = "".join(f"<tr><th scope='row'>{e(m)}</th><td>{e(f(a))}</td><td>{e(f(v))}</td></tr>" for m, f in metrics)
        cats = "".join(f"<tr><th scope='row'>{e(CATEGORY_NAMES[c])}</th><td>{e(rng(a['accuracy_by_category'][c]))}</td>"
                       f"<td>{e(rng(v['accuracy_by_category'][c]))}</td></tr>" for c in CATEGORY_NAMES
                       if c in v["accuracy_by_category"])
        table = (f"<table class='cost'><thead><tr><th scope='col'>Measure</th><th scope='col'>A · {e(SETUP_NAMES['A'])}</th>"
                 f"<th scope='col'>A_raw · {e(SETUP_NAMES[X])}</th></tr></thead><tbody>{body}</tbody></table>")
        cat_table = (f"<table class='cost'><thead><tr><th scope='col'>Category</th><th scope='col'>A</th>"
                     f"<th scope='col'>A_raw</th></tr></thead><tbody>{cats}</tbody></table>")
        repo = need(ev("replays"), "links", "repo")
        hq = need(ev("replays"), "hero", "question_id")
        if X not in next((x["runs"] for x in need(ev("replays"), "replays") if x["question_id"] == hq), {}):
            die(f"replays.yaml: the hero replay {hq} needs an A_raw run when A_raw.jsonl exists")
        lst = lambda ids: f" ({', '.join(ids)})" if ids else ""  # noqa: E731
        n_runs = len(v["runs_per_question"])
        return f"""
<div class="kicker exploratory">Added after seeing the main results</div>
<h2>Why the baseline was so strong</h2>
<p class="muted">Setup A again, on a copy of the database with the columns that carry meaning removed
({e(removed)}). Same questions, answer key, model, instructions and scorer. Each removed column can be
recomputed from columns that stayed (<code>src/build_raw_views.py</code> checks this), so no question became
unanswerable. This run is not one of the planned comparisons.</p>
<div class="box">
<p class="verdict">{e(verdict)}</p>
<dl class="counts">
  <div><dt>A right, A_raw wrong</dt><dd>{len(a_only)}<span class="small muted">{e(lst(a_only))}</span></dd></div>
  <div><dt>A_raw right, A wrong</dt><dd>{len(raw_only)}<span class="small muted">{e(lst(raw_only))}</span></dd></div>
  <div><dt>Both right</dt><dd>{pc["both_right"]}</dd></div>
  <div><dt>Both wrong</dt><dd>{pc["both_wrong"]}</dd></div>
</dl>
<p class="small muted">A setup is right on a question when more than half of its {n_runs} runs are correct
({pc["questions"]} questions). Exact two-sided sign test on the {pc["discordant"]} discordant
question{"" if pc["discordant"] == 1 else "s"}: {e(sign_test_text(pc["discordant"], p))}.</p>
</div>
<div class="results-grid">
  <div class="panel"><h3>Accuracy <span class="muted small">bar = mean, whiskers = lowest–highest run</span></h3>{bars}
    <p class="small muted range-text">{ranges}</p>{table}</div>
  <div class="panel"><h3>Accuracy by category <span class="muted small">mean [lowest, highest run]</span></h3>{cat_table}</div>
</div>
<p class="small"><a class="jump" href="#replay?q={e(hq)}&amp;left=A&amp;right=A_raw">Compare A and A_raw on {e(hq)} →</a> ·
<a href="{e(repo)}/blob/main/eval/results/A_raw_failures.md">A_raw runs worth reading</a> ·
<a href="{e(repo)}/blob/main/eval/results/summary.md">summary.md</a></p>"""

    # Results, last: what a correct score does not show
    def misses(self):
        ev = self.ev
        s, q = ev("summary"), ev("questions")
        items = []
        raw = ev("a_raw")
        if raw is not None:
            q016 = sorted(k for k in raw if k[0] == "q016")
            said = [k for k in q016 if re.search(r"total operating cash flow", " ".join(raw[k].get("text") or []), re.I)]
            ok = sum(score.score_run(raw[k], q["q016"])["correct"] for k in q016)
            if said:
                t = self.claim(
                    "q016: A_raw runs scored correct (score.py) and A_raw runs whose recorded text contains "
                    "'total operating cash flow'",
                    f"q016, the right number with the wrong explanation: on Darden operating cash flow from continuing "
                    f"operations, {ok} of {len(q016)} A_raw runs had the right number, and {len(said)} told the reader "
                    "it was total operating cash flow; the scorer doesn't grade the explanation.")
                rec = raw[said[0]]
                items.append(f"""
<li><span class="kicker exploratory">From the exploratory run</span>
  <p>{e(t)}</p>
  <details class="transcript"><summary>show transcript (A_raw, q016, run {said[0][1]})</summary>
    <p class="small"><b>Final answer:</b> {e(json.dumps(rec.get("final")))}</p>
    <div class="steps" data-verbatim>{render_steps(rec)}</div></details></li>""")
        st_ = s["setups"]
        ow = ", ".join(f"{x} {st_[x]['over_warning_runs']} of {st_[x]['answer_question_runs']}" for x in score.SETUPS)
        t = self.claim("over-warning: summary.json over_warning_runs / answer_question_runs per setup",
                       f"Over-warned runs (a warning when none was needed, not scored wrong): {ow}.")
        d_vals = {st_[x]["answer_question_runs"] for x in score.SETUPS}
        if len(d_vals) != 1:
            die(f"over-warning runs are out of different totals per setup ({d_vals}); the lead sentence needs one shared total")
        lead = self.claim(
            "over-warning lead: summary.json over_warning_runs for A, B and D, read against the same "
            "answer_question_runs total; no comparison between B and C",
            f"This is the one place context visibly changed behavior: over-warning fell from "
            f"{st_['A']['over_warning_runs']} of {d_vals.pop()} runs with no tags to {st_['B']['over_warning_runs']} "
            f"with prose and {st_['D']['over_warning_runs']} with the enforcing tools. It was not a planned measure, "
            "so treat it as a lead, not a result.")
        items.append(f"<li><p>{e(t)} {e(lead)}</p></li>")
        return f"""
<div class="note-box">
<h2>What the score misses</h2>
<ul class="misses">{"".join(items)}</ul>
</div>"""

    # Conclusion: the whole experiment in one section, organised by the two problems it addresses
    # (AI accessibility; alternative data and onboarding). Every number is read from the outputs.
    def conclusion(self):
        ev = self.ev
        s, questions, r = ev("summary"), ev("questions"), ev("replays")
        f = self.facts()
        st_ = s["setups"]
        repo = need(r, "links", "repo")
        rule = "conclusion: "
        n_q = len({qq for v in st_.values() for qq in v["per_question"]})
        n_cat_q = {}
        for qq in questions.values():
            n_cat_q[qq["category"]] = n_cat_q.get(qq["category"], 0) + 1
        qpc = (str(min(n_cat_q.values())) if len(set(n_cat_q.values())) == 1
               else f"{min(n_cat_q.values())}–{max(n_cat_q.values())}")
        companies = len({SEC_RE.fullmatch(x["source_url"])[1] for x in ev("vlog") if SEC_RE.fullmatch(x["source_url"])})

        # Pillar 1 evidence
        with_src = {x: [0, 0] for x in score.SETUPS}
        for (qid, st, _), rec in ev("runs").items():
            if questions[qid]["expected_behavior"] == "refuse":
                continue
            with_src[st][1] += 1
            with_src[st][0] += bool(tool_sources(rec, repo))
        if any(with_src[x][0] for x in score.SETUPS if x != "D"):
            die("a SQL setup returned sources; the conclusion says only the enforcing tool does")
        dk, dn = with_src["D"]
        bc = s["b_vs_c"]
        _, bvc_p = b_vs_c_verdict(len(bc["b_right_c_wrong"]), len(bc["c_right_b_wrong"]))
        b_c_disc = len(bc["b_right_c_wrong"]) + len(bc["c_right_b_wrong"])
        d = st_["A"]["answer_question_runs"]
        if {st_[x]["answer_question_runs"] for x in score.SETUPS} != {d}:
            die("over-warning totals differ by setup; the conclusion needs one shared total")
        d_wrong = st_["D"]["n"] - st_["D"]["correct_runs"]
        if f["n"]["tool_interface"] != d_wrong:
            die("not every wrong setup D run is a tool_interface failure; the conclusion says they all are")

        # Pillar 2 evidence: vendor-style traps
        parent = [(st_[x]["trap_hits"]["included_parent_rows"]["hits"], st_[x]["trap_hits"]["included_parent_rows"]["runs"])
                  for x in score.SETUPS]
        p_hits, p_checks = sum(h for h, _ in parent), sum(n for _, n in parent)
        if p_hits:
            die("the parent-row trap fired; the conclusion says no run added the parent's row")
        h_ok = h_n = 0
        c_warn = c_n = 0
        for (qid, st, _), rec in ev("runs").items():
            qq = questions[qid]
            sc = score.score_run(rec, qq)
            if qq["category"] == "hierarchy":
                h_n += 1
                h_ok += sc["correct"]
            if qq["category"] == "comparability_unanswerable" and qq["expected_behavior"] == "answer_with_warning":
                c_n += 1
                c_warn += bool(sc["final"] and sc["final"]["warning"])
        # Pillar 2 evidence: auto-drafted tags (followup/autotag)
        at = ev("autotag")
        at_sc = [score.score_run(rec, questions[k[0]]) for k, rec in at["runs"].items()]
        at_ok, at_n = sum(x["correct"] for x in at_sc), len(at_sc)
        at_bad = [x for x in at_sc if not x["correct"]]
        refused = sum(1 for x in at_bad if x["final"] and x["final"]["refused"])
        no_final = sum(1 for x in at_bad if x["final"] is None)
        silent = sum(1 for x in at_bad if x["final"] and not x["final"]["refused"] and not x["final"]["warning"]
                     and x["value"] is not None)
        if silent:
            die("auto-drafted tags produced silent wrong numbers; the conclusion says none did")
        if refused + no_final != len(at_bad):
            die("some auto-tag failures are neither refusals nor missing final lines; reword the conclusion")
        verdicts = need(at["scores"], "verdicts")
        review = sum(1 for v in verdicts.values() if v["verdict"] == "needs human review")

        bottom = self.claim(rule + f"setup A at most {FEW_ERRORS:.0%} wrong (summary.json); judgment drawn from the findings below",
                            "Getting reliable answers from AI on financial data depends less on the model and more on how "
                            "the data is described and what tools the model is given. On this data the model already did the "
                            "math right almost every time. What made the difference was around the model: whether each answer "
                            "came with its source, whether the tool let the model ask for what it needed, and whether the "
                            "descriptions of the data were correct.")
        did = self.claim(rule + "question and company counts; summary.json model, runs and cost",
                         f"We wrote {n_q} questions an analyst might ask about {word(companies)} restaurant companies, using "
                         f"their SEC filings and public data, and asked {', '.join(s['model'])} each question in four setups, "
                         "each adding one thing: (A) only the table and column names; (B) a plain-English description of "
                         "every column; (C) the same facts as structured tags; (D) a tool that applies those tags and does "
                         f"the calculation, with no SQL allowed. {f['total']} answers in total, costing "
                         f"${s['total_cost_usd']:.2f}. The correct answers were computed separately and checked against the "
                         "original filings, and the questions were locked before the first run.")
        disagree = (f"they disagreed on only {b_c_disc} {plural(b_c_disc, 'question', 'questions')}, too few to tell "
                    "apart" if b_c_disc < MIN_DISCORDANT else f"exact sign test, p = {bvc_p:.2f}")
        p1 = [
            self.claim(rule + "setup A mean accuracy and wrong runs (summary.json)",
                       f"Accuracy was not the bottleneck. Given only the table and column names, the model was already "
                       f"{pct(f['acc_a'])} correct; only {f['wrong']} of {f['total']} answers were wrong. So this test "
                       "cannot show that describing the data improves accuracy."),
            self.claim(rule + "B vs C exact sign test, stated only if p >= 0.05 (checked in facts())",
                       "Writing style did not matter. Plain-English descriptions and structured tags carrying the same "
                       f"facts showed no measurable difference ({disagree})."),
            self.claim(rule + "answerable runs whose tools returned at least one source, per setup",
                       "The tool made answers traceable. Only when the model had to go through the tool, instead of "
                       f"writing SQL, did each answer come with a link to its source: {dk} of {dn} answers, against none "
                       "when it wrote SQL itself. An analyst who cannot read SQL can still check the number."),
            self.claim(rule + "over_warning_runs for A, B and D against the shared answer_question_runs total",
                       f"Descriptions cut false alarms. Unneeded caveats fell from {st_['A']['over_warning_runs']} of {d} "
                       f"answers with no descriptions to {st_['B']['over_warning_runs']} with plain-English descriptions "
                       f"and {st_['D']['over_warning_runs']} with the tool. We did not plan to measure this, so treat it as "
                       "a hint, not a result."),
            self.claim(rule + "wrong setup D runs equal the tool_interface runs in report/failure_types.yaml",
                       "The tool itself became the weak point. "
                       + ("Both of the tool setup's wrong answers" if d_wrong == 2 else
                          "The tool setup's one wrong answer" if d_wrong == 1 else
                          f"All {word(d_wrong)} of the tool setup's wrong answers")
                       + " came from limits in how the tool accepts requests, not from the data."),
        ]
        p2 = [
            self.claim(rule + "included_parent_rows trap hits (summary.json); hierarchy runs correct; comps runs that warned",
                       "Messy vendor-style data was mostly handled. No answer double-counted a parent company on top of its "
                       f"brands ({p_hits} times in {p_checks} chances); questions about brands were wrong in {h_n - h_ok} "
                       f"of {h_n} answers; and where each company defines comparable sales its own way, the model added the "
                       f"required caveat in {c_warn} of {c_n} answers."),
            self.claim(rule + "followup/autotag/results/D_autotag.jsonl scored with score.py; hand D from summary.json; "
                       "field verdicts from followup/autotag/results/score_tags.json",
                       "Letting AI write the descriptions is not safe yet. In a follow-up, a model wrote the tags itself "
                       "from column summaries and documentation, as you might for a new vendor dataset. With those tags in "
                       f"place of the human-written ones, correct answers in the tool setup fell from "
                       f"{st_['D']['correct_runs']} to {at_ok} out of {at_n}. It failed safely: {refused} refusals and "
                       f"{no_final} unfinished answers, and no confidently wrong numbers. But {review} of {len(verdicts)} "
                       "tag fields needed a person to correct them. The approach this points to: AI drafts, a person "
                       "approves, and a test set checks the result."),
        ]
        means = self.claim(rule + "restates the rule-checked findings above",
                           "To make existing data usable by AI, the work that pays off is: descriptions a person has checked, "
                           "a tool that returns the source with every number, and a set of real analyst questions to test "
                           "before and after. A smarter model is not the main lever. For new vendor data, the messy parts can "
                           "be handled, but AI-written descriptions need a human review before they can be trusted at scale.")
        limits = self.claim(rule + "questions per category and companies (questions.yaml, verification_log.csv)",
                            f"Limits: {qpc} questions per category, {word(companies)} companies, one model. The website-traffic "
                            "data stands in for a real vendor dataset and predicts nothing. The tool was designed around these "
                            "question types, and the same person wrote both the questions and the system.")
        li = lambda items: "".join(f"<li>{e(t)}</li>" for t in items)  # noqa: E731
        return f"""
<h2>Conclusion</h2>
<div class="conclusion">
<p class="punch">{e(bottom)}</p>
<h3>Why we did it</h3>
<p>Analysts now ask AI assistants questions about financial data in plain English. That raises two problems.
First, existing datasets have to be made usable by AI. Connecting a model to a database (for example through an
MCP connector) is not enough: the model also has to know what each column means, such as whether it can be added
up across quarters, whether it is a year-to-date total, and which fiscal calendar it follows. Second, new data from
outside vendors, often called alternative data, arrives messy: daily rows, brand and parent-company rows mixed
together, renamed series, and definitions that differ by company. We built both problems into one test, using
traps taken from real company filings.</p>
<h3>What we did</h3>
<p>{e(did)}</p>
<h3>What we found: using existing data with AI</h3>
<ol>{li(p1)}</ol>
<h3>What we found: adding new, messy data</h3>
<ol start="{len(p1) + 1}">{li(p2)}</ol>
<h3>What it means</h3>
<p>{e(means)}</p>
<h3>What would change the answer</h3>
<p>A harder test: data whose meaning cannot be worked out from the other columns, more questions so that small
differences show up, and grading that checks the explanation, not just the final number.</p>
<p class="small muted">{e(limits)}</p>
</div>"""

    # Footer: limits (SPEC §11.8)
    def limits(self):
        ev = self.ev
        r = ev("replays")
        n_cat = {}
        for qq in ev("questions").values():
            n_cat[qq["category"]] = n_cat.get(qq["category"], 0) + 1
        qpc = str(min(n_cat.values())) if len(set(n_cat.values())) == 1 else f"{min(n_cat.values())}–{max(n_cat.values())}"
        ciks = {SEC_RE.fullmatch(x["source_url"])[1] for x in ev("vlog") if SEC_RE.fullmatch(x["source_url"])}
        fmt = {"questions_per_category": qpc, "companies": len(ciks)}
        lims = "".join(f"<li>{e(lim.format(**fmt))}</li>" for lim in need(r, "limitations"))
        return f"""
<h2>Limits</h2>
<ul class="limits">{lims}</ul>"""

    # S6
    def replay(self):
        ev = self.ev
        r, questions = ev("replays"), ev("questions")
        items = need(r, "replays")
        default = need(r, "default_replay")
        cats = [(questions.get(need(x, "question_id")) or die(f"replay question {x['question_id']} not in questions.yaml"))["category"]
                for x in items]
        if sorted(cats) != sorted(CATEGORY_NAMES):
            die(f"replays.yaml must list one replay per category, got {cats}")
        if default not in [x["question_id"] for x in items]:
            die(f"default_replay {default} is not one of the replays")
        for x in items:
            qid = x["question_id"]
            for st in tab_setups(x, ev):
                run = need(x, "runs", st)
                o = outcome(scored_any(ev, qid, st, run)[1])
                exp = need(x, "expect", st)
                if exp not in BADGES:
                    die(f"replays.yaml {qid} {st}: unknown expected outcome {exp}")
                if o != exp:
                    die(f"replays.yaml says {qid} setup {st} run {run} is '{exp}', but the recorded score is '{o}'")
        a_ok, a_n, _ = record(ev, default, "A")
        if a_ok == a_n:
            die(f"setup A answered the default replay {default} correctly in all {a_n} runs; "
                "pick a different default_replay in report/replays.yaml")
        d_item = next(x for x in items if x["question_id"] == default)
        if is_ok(outcome(scored(ev, default, "A", d_item["runs"]["A"])[1])):
            die(f"the default replay shows a correct setup A run ({default} run {d_item['runs']['A']}); "
                "show one of A's failed runs")
        ordered = sorted(items, key=lambda x: list(CATEGORY_NAMES).index(questions[x["question_id"]]["category"]))
        picker = "".join(
            f'<button type="button" role="radio" aria-checked="{"true" if x["question_id"] == default else "false"}" '
            f'tabindex="{0 if x["question_id"] == default else -1}" data-q="{e(x["question_id"])}">'
            f'{e(CATEGORY_NAMES[questions[x["question_id"]]["category"]])}</button>' for x in ordered)
        blocks = []
        for x in ordered:
            qid = x["question_id"]
            q = questions[qid]
            cols = []
            for side, start in (("left", "A"), ("right", "D")):
                tabs = "".join(
                    f'<button type="button" role="tab" data-setup="{st}" aria-selected="{"true" if st == start else "false"}" '
                    f'tabindex="{0 if st == start else -1}">{st} · {e(SETUP_NAMES[st])}</button>' for st in tab_setups(x, ev))
                panes = "".join(self.pane(qid, st, x["runs"][st], st != start) for st in tab_setups(x, ev))
                cols.append(f'<div class="col" data-side="{side}"><div class="tabs" role="tablist" '
                            f'aria-label="Setup shown in the {side} column">{tabs}</div>{panes}</div>')
            expected = ("refuse (the data isn't there)" if q["expected_behavior"] == "refuse" else
                        f"{num(q['correct'])} {q['unit']}"
                        + (", with a warning" if q["expected_behavior"] == "answer_with_warning" else ""))
            blocks.append(f"""
<div class="replay" data-q="{e(qid)}"{"" if qid == default else " hidden"}>
  <p class="q"><span class="muted">{e(qid)} · {e(CATEGORY_NAMES[q["category"]])}</span><br>“{e(q["question"])}”</p>
  <p class="small"><b>Correct answer:</b> {e(expected)} · <b>Sources:</b> {source_html(ev, qid)}</p>
  <p class="small muted">{e(need(x, "note"))}</p>
  <div class="cols">{"".join(cols)}</div>
</div>""")
        return f"""
<h2>Side-by-side replay</h2>
<p class="muted">Recorded runs, shown as recorded. Pick a question, then a setup for each column.</p>
<div class="picker" role="radiogroup" aria-label="Replay question">{picker}</div>
{"".join(blocks)}"""

    def pane(self, qid, setup, run, hidden):
        ev = self.ev
        rec, sc = scored_any(ev, qid, setup, run)
        k, n, outs = record_any(ev, qid, setup)
        f = sc["final"]
        if f:
            final = (f"{num(f['answer']) if f['answer'] is not None else 'no number'} {f['unit'] or ''}".strip()
                     + f" · warning {str(f['warning']).lower()} · refused {str(f['refused']).lower()}")
        else:
            final = f"no FINAL line (stopped: {rec.get('stop_reason')})"
        runs_line = ", ".join(f"run {i}: {BADGES[o][0].lower()}" for i, o in outs)
        srcs = tool_sources(rec, need(ev("replays"), "links", "repo"))
        src_html = (" · ".join(f'<a href="{e(u)}">{e(l)}</a>' for l, u in srcs) if srcs else
                    '<span class="muted">none returned in this run</span>')
        return f"""
<div class="pane" data-setup="{e(setup)}" role="tabpanel"{" hidden" if hidden else ""}>
  <div class="pane-head">{badge(sc)} <span class="small muted">setup {e(setup)}, run {run} · {k} of {n} runs correct ({e(runs_line)})</span></div>
  <p class="small"><b>Final answer:</b> {e(final)}</p>
  <p class="small tool-sources"><b>Sources returned by its tools:</b> {src_html}</p>
  <div class="steps" data-verbatim>{render_steps(rec)}</div>
</div>"""

    # S7
    def b_vs_c(self):
        s = self.ev("summary")
        bc = s["b_vs_c"]
        b, c = len(bc["b_right_c_wrong"]), len(bc["c_right_b_wrong"])
        if b + c + bc["both_right"] + bc["both_wrong"] != bc["questions"]:
            die("summary.json b_vs_c counts do not add up to b_vs_c.questions")
        verdict, p = b_vs_c_verdict(b, c)
        self.claim("§3 B vs C: exact two-sided sign test (McNemar) on discordant questions, p < 0.05", verdict)
        n_runs = len(s["runs_per_question"])
        lst = lambda ids: f" ({', '.join(ids)})" if ids else ""  # noqa: E731
        notes = s["scorer_notes"]
        if len(notes) != 1:
            die(f"summary.json has {len(notes)} scorer_notes; the B vs C line describes exactly one fix")
        n = notes[0]
        if not n["flip_direction"].startswith("incorrect to correct"):
            die("scorer_notes flip_direction is not 'incorrect to correct'; the B vs C line says it is")
        fb, fc = n["flipped_by_setup"].get("B", 0), n["flipped_by_setup"].get("C", 0)
        fix_line = self.claim("B vs C: summary.json scorer_notes flipped_by_setup and flip_direction",
                              f"B's count includes the unit-parsing fix described in How it was checked, which changed "
                              f"{fb} B {plural(fb, 'run', 'runs')} and {fc} C {plural(fc, 'run', 'runs')} from "
                              "incorrect to correct.")
        return f"""
<div class="box">
<h2>B vs. C, paired by question</h2>
<p class="verdict">{e(verdict)}</p>
<dl class="counts">
  <div><dt>B right, C wrong</dt><dd>{b}<span class="small muted">{e(lst(bc["b_right_c_wrong"]))}</span></dd></div>
  <div><dt>C right, B wrong</dt><dd>{c}<span class="small muted">{e(lst(bc["c_right_b_wrong"]))}</span></dd></div>
  <div><dt>Both right</dt><dd>{bc["both_right"]}</dd></div>
  <div><dt>Both wrong</dt><dd>{bc["both_wrong"]}</dd></div>
</dl>
<p class="small muted">B and C receive the same facts; only the format differs. A setup is right on a question
when more than half of its {n_runs} runs are correct (majority vote). Exact two-sided sign test (McNemar) on
the {b + c} discordant question{"" if b + c == 1 else "s"}: {e(sign_test_text(b + c, p))}.</p>
<p class="small">{e(fix_line)}</p>
</div>"""

    # S8
    def failures(self):
        ev = self.ev
        entries = parse_error_analysis(ev("error_analysis"))
        r = ev("replays")
        shown = {(x["question_id"], st, x["runs"][st]) for x in need(r, "replays") for st in score.SETUPS}
        groups = []
        for st in FAILURE_ORDER:
            es = entries.get(st) or die(f"docs/error_analysis.md has no entries for setup {st}")
            if len(es) != 2:
                die(f"docs/error_analysis.md lists {len(es)} entries for setup {st}; expected 2")
            k = sum(record(ev, q, st)[0] for q in ev("questions"))
            n = sum(record(ev, q, st)[1] for q in ev("questions"))
            items = []
            failed = 0
            for qid, run, title, happened, fix, _ in es:
                if qid not in ev("questions"):
                    die(f"docs/error_analysis.md cites unknown question {qid}")
                rec, sc = scored(ev, qid, st, run)
                failed += not is_ok(outcome(sc))
                mark = badge(sc)
                if k == n:  # a setup with no wrong runs shows over-warning examples instead
                    if not (sc["correct"] and sc["over_warning"]):
                        die(f"error_analysis.md {st} {qid} run {run}: a no-failure setup's example must be an "
                            "over-warned, correct run")
                    mark = '<span class="badge neutral">Over-warned</span>'
                if (qid, st, run) in shown:
                    left, right = (st, "D") if st != "D" else ("A", "D")
                    more = f'<a class="jump" href="#replay?q={e(qid)}&amp;left={left}&amp;right={right}">open its replay →</a>'
                else:
                    more = (f'<details class="transcript"><summary>show transcript (setup {e(st)}, run {run})</summary>'
                            f'<p class="small"><b>Final answer:</b> {e(json.dumps(sc["final"]))}</p>'
                            f'<div class="steps" data-verbatim>{render_steps(rec)}</div></details>')
                items.append(f"""
<li class="fail" data-q="{e(qid)}" data-run="{run}">
  <div>{mark} <b>{e(qid)}, run {run}</b>{" — " + e(title) if title else ""}</div>
  <p class="small"><b>What happened:</b> {inline_md(happened)}</p>
  <p class="small"><b>What would fix it:</b> <span class="fix">{inline_md(fix)}</span></p>
  {more}
</li>""")
            if st == "D" and not failed:
                die("docs/error_analysis.md: no D entry is a scored failure; SPEC §11.7 needs one from D")
            head = ""
            if not failed:
                head = self.claim("no-failure note: setup's scored runs, all correct",
                                  f"{st} had no incorrect runs ({k} of {n} correct); the error analysis lists two "
                                  "over-warning examples instead, which are scored correct.")
            title = (f'{e(st)} · {e(SETUP_NAMES[st])}: {n - k} of {n} runs wrong; {word(len(items))} over-warnings shown'
                     if k == n else
                     f'{e(st)} · {e(SETUP_NAMES[st])} <span class="muted small">{n - k} of {n} runs wrong</span>')
            groups.append(f'<div class="fail-group"><h3>{title}</h3>'
                          + (f'<p class="small muted">{e(head)}</p>' if head else "")
                          + f'<ul class="fails">{"".join(items)}</ul></div>')
        return f"""
<h2>Where it fails</h2>
<p class="muted">Two instructive runs per setup, from <code>docs/error_analysis.md</code>. Each badge is
recomputed from the recorded score. D comes first: its failures show where the enforcing tools
themselves broke on answerable questions.</p>
<div class="fail-grid">{"".join(groups)}</div>"""

    # S9
    def checks(self):
        ev = self.ev
        s, vlog, questions, r = ev("summary"), ev("vlog"), ev("questions"), ev("replays")
        if re.search(r"^\s*(from|import)\s+semantics\b", ev("make_questions"), re.M):
            die("eval/make_questions.py imports semantics; the page says the answer key is independent")
        by_q = {}
        for row in vlog:
            by_q.setdefault(row["question_id"], []).append(row["matches"].strip().lower() == "yes")
        n_q = len(questions)
        all_yes = sum(1 for q in questions if by_q.get(q) and all(by_q[q]))
        verified = [self.claim("verification: questions whose verification_log rows all say matches=yes",
                               f"{all_yes} of {n_q} questions have every row in the verification log marked "
                               f"matches = yes ({len(vlog)} rows).")]
        verified += [self.claim("verification: distinct inputs in verification_log.csv; hand checks from its notes; "
                                "AI-assisted read, mismatches and revisions from verification_ai.csv", t)
                     for t in verification_claims(verification_counts(vlog, ev("vlog_ai")))]
        g = ev("git")
        draft_rev = need(r, "provenance", "draft_commit")
        repl_rev = need(r, "provenance", "replacement_commit")
        repl = need(r, "provenance", "replacement_questions")
        for q in repl:
            if q not in questions:
                die(f"replays.yaml provenance.replacement_questions: {q} not in questions.yaml")
        if "questions_draft.md" not in g("show", "--name-only", "--format=", draft_rev):
            die(f"draft_commit {draft_rev} does not touch eval/questions_draft.md")
        d_draft, d_engine = commit_date(draft_rev), first_commit_date("src/semantics.py")
        d_repl, d_frozen = commit_date(repl_rev), commit_date("questions-frozen")
        first_run = min(s["run_dates"])
        if not (d_draft <= d_engine <= d_repl <= d_frozen <= first_run):
            die(f"provenance dates out of order: draft {d_draft}, engine {d_engine}, replacements {d_repl}, "
                f"frozen {d_frozen}, first run {first_run}")
        frozen = self.claim(
            "provenance: git commit dates of the draft, src/semantics.py's first commit, the replacement commit and tag questions-frozen",
            f"Most questions were written before the rule engine, and all were frozen before any run: drafted {d_draft} (commit {draft_rev}), "
            f"before semantics.py was first committed ({d_engine}); {word(len(repl))} replacements "
            f"({', '.join(repl)}) were added {d_repl}, after it; all frozen {d_frozen} (git tag questions-frozen), "
            f"before the first run ({first_run}).")
        test_li = "<li>" + e(self.claim("tests: pytest run during the build (same line as the trust badge)",
                                        self.test_line)) + "</li>"
        bug = []
        for n in s["scorer_notes"]:
            fl = n["flipped_by_setup"]
            bug.append(self.claim(
                "scorer disclosure: summary.json scorer_notes",
                f"Post-hoc scorer fix, made after the runs were scored and before publishing (found {n['found']}, "
                f"commit {n['fix_commit']}): {n['description']} The fix changed {n['runs_flipped']} runs "
                f"({', '.join(f'{k} {v}' for k, v in fl.items())}; {', '.join(n['flipped_questions'])}), all from "
                "incorrect to correct."))
        repo = need(r, "links", "repo")
        return f"""
<h2>How it was checked</h2>
<ul class="checks">
  <li>The answer key was computed by <code>eval/make_questions.py</code> with direct SQL, independent of
  <code>semantics.py</code>, so the code being tested does not grade itself.</li>
  {"".join(f"<li>{e(t)}</li>" for t in verified)}
  <li>{e(frozen)}</li>
  {test_li}
  {"".join(f"<li>{e(b)}</li>" for b in bug)}
</ul>
<p><a href="{e(repo)}">Repository</a> · <a href="{e(repo)}/blob/main/eval/verification_log.csv">Verification log</a> ·
<a href="{e(repo)}/blob/main/eval/verification_ai.csv">AI-assisted source reads</a> ·
<a href="{e(repo)}/blob/main/docs/error_analysis.md">Error analysis</a></p>"""

    # S10
    def next(self):
        ev = self.ev
        r, s = ev("replays"), ev("summary")
        if len(need(r, "next_steps")) != 3:
            die("replays.yaml next_steps must have exactly three items")
        steps = list(need(r, "next_steps"))
        if ev("a_raw") is None:
            steps.append(A_RAW_NOT_RUN)
        else:
            pc = need(s, "exploratory", "a_vs_a_raw")
            steps.append(self.claim("next step: exploratory A vs A_raw sign test (summary.json exploratory.a_vs_a_raw), "
                                    "a direction only if p < 0.05",
                                    a_raw_next_step(len(pc["a_right_a_raw_wrong"]), len(pc["a_raw_right_a_wrong"]))))
        items = "".join(f"<li>{e(x)}</li>" for x in steps)
        repo = need(r, "links", "repo")
        video = (r.get("links") or {}).get("video")
        if not video:
            self.notes.append("replays.yaml links.video is absent; the footer omits the video link")
        xd = s.get("exploratory", {}).get("setups", {}).get(X, {}).get("run_dates") if ev("a_raw") is not None else None
        self.closing = (f"A small experiment. All numbers generated from recorded runs on {' and '.join(s['run_dates'])} (UTC)"
                        + (f"; the exploratory A_raw runs on {' and '.join(xd)} (UTC)." if xd else "."))
        return f"""
<h2>Next steps</h2>
<ol class="next">{items}</ol>
<footer class="foot"><a href="{e(repo)}">Repository</a>{f' · <a href="{e(video)}">Video</a>' if video else ""}
<p class="small muted">{e(self.closing)}</p></footer>"""


def tool_sources(rec, repo):
    """(label, url) for each distinct source the run's tools returned, labelled like the links above the columns."""
    out, seen = [], set()
    for c in rec.get("tool_calls") or []:
        try:
            o = json.loads(c["output"]) if isinstance(c["output"], str) else c["output"]
        except (TypeError, ValueError):
            continue
        for src in (o.get("sources") or []) if isinstance(o, dict) else []:
            t, u = src.get("type"), src.get("url")
            if not u:
                continue
            if t == "sec_filing":
                label, u = f"{src.get('form') or 'SEC filing'} · {src['accession']}", sec_link(u) or u
            elif t == "earnings_release":
                label = f"Earnings release · {src.get('ticker')}"
            elif t == "macro_series":
                label = "BLS series page" if "bls.gov" in u else "Census retail trade" if "census.gov" in u else src.get("series_id")
            elif t == "pageviews":
                label = f"Wikimedia pageviews · {src.get('article_title')}"
            elif t == "tags":
                label, u = u, f"{repo}/blob/main/{u}"
            else:
                die(f"tool returned a source of unknown type {t}")
            if u not in seen:
                seen.add(u)
                out.append((label, u))
    return out


def render_steps(rec):
    """Every step in order: model text, then each tool call with its input and an excerpt of what came back."""
    texts = rec.get("text") or []
    calls = rec.get("tool_calls") or []
    out = []
    turns = max(len(texts), 1 + max([c["turn"] for c in calls], default=-1))
    for t in range(turns):
        txt = texts[t] if t < len(texts) else ""
        if txt.strip():
            out.append(f'<div class="step"><div class="step-k">model</div>{excerpt(txt, "prose")}</div>')
        for c in (c for c in calls if c["turn"] == t):
            inp = c["input"]
            body = inp["sql"] if isinstance(inp, dict) and set(inp) == {"sql"} else json.dumps(inp, indent=1)
            err = ' <span class="badge bad">tool error</span>' if c.get("is_error") else ""
            out.append(f'<div class="step"><div class="step-k"><code>{e(c["name"])}</code>{err}</div>'
                       f'{excerpt(body, "code")}<div class="step-k">returned</div>{excerpt(str(c["output"]), "code")}</div>')
    return "".join(out) or '<p class="muted small">No steps recorded.</p>'


def excerpt(text, kind):
    tag = "pre" if kind == "code" else "div"
    cls = ' class="txt"' if kind != "code" else ""
    if len(text) <= EXCERPT_CHARS:
        return f"<{tag}{cls}>{e(text)}</{tag}>"
    return (f"<{tag}{cls}>{e(text[:EXCERPT_CHARS])}…</{tag}><details class=\"full\"><summary>show full</summary>"
            f"<{tag}{cls}>{e(text)}</{tag}></details>")


EA_HEAD = re.compile(r"^## ([ABCD]):", re.M)
EA_ITEM = re.compile(r"^- \*\*(q\d{3}), run (\d+)(?: — (.+?))?\.\*\* (.+)$", re.M)
FIX_RE = re.compile(r"remedy|refinement|\bcould\b|\bwould\b|\bapplies\b", re.I)


CLAUSE_RE = re.compile(r"(?<=[.;])\s+(?=[A-Za-z`])")


def split_entry(text):
    """(what happened, what would fix it) from one error_analysis.md entry, dropping nothing.

    The split falls at the first clause (sentence or ;-part) that states a fix (FIX_RE); everything
    before it is what happened, everything from it on is the fix. Both parts are verbatim slices of
    the entry, so happened + " " + fix is the whole entry."""
    clauses = CLAUSE_RE.split(" ".join(text.split()))
    j = next((i for i, c in enumerate(clauses) if FIX_RE.search(c)), None)
    if not j:
        return None
    return " ".join(clauses[:j]), " ".join(clauses[j:])


def parse_error_analysis(text):
    """setup -> [(qid, run, title, what happened, what would fix it, full entry)] from the '## X:' bullets."""
    heads = list(EA_HEAD.finditer(text))
    if not heads:
        die("docs/error_analysis.md has no '## A:' style setup sections")
    out = {}
    for i, h in enumerate(heads):
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        body = body.split("\n## ")[0]
        for m in EA_ITEM.finditer(body):
            parts = split_entry(m[4])
            if parts is None:
                die(f"docs/error_analysis.md {h[1]} {m[1]} run {m[2]}: can't find separate "
                    "'what happened' and 'what would fix it' text")
            out.setdefault(h[1], []).append((m[1], int(m[2]), m[3], *parts, " ".join(m[4].split())))
    return out


# ---------- checks on the template, prose and output ----------

def template_digits(template):
    text = re.sub(r"<style.*?</style>|<script.*?</script>", "", template, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{\{[A-Z_0-9]+\}\}", " ", text)
    text = re.sub(r"&#?\w+;", " ", text)
    return re.findall(r"\S*\d\S*", text)


def prose_digits(replays):
    """Digits in replays.yaml prose (rules, notes, sentences); question IDs and URLs are data, not copy."""
    bad = []

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                if k not in ("question_id", "runs", "links", "provenance", "hero", "default_replay", "tags", "id"):
                    walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")
        elif isinstance(x, str):
            t = re.sub(r"\bq\d{3}\b|\{[a-z_]+\}", "", x)
            if re.search(r"\d", t):
                bad.append(f"{path}: {x[:60]}")
    walk(replays, "replays.yaml")
    return bad


class _Text(HTMLParser):
    """Visible text, skipping style, script and (optionally) recorded transcripts marked data-verbatim."""
    VOID = {"br", "img", "hr", "meta", "input", "link", "line", "rect", "path", "circle", "wbr"}

    def __init__(self, skip_verbatim):
        super().__init__(convert_charrefs=True)
        self.skip_verbatim, self.depth, self.out = skip_verbatim, 0, []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        if self.depth or tag in ("style", "script") or (self.skip_verbatim and "data-verbatim" in dict(attrs)):
            self.depth += 1

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)


def page_text(page, skip_verbatim=True):
    p = _Text(skip_verbatim)
    p.feed(page)
    return " ".join(p.out)


def banned_words(page):
    text = page_text(page)
    return [w for w in BANNED if re.search(rf"\b{re.escape(w)}\b", text, re.I)]


def external_links(fragment):
    return sorted(set(html.unescape(u) for u in re.findall(r'href="(https?://[^"]+)"', fragment)))


# ---------- build ----------

@dataclass
class Result:
    page: str
    audit: list
    links: dict
    claims: list
    notes: list
    pilot: bool
    values: list = None


VALUE_COLS = ["value", "where_on_page", "question_id", "source_url", "where_in_source", "matches"]
NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])\$?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion))?%?")


def page_values(d):
    """Every source-derived number in the hero, the replays, the tag cards and the failure cards, with the
    verification_log.csv row it comes from where there is one. matches is left empty for a hand check."""
    rows = []
    vlog, questions, r = d["vlog"], d["questions"], d["replays"]
    by_q = {}
    for v in vlog:
        by_q.setdefault(v["question_id"], []).append(v)

    def inputs(qid, where):
        for v in by_q.get(qid, []):
            rows.append([num(float(v["value_seen"])) if v["value_seen"] else "", where, qid, v["source_url"],
                         v["where_in_source"], ""])

    def derived(qid, value, where):
        rows.append([value, where, qid, " ; ".join(dict.fromkeys(v["source_url"] for v in by_q.get(qid, []))),
                     "answer key (eval/questions.yaml), computed from the inputs listed with this question", ""])

    hq = r["hero"]["question_id"]
    q = questions[hq]
    for name, label in ((r["hero"]["trap"], "Hero, trap card (full fiscal year)"),
                        (r["hero"]["minus"], "Hero, correct-answer card (first nine months)")):
        val = q["trap_answers"][name]
        src = [v for v in by_q.get(hq, []) if v["value_seen"] and float(v["value_seen"]) == val]
        if not src:
            die(f"page values: hero value {val} has no verification_log.csv row")
        rows.append([num(val), label, hq, src[0]["source_url"], src[0]["where_in_source"], ""])
    derived(hq, f"{num(q['correct'])} {q['unit']}", "Hero, correct-answer card (fourth quarter)")
    for x in r["replays"]:
        qid = x["question_id"]
        qq = questions[qid]
        derived(qid, f"{num(qq['correct'])} {qq['unit']}", f"Replay {qid}, correct answer")
        inputs(qid, f"Replay {qid}, input to the correct answer")
    tags = d["tags"]
    for c in r["tag_cards"]:
        t = tags[c["id"]]
        rows.append([t["lineage"]["retrieved_on"], f"Tag card {c['id']}, lineage retrieved date", "",
                     t["lineage"].get("url_template") or t["lineage"].get("url") or "",
                     "tags/tags.yaml lineage.retrieved_on (a retrieval date, not a filing value)", ""])
    for st, es in parse_error_analysis(d["error_analysis"]).items():
        for qid, run, _, happened, fix, _ in es:
            for part, text in (("what happened", happened), ("what would fix it", fix)):
                clean = text.replace("`", "")
                for m in NUM_RE.finditer(clean):
                    tok = m.group(0).strip()
                    if re.search(r"\b(?:run|runs)\s*$", clean[:m.start()], re.I):
                        continue  # a run number, not a value
                    raw = tok.replace("$", "").replace(",", "").replace("%", "")
                    mult = 1e6 if "million" in raw else 1e9 if "billion" in raw else 1
                    try:
                        val = float(raw.replace("million", "").replace("billion", "").strip()) * mult
                    except ValueError:
                        continue
                    src = [v for v in by_q.get(qid, []) if v["value_seen"]
                           and abs(float(v["value_seen"]) - val) <= 1e-9 * max(1, abs(val))]
                    where = f"Failure card {st} {qid} run {run}, {part}"
                    qq = questions.get(qid, {})
                    key = {"correct": qq.get("correct"), **(qq.get("trap_answers") or {})}
                    hit = [k for k, kv in key.items() if isinstance(kv, (int, float))
                           and abs(kv - val) <= 0.0005 * max(1, abs(kv))]
                    if not src and hit:
                        rows.append([tok, where, qid, " ; ".join(dict.fromkeys(v["source_url"] for v in by_q.get(qid, []))),
                                     f"answer key (eval/questions.yaml) {hit[0]}, computed from this question's inputs", ""])
                    elif src:
                        rows.append([tok, where, qid, src[0]["source_url"], src[0]["where_in_source"], ""])
                    else:
                        rows.append([tok, where, qid, "", "not an input value: from the recorded transcript, the "
                                     "answer key or the scoring tolerance; check against eval/results and "
                                     "eval/questions.yaml", ""])
    return rows


def build(paths=Paths()):
    ev, template, covered = load(paths)
    bad = template_digits(template)
    if bad:
        die(f"template text contains digits {bad}; numbers must come from the data")
    bad = prose_digits(ev._data["replays"])
    if bad:
        die("replays.yaml prose contains digits: " + "; ".join(bad))
    summary = ev._data["summary"]
    pilot = summary.get("pilot") is True or len(covered) < len(ev._data["questions"])
    page = Page(ev)
    n_traps = len(need(ev._data["replays"], "traps"))
    parts_spec = [(pid, label, list(secs)) for pid, label, secs in PARTS]
    if ev._data["a_raw"] is not None:
        res = next(secs for pid, _, secs in parts_spec if pid == "part-results")
        i = [x[0] for x in res].index("b-vs-c")
        res[i] = (*res[i][:3], EXPLORATORY_IN)
        res.insert(i + 1, EXPLORATORY)
    fmt = lambda name: name.format(n_traps=word(n_traps).capitalize())  # noqa: E731
    parts_spec = [(pid, label, [(sid, fmt(n), q, b) for sid, n, q, b in secs]) for pid, label, secs in parts_spec]
    sections = [x for _, _, secs in parts_spec for x in secs]
    parts, audit, links = {}, [], {}
    banner = '<div class="pilot-banner" role="alert">PILOT DATA — NOT FINAL</div>' if pilot else ""
    for sid, name, question, bridge in sections:
        ev.section = sid
        body = getattr(page, sid.replace("-", "_"))()
        bridge = bridge.format(n_traps=word(n_traps), closing=getattr(page, "closing", ""))
        bridge_html = "" if sid == "next" else f'<p class="bridge">{e(bridge)}</p>'
        parts[sid] = f'<section id="{sid}" aria-label="{e(name)}">{banner}{body}{bridge_html}</section>'
        for u in external_links(body):
            links.setdefault(u, []).append(name)
        audit.append((name, question, ", ".join(sorted(ev.used.get(sid, []))), bridge))
    for name, q, files, bridge in audit:
        if not (name and q and files and bridge):
            die(f"story audit: section '{name}' has an empty cell")
    rail, body = [], []
    for pid, label, secs in parts_spec:
        links_html = "".join(f'<li><a href="#{sid}">{e(name)}</a></li>' for sid, name, _, _ in secs)
        rail.append(f'<li class="rail-part">' + (f'<span class="rail-label">{e(label)}</span>' if label else "")
                    + f'<ol>{links_html}</ol></li>')
        inner = "\n".join(parts[sid] for sid, _, _, _ in secs)
        if label:
            body.append(f'<div class="part" id="{pid}"><h2 class="part-h">{e(label)}</h2>\n{inner}</div>')
        else:
            body.append(f'<div class="part part-foot" id="{pid}">\n{inner}</div>')
    rail = "".join(rail)
    out = template
    fills = {"RAIL": rail, "SECTIONS": "\n".join(body),
             "PILOT": '<div class="pilot-fixed" aria-hidden="true">PILOT DATA — NOT FINAL</div>' if pilot else "",
             "DESCRIPTION": e(f"A small experiment: {len(covered)} restaurant-finance questions, four setups, "
                              f"{', '.join(summary['model'])}."),
             "DEFAULT_REPLAY": e(ev._data["replays"]["default_replay"])}
    for k, v in fills.items():
        if "{{" + k + "}}" not in out:
            die(f"template has no {{{{{k}}}}} placeholder")
        out = out.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        die(f"unfilled placeholders {left}")
    found = banned_words(out)
    if found:
        die(f"page contains banned words {found}")
    if re.search(r'(?:href|src)="(?:/|file:|[A-Za-z]:\\)', out) or str(ROOT) in out:
        die("page contains a local absolute path")
    if re.search(r"<script[^>]+src=|<link[^>]+href=\"http|fetch\(|XMLHttpRequest", out):
        die("page loads an external resource or calls fetch")
    size = len(out.encode())
    if size > MAX_BYTES:
        die(f"page is {size:,} bytes, over the {MAX_BYTES:,} byte limit")
    return Result(out, audit, links, page.claims, page.notes, pilot, page_values(ev._data))


def links_text(links):
    lines = ["# Every distinct external link on docs/index.html, with the section(s) it appears in.",
             "# Generated by report/build_report.py. Open each one by hand.", ""]
    for u in sorted(links):
        lines.append(f"{u}\t{', '.join(dict.fromkeys(links[u]))}")
    return "\n".join(lines) + "\n"


def audit_table(audit):
    rows = [("Section", "Reader question", "Evidence", "Bridge into next section")] + [tuple(a) for a in audit]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * 4]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="build to a temp dir, validate, print the audit")
    args = ap.parse_args(argv)
    paths = Paths()
    try:
        if args.check:
            tmp = Path(tempfile.mkdtemp(prefix="build_report_"))
            paths = replace(paths, out=tmp / "index.html", links=tmp / "links_to_check.txt",
                            values=tmp / "page_values_to_check.csv")
        res = build(paths)
    except BuildError as exc:
        sys.exit(f"build_report: FAILED: {exc}")
    paths.out.parent.mkdir(parents=True, exist_ok=True)
    paths.out.write_text(res.page)
    paths.links.write_text(links_text(res.links))
    with paths.values.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(VALUE_COLS)
        w.writerows(res.values)
    for n in res.notes:
        print(f"warning: {n}")
    if res.pilot:
        print("warning: summary.json is pilot data; every section carries the PILOT DATA banner")
    print("\nStory audit")
    print(audit_table(res.audit))
    print("\nGenerated claim sentences")
    for sec, rule, text in res.claims:
        print(f"- [{sec}] {text}\n    rule: {rule}")
    print(f"\nwrote {rel(paths.out)} ({len(res.page.encode()):,} bytes) and {rel(paths.links)} "
          f"({len(res.links)} links)")


if __name__ == "__main__":
    main()
