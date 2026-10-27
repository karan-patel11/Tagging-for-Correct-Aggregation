"""Phase 12: evaluation harness (SPEC §11.4–11.5).

Runs each question through four setups on claude-haiku-5-5 and writes one JSON line per run to
eval/results/{setup}.jsonl (eval/results/pilot/{setup}.jsonl with --pilot).

  A  schema_only.txt  + run_sql
  B  prose.txt        + run_sql
  C  tags.txt         + run_sql
  D  no context file  + the 4 semantic tools (no SQL); tags reach the model only via describe_column

The base instructions and the FINAL format are identical for all four setups; only the context
file and the tool list differ. Tool names, descriptions and schemas come only from src/tool_specs.py.
D's tools run in-process through mcp_server.call_tool, so they return exactly what the MCP server
returns.

run_sql opens DuckDB with read_only=True, disables file system and extension access (so a query
cannot read eval/questions.yaml or tags/), returns at most 200 rows, returns errors as text, and
interrupts queries after 10 seconds.

The fixed prefix (tools + system) is cached when it reaches the model's minimum cacheable length,
measured with the token-counting endpoint; shorter prefixes are sent without cache_control and are
not padded. Cost is added up after every API call from the usage counts and the published prices
below, with a hard stop at $5: a call is only started when the spend so far, plus a worst-case
reserve for every call in flight, stays under the cap. API errors are retried with backoff; a wrong
answer is never retried.

Reads ANTHROPIC_API_KEY from the environment or .env. Only questions whose verification_log rows all
say matches = yes are run.

Run: python eval/run_eval.py --pilot
     python eval/run_eval.py [--runs 3]
"""

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
import duckdb
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mcp_server  # noqa: E402
from tool_specs import RUN_SQL_SPEC, TOOL_SPECS  # noqa: E402

MODEL = "claude-haiku-5-5"
API_BASE_URL = "https://api.anthropic.com"  # explicit, so an inherited ANTHROPIC_BASE_URL is ignored
MAX_TOOL_TURNS = 10
MAX_TOKENS = 2000
CONCURRENCY = 5
COST_CAP_USD = 5.00
MIN_CACHEABLE_TOKENS = 512  # claude-haiku-5-5, from the prompt caching docs' "Cache limitations"
CACHING_URL = "https://platform.claude.com/docs/en/build-with-claude/prompt-caching"

# USD per million tokens for claude-haiku-5-5, read from PRICING_URL on 2026-10-27 (model pricing
# table). Haiku 5.5 is priced by prompt length: a request whose prompt (input + cache reads + cache
# writes) is over 100,000 tokens pays the higher row. Only the 5-minute cache TTL is used.
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
LONG_PROMPT_TOKENS = 100_000
PRICES = {
    "up_to_100k": {"input": 0.10, "cache_write_5m": 0.125, "cache_read": 0.01, "output": 0.50},
    "over_100k": {"input": 0.50, "cache_write_5m": 0.625, "cache_read": 0.05, "output": 2.50},
}

DB_PATH = ROOT / "data" / "warehouse.duckdb"
CONTEXTS = ROOT / "eval" / "contexts"
QUESTIONS = ROOT / "eval" / "questions.yaml"
VERIFICATION_LOG = ROOT / "eval" / "verification_log.csv"
RESULTS = ROOT / "eval" / "results"

SQL_MAX_ROWS = 200
SQL_TIMEOUT_S = 10

BASE_INSTRUCTIONS = (
    "Answer using only the tools. If the data needed isn't available, say so and set refused to true. "
    "If the answer needs a caveat, set warning to true. End with exactly one line:\n"
    'FINAL: {"answer": number_or_null, "unit": "...", "warning": true_or_false, "refused": true_or_false}'
)
CONTEXT_HEADER = "Database context:\n\n"

SETUPS = {
    "A": {"context": "schema_only.txt", "tools": [RUN_SQL_SPEC]},
    "B": {"context": "prose.txt", "tools": [RUN_SQL_SPEC]},
    "C": {"context": "tags.txt", "tools": [RUN_SQL_SPEC]},
    "D": {"context": None, "tools": TOOL_SPECS},
}

# 5 questions from 5 categories: Yum FY2025 total assets (time_additivity), a combined margin
# (ratios), Darden's derived fiscal Q3 cash flow (ytd_calendar), a CPI change (indices), and CAVA
# comps, which aren't in the data (comparability_unanswerable, refuse).
PILOT_IDS = ["q003", "q007", "q016", "q018", "q038"]

# Worst case for one API call, held back from the cap while the call is in flight: a full-price
# prompt at the 100K threshold plus max_tokens of output at the long-prompt output price.
CALL_RESERVE_USD = (LONG_PROMPT_TOKENS * PRICES["over_100k"]["input"]
                    + MAX_TOKENS * PRICES["over_100k"]["output"]) / 1e6

FINAL_RE = re.compile(r"^\s*FINAL:\s*(\{.*\})\s*$")
FINAL_KEYS = {"answer", "unit", "warning", "refused"}


# ---------- run_sql ----------

_sql_con = None
_sql_lock = threading.Lock()
_tool_lock = threading.Lock()  # semantics.py shares one DuckDB connection; calls are serialized


def _sql_connection():
    global _sql_con
    with _sql_lock:
        if _sql_con is None:
            con = duckdb.connect(str(DB_PATH), read_only=True)
            con.execute("SET enable_external_access = false")
            con.execute("SET lock_configuration = true")
            _sql_con = con
    return _sql_con


def _cell(v):
    return "NULL" if v is None else str(v)


def run_sql(sql):
    """Run one query; return (text, is_error). Never raises."""
    cur = _sql_connection().cursor()
    timer = threading.Timer(SQL_TIMEOUT_S, cur.interrupt)
    timer.start()
    try:
        cur.execute(sql)
        if cur.description is None:
            return "OK (no rows returned)", False
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(SQL_MAX_ROWS + 1)
    except duckdb.InterruptException:
        return f"ERROR: query timed out after {SQL_TIMEOUT_S} seconds", True
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}", True
    finally:
        timer.cancel()
        cur.close()
    lines = ["\t".join(cols)] + ["\t".join(_cell(v) for v in r) for r in rows[:SQL_MAX_ROWS]]
    if len(rows) > SQL_MAX_ROWS:
        lines.append(f"(truncated: showing the first {SQL_MAX_ROWS} rows)")
    elif not rows:
        lines.append("(0 rows)")
    return "\n".join(lines), False


def execute_tool(setup, name, args):
    """Run one tool call for a setup; return (text, is_error)."""
    allowed = [t["name"] for t in SETUPS[setup]["tools"]]
    if name not in allowed:
        return f"ERROR: unknown tool '{name}'; tools are {allowed}", True
    if name == "run_sql":
        sql = (args or {}).get("sql")
        if not isinstance(sql, str):
            return "ERROR: run_sql needs a string argument 'sql'", True
        return run_sql(sql)
    with _tool_lock:
        envelope = mcp_server.call_tool(name, args)
    return json.dumps(envelope), envelope.get("status") == "error"


# ---------- prompts ----------

def system_blocks(setup, cache):
    blocks = [{"type": "text", "text": BASE_INSTRUCTIONS}]
    ctx = SETUPS[setup]["context"]
    if ctx:
        blocks.append({"type": "text", "text": CONTEXT_HEADER + (CONTEXTS / ctx).read_text()})
    if cache:
        blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    return blocks


def prefix_tokens(client, setup):
    """Tokens in the fixed prefix (tools + system), from the token-counting endpoint."""
    probe = [{"role": "user", "content": "."}]
    full = client.messages.count_tokens(model=MODEL, system=system_blocks(setup, False),
                                        tools=SETUPS[setup]["tools"], messages=probe)
    bare = client.messages.count_tokens(model=MODEL, messages=probe)
    return full.input_tokens - bare.input_tokens


# ---------- cost ----------

def call_cost(usage):
    inp = usage.get("input_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    p = PRICES["over_100k" if inp + cw + cr > LONG_PROMPT_TOKENS else "up_to_100k"]
    return (inp * p["input"] + cw * p["cache_write_5m"] + cr * p["cache_read"]
            + usage.get("output_tokens", 0) * p["output"]) / 1e6


class CapReached(Exception):
    pass


class Budget:
    def __init__(self, cap):
        self.cap, self.spent, self.reserved = cap, 0.0, 0.0
        self.lock = threading.Lock()
        self.stopped = threading.Event()

    def reserve(self):
        with self.lock:
            if self.stopped.is_set() or self.spent + self.reserved + CALL_RESERVE_USD > self.cap:
                self.stopped.set()
                raise CapReached(f"cost cap ${self.cap:.2f} reached (spent ${self.spent:.4f})")
            self.reserved += CALL_RESERVE_USD

    def settle(self, cost):
        with self.lock:
            self.reserved -= CALL_RESERVE_USD
            self.spent += cost


# ---------- API calls ----------

RETRY_ATTEMPTS = 6


def _retryable(e):
    if isinstance(e, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return True
    return isinstance(e, anthropic.APIStatusError) and e.status_code >= 500


def create_with_retry(client, budget, **kwargs):
    """One messages.create call, retried with backoff on API errors only. Returns (response, cost)."""
    for attempt in range(RETRY_ATTEMPTS):
        budget.reserve()
        try:
            resp = client.messages.create(**kwargs)
        except Exception as e:
            budget.settle(0.0)  # failed requests return no usage and are not billed
            if not _retryable(e) or attempt == RETRY_ATTEMPTS - 1:
                raise
            wait = min(60.0, 2 ** attempt + random.uniform(0, 1))
            after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
            if after and after.replace(".", "", 1).isdigit():
                wait = max(wait, float(after))
            print(f"  API error ({type(e).__name__}); retry {attempt + 1} in {wait:.1f}s", flush=True)
            time.sleep(wait)
            continue
        usage = resp.usage.model_dump()
        cost = call_cost(usage)
        budget.settle(cost)
        return resp, cost


def parse_final(text):
    """The last FINAL line of the model's last message, as (line, dict or None)."""
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("FINAL:")]
    if not lines:
        return None, None
    m = FINAL_RE.match(lines[-1])
    if not m:
        return lines[-1].strip(), None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return lines[-1].strip(), None
    if not isinstance(obj, dict) or set(obj) != FINAL_KEYS:
        return lines[-1].strip(), None
    return lines[-1].strip(), obj


def run_one(client, budget, q, setup, run, cache):
    t0 = time.time()
    system = system_blocks(setup, cache)
    tools = SETUPS[setup]["tools"]
    messages = [{"role": "user", "content": q["question"]}]
    tokens = defaultdict(int)
    cost, api_calls, tool_calls, turns = 0.0, 0, [], []
    stop_reason, error, last_text = None, None, ""
    try:
        for turn in range(MAX_TOOL_TURNS + 1):
            resp, c = create_with_retry(client, budget, model=MODEL, max_tokens=MAX_TOKENS,
                                        system=system, tools=tools, messages=messages)
            cost += c
            api_calls += 1
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                      "output_tokens"):
                tokens[k] += getattr(resp.usage, k, 0) or 0
            stop_reason = resp.stop_reason
            last_text = "".join(b.text for b in resp.content if b.type == "text")
            turns.append(last_text)
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                break
            if turn == MAX_TOOL_TURNS:
                stop_reason = "tool_turn_limit"
                break
            results = []
            for b in resp.content:
                if b.type != "tool_use":
                    continue
                out, is_err = execute_tool(setup, b.name, b.input)
                tool_calls.append({"turn": turn, "name": b.name, "input": b.input,
                                   "output": out, "is_error": is_err})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out,
                                "is_error": is_err})
            messages.append({"role": "user", "content": results})
    except CapReached:
        raise
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    final_line, final = parse_final(last_text) if stop_reason not in (None, "tool_turn_limit") else (None, None)
    return {
        "question_id": q["id"], "setup": setup, "run": run, "model": MODEL,
        "final": final, "final_line": final_line, "parsed": final is not None,
        "tool_calls": tool_calls, "text": turns, "tokens": dict(tokens),
        "cost_usd": round(cost, 6), "seconds": round(time.time() - t0, 2),
        "api_calls": api_calls, "stop_reason": stop_reason, "cached_prefix": cache, "error": error,
    }


# ---------- driver ----------

def load_questions(ids=None):
    qs = yaml.safe_load(QUESTIONS.read_text())
    rows = defaultdict(list)
    with open(VERIFICATION_LOG, newline="") as f:
        for r in csv.DictReader(f):
            rows[r["question_id"]].append(r["matches"].strip().lower())
    ok = [q for q in qs if rows[q["id"]] and all(m == "yes" for m in rows[q["id"]])]
    skipped = sorted({q["id"] for q in qs} - {q["id"] for q in ok})
    if skipped:
        print(f"Skipping unverified questions: {skipped}")
    if ids:
        missing = [i for i in ids if i not in {q["id"] for q in ok}]
        if missing:
            sys.exit(f"Pilot questions missing or unverified: {missing}")
        ok = [q for q in ok if q["id"] in ids]
    return ok


def check_frozen():
    r = subprocess.run(["git", "diff", "--quiet", "questions-frozen", "--", str(QUESTIONS)], cwd=ROOT)
    if r.returncode != 0:
        sys.exit("eval/questions.yaml differs from the questions-frozen tag (or the tag is missing).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="5 questions x 4 setups x 1 run")
    ap.add_argument("--runs", type=int, default=3, help="runs per question and setup (full run)")
    ap.add_argument("--overwrite", action="store_true", help="replace existing result files")
    args = ap.parse_args()

    check_frozen()
    load_dotenv(ROOT / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set (environment or .env).")
    client = anthropic.Anthropic(api_key=key, base_url=API_BASE_URL, max_retries=0)

    print(f"Model: {MODEL}")
    print(f"Prices (USD per million tokens) from {PRICING_URL}:")
    for tier, p in PRICES.items():
        print(f"  {tier}: " + ", ".join(f"{k} ${v}" for k, v in p.items()))
    print(f"Minimum cacheable prefix: {MIN_CACHEABLE_TOKENS} tokens ({CACHING_URL})")
    print(f"Cost cap: ${COST_CAP_USD:.2f}; per-call reserve ${CALL_RESERVE_USD:.4f}")

    qs = load_questions(PILOT_IDS if args.pilot else None)
    runs = 1 if args.pilot else args.runs
    if args.pilot:
        print(f"Pilot question IDs: {[q['id'] for q in qs]} "
              f"(categories: {[q['category'] for q in qs]})")

    cache = {}
    for s in SETUPS:
        n = prefix_tokens(client, s)
        cache[s] = n >= MIN_CACHEABLE_TOKENS
        print(f"Setup {s}: fixed prefix {n} tokens -> {'cached' if cache[s] else 'not cached (below minimum)'}")

    out_dir = RESULTS / "pilot" if args.pilot else RESULTS
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {s: out_dir / f"{s}.jsonl" for s in SETUPS}
    if not args.pilot and not args.overwrite and any(p.exists() and p.stat().st_size for p in paths.values()):
        sys.exit(f"Result files already exist in {out_dir}; pass --overwrite to replace them.")
    files = {s: open(p, "w") for s, p in paths.items()}
    write_lock = threading.Lock()

    budget = Budget(COST_CAP_USD)
    jobs = [(q, s, r) for r in range(1, runs + 1) for q in qs for s in SETUPS]
    records = []
    print(f"\n{len(jobs)} runs, concurrency {CONCURRENCY}\n")
    with ThreadPoolExecutor(CONCURRENCY) as pool:
        futures = {pool.submit(run_one, client, budget, q, s, r, cache[s]): (q["id"], s, r)
                   for q, s, r in jobs}
        for fut in as_completed(futures):
            qid, s, r = futures[fut]
            try:
                rec = fut.result()
            except CapReached as e:
                print(f"STOP {qid} {s} run {r}: {e}", flush=True)
                continue
            records.append(rec)
            with write_lock:
                files[s].write(json.dumps(rec) + "\n")
                files[s].flush()
            t = rec["tokens"]
            print(f"{qid} {s} run {r} | in {t.get('input_tokens', 0)} cache_w "
                  f"{t.get('cache_creation_input_tokens', 0)} cache_r {t.get('cache_read_input_tokens', 0)} "
                  f"out {t.get('output_tokens', 0)} | ${rec['cost_usd']:.5f} | tools {len(rec['tool_calls'])} "
                  f"| parsed {rec['parsed']} | {rec['final_line'] or '(no FINAL line)'}"
                  + (f" | stop {rec['stop_reason']}" if rec["stop_reason"] != "end_turn" else "")
                  + (f" | ERROR {rec['error']}" if rec["error"] else "")
                  + f" | total ${budget.spent:.4f}", flush=True)
    for f in files.values():
        f.close()

    print(f"\nCompleted {len(records)}/{len(jobs)} runs; spent ${budget.spent:.4f}"
          + (" (stopped at the cost cap)" if budget.stopped.is_set() else ""))
    print(f"Parsed FINAL lines: {sum(r['parsed'] for r in records)}/{len(records)}")
    if args.pilot and records:
        n_q = len(load_questions())
        total = 0.0
        print("\nProjected full-run cost (mean pilot cost per run x questions x 3 runs):")
        for s in SETUPS:
            cs = [r["cost_usd"] for r in records if r["setup"] == s]
            if not cs:
                continue
            proj = sum(cs) / len(cs) * n_q * 3
            total += proj
            print(f"  {s}: ${sum(cs) / len(cs):.5f}/run x {n_q} x 3 = ${proj:.4f}")
        print(f"  total: ${total:.4f} for {n_q * 4 * 3} runs (cap ${COST_CAP_USD:.2f})")


if __name__ == "__main__":
    main()
