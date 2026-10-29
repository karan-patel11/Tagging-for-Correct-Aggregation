"""STEP 5 (M4): setup D, 42 questions x 3 runs, on draft 1, through autotag_env.install().

Reuses eval/run_eval.py's run_one, Budget, load_questions, check_frozen and prefix_tokens unchanged;
only the tags file differs. Runs only if draft 1 passes M3 (PREREG: otherwise the validation
failures are the M4 result). Output goes only to followup/autotag/results/D_autotag.jsonl, with
tags_path and tags_sha256 in every record. Resumes: a (question, run) already written without an API
error is skipped. The cap is the follow-up's costs.COST_CAP_USD, counting what is already spent.

Run in a fresh process: python followup/autotag/run_d.py
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import autotag_env  # noqa: E402
import costs  # noqa: E402

DRAFT_1 = HERE / "drafts" / "draft_1.yaml"
OUT = costs.D_AUTOTAG
SETUP = "D"
RUNS = 3


def main():
    import score_tags  # imports src/tags only; semantics is not imported before install()
    m3 = score_tags.m3(DRAFT_1)
    if not m3["pass"]:
        print("draft_1 fails M3; M4 is not run (PREREG). Failures:")
        print(json.dumps(m3, indent=1))
        sys.exit(3)

    _, semantics, run_eval = autotag_env.install(DRAFT_1)
    out = autotag_env.check_output_path(OUT)
    tags_path = str(DRAFT_1.relative_to(ROOT))
    tags_sha = autotag_env.sha256(DRAFT_1)
    run_eval.check_frozen()

    from dotenv import load_dotenv
    import anthropic
    load_dotenv(ROOT / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set (environment or .env).")
    client = anthropic.Anthropic(api_key=key, base_url=run_eval.API_BASE_URL, max_retries=0)

    qs = run_eval.load_questions()
    n = run_eval.prefix_tokens(client, SETUP)
    cache = n >= run_eval.MIN_CACHEABLE_TOKENS
    print(f"Model {run_eval.MODEL}; tags {tags_path} sha256 {tags_sha}")
    print(f"Setup {SETUP}: fixed prefix {n} tokens -> {'cached' if cache else 'not cached'}")

    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("tags_sha256") != tags_sha:
                    sys.exit(f"{out} holds runs on a different tags file ({r.get('tags_sha256')})")
                if not r.get("error"):
                    done.add((r["question_id"], r["run"]))
    budget = run_eval.Budget(costs.COST_CAP_USD)
    budget.spent = costs.spent_so_far()
    print(f"Spent so far in the follow-up: ${budget.spent:.4f} of ${costs.COST_CAP_USD:.2f}")
    jobs = [(q, r) for r in range(1, RUNS + 1) for q in qs if (q["id"], r) not in done]
    print(f"{len(jobs)} runs to do ({len(done)} already written)")

    out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    with open(out, "a") as f, ThreadPoolExecutor(run_eval.CONCURRENCY) as pool:
        futures = {pool.submit(run_eval.run_one, client, budget, q, SETUP, r, cache): (q["id"], r)
                   for q, r in jobs}
        for fut in as_completed(futures):
            qid, r = futures[fut]
            try:
                rec = fut.result()
            except run_eval.CapReached as e:
                print(f"STOP {qid} run {r}: {e}", flush=True)
                continue
            rec["tags_path"], rec["tags_sha256"] = tags_path, tags_sha
            with lock:
                f.write(json.dumps(rec) + "\n")
                f.flush()
            print(f"{qid} run {r} | ${rec['cost_usd']:.5f} | tools {len(rec['tool_calls'])} | "
                  f"{rec['final_line'] or '(no FINAL line)'}"
                  + (f" | ERROR {rec['error']}" if rec["error"] else "")
                  + f" | total ${budget.spent:.4f}", flush=True)
    if autotag_env.sha256(DRAFT_1) != tags_sha:
        sys.exit("draft_1.yaml changed during the run")
    print(f"done; follow-up spend ${costs.spent_so_far():.4f}"
          + (" (stopped at the cap)" if budget.stopped.is_set() else ""))


if __name__ == "__main__":
    main()
