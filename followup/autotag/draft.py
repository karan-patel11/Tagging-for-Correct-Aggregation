"""STEP 3: cost check, then the 3 drafts of tags (PREREG.md, Fixed choices).

  --cost-check  Measure the system prefix with the token-counting endpoint (cached only if it
                reaches claude-sonnet-5-5's minimum cacheable length; never padded), count the
                input tokens of all 43 user messages, run one id through the tagger, and extrapolate
                to 3 drafts x 43 ids plus 126 setup D runs (Haiku cost per run from
                eval/results/D.jsonl). Writes results/cost_check.json; exits 2 if the estimate is
                over the $3 cap.
  --draft N     One call per tag id (43), sequential, default sampling settings. Writes the raw
                response of every call to drafts/raw/draft_N/<id>.json and the draft to
                drafts/draft_N.yaml: id, table and filter copied from the packet, every other field
                from the model's JSON object. Writes drafts/draft_N_meta.json (wall-clock time,
                tokens, cost, parse notes). Resumes: an id whose raw file holds a response is not
                called again.

Reads ANTHROPIC_API_KEY from the environment or .env. Refuses to start a call that could take the
follow-up's spend over costs.COST_CAP_USD.

Run: python followup/autotag/draft.py --cost-check
     python followup/autotag/draft.py --draft 1
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import costs  # noqa: E402
import prompt  # noqa: E402
import tags  # noqa: E402  (src/ is on sys.path via prompt)

INPUTS = HERE / "inputs"
DRAFTS = costs.DRAFTS
HAND_D = ROOT / "eval" / "results" / "D.jsonl"
API_BASE_URL = "https://api.anthropic.com"  # explicit, so an inherited ANTHROPIC_BASE_URL is ignored
MAX_TOKENS = 2000
COST_CHECK_ID = "fundamentals.revenue"
N_DRAFTS, N_IDS, N_D_RUNS = 3, 43, 126
# Held back from the cap while a call is in flight: the largest user message (about 5,800
# characters) is far under 20,000 input tokens; plus max_tokens of output.
CALL_RESERVE_USD = (20_000 * costs.TAGGER_PRICES["input"]
                    + MAX_TOKENS * costs.TAGGER_PRICES["output"]) / 1e6
RETRY_ATTEMPTS = 6


def client():
    load_dotenv(ROOT / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set (environment or .env).")
    return anthropic.Anthropic(api_key=key, base_url=API_BASE_URL, max_retries=0)


def packet_ids():
    ids = sorted(p.stem for p in INPUTS.glob("*.json"))
    assert len(ids) == N_IDS, f"expected {N_IDS} packets, found {len(ids)}"
    return ids


def load_packet(tag_id):
    return json.loads((INPUTS / f"{tag_id}.json").read_text())


def system_blocks(cache):
    block = {"type": "text", "text": prompt.system_prefix()}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def prefix_tokens(c):
    probe = [{"role": "user", "content": "."}]
    full = c.messages.count_tokens(model=costs.TAGGER_MODEL, system=system_blocks(False), messages=probe)
    bare = c.messages.count_tokens(model=costs.TAGGER_MODEL, messages=probe)
    return full.input_tokens - bare.input_tokens


def user_tokens(c, tag_id):
    msg = [{"role": "user", "content": prompt.user_message(load_packet(tag_id))}]
    return c.messages.count_tokens(model=costs.TAGGER_MODEL, messages=msg).input_tokens


def _retryable(e):
    if isinstance(e, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return True
    return isinstance(e, anthropic.APIStatusError) and e.status_code >= 500


def call_tagger(c, tag_id, cache):
    """One tagger call. Returns a dict with the raw response, usage, cost and timing."""
    if costs.spent_so_far() + CALL_RESERVE_USD > costs.COST_CAP_USD:
        sys.exit(f"STOP: spend ${costs.spent_so_far():.4f} + reserve ${CALL_RESERVE_USD:.4f} would "
                 f"exceed the ${costs.COST_CAP_USD:.2f} cap")
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = c.messages.create(
                model=costs.TAGGER_MODEL, max_tokens=MAX_TOKENS, system=system_blocks(cache),
                messages=[{"role": "user", "content": prompt.user_message(load_packet(tag_id))}])
            break
        except Exception as e:
            if not _retryable(e) or attempt == RETRY_ATTEMPTS - 1:
                raise
            wait = min(60.0, 2 ** attempt + random.uniform(0, 1))
            print(f"  API error ({type(e).__name__}); retry {attempt + 1} in {wait:.1f}s", flush=True)
            time.sleep(wait)
    usage = resp.usage.model_dump()
    return {"id": tag_id, "model": costs.TAGGER_MODEL, "started_at": started_at,
            "seconds": round(time.time() - t0, 2), "cached_prefix": cache,
            "usage": usage, "cost_usd": round(costs.tagger_cost(usage), 6),
            "stop_reason": resp.stop_reason, "response": resp.model_dump(mode="json")}


def response_text(raw):
    return "".join(b.get("text", "") for b in raw["response"]["content"] if b.get("type") == "text")


def parse_fields(text):
    """The model's JSON object. Returns (obj or None, notes). A ```json fence around the object is
    removed and noted; nothing else is repaired."""
    notes = []
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[-1].strip() == "```":
            s = "\n".join(lines[1:-1]).strip()
            notes.append("code fence removed")
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        return None, notes + [f"not valid JSON: {e}"]
    if not isinstance(obj, dict):
        return None, notes + [f"JSON is a {type(obj).__name__}, not an object"]
    return obj, notes


def build_entry(tag_id, packet, obj):
    """id, table, filter from the packet (PREREG decision 3); the rest from the model, in the Tag
    model's field order, then any keys the schema does not have (load_tags rejects those)."""
    entry = {"id": tag_id, "table": packet["table"], "filter": packet.get("filter")}
    notes = []
    if obj is None:
        return entry, notes
    dropped = [k for k in prompt.COPIED_FIELDS if k in obj]
    if dropped:
        notes.append(f"model returned {dropped}; replaced by the packet's values")
    for k in tags.Tag.model_fields:
        if k not in prompt.COPIED_FIELDS and k in obj:
            entry[k] = obj[k]
    for k in obj:
        if k not in tags.Tag.model_fields:
            entry[k] = obj[k]
    return entry, notes


def hand_d_cost_per_run():
    cs = [json.loads(l)["cost_usd"] for l in HAND_D.read_text().splitlines() if l.strip()]
    return sum(cs) / len(cs), max(cs), len(cs)


def cost_check():
    if costs.COST_CHECK.exists():
        # Its sample call is part of the spend ledger; overwriting it would drop that cost.
        sys.exit(f"{costs.COST_CHECK.relative_to(ROOT)} already exists; the cost check runs once")
    c = client()
    n_prefix = prefix_tokens(c)
    cache = n_prefix >= costs.TAGGER_MIN_CACHEABLE_TOKENS
    print(f"Tagger model: {costs.TAGGER_MODEL}")
    print(f"Prices (USD/MTok, read {costs.PRICES_READ_ON} from {costs.PRICING_URL}): {costs.TAGGER_PRICES}")
    print(f"System prefix: {n_prefix} tokens; minimum cacheable {costs.TAGGER_MIN_CACHEABLE_TOKENS} "
          f"({costs.CACHING_URL}) -> {'cached' if cache else 'sent uncached (below minimum, not padded)'}")

    per_id = {i: user_tokens(c, i) for i in packet_ids()}
    sample = call_tagger(c, COST_CHECK_ID, cache)
    u = sample["usage"]
    print(f"Sample call {COST_CHECK_ID}: input {u['input_tokens']}, cache write "
          f"{u.get('cache_creation_input_tokens') or 0}, cache read {u.get('cache_read_input_tokens') or 0}, "
          f"output {u['output_tokens']} -> ${sample['cost_usd']:.6f}; stop {sample['stop_reason']}")

    # Input per call = prefix + that id's user message, from the token-counting endpoint.
    # Output per call = the sample call's output tokens (an assumption; the bound uses max_tokens).
    p = costs.TAGGER_PRICES
    if cache:
        # Within one draft the first call writes the prefix and the other 42 read it.
        prefix_cost = (n_prefix * p["cache_write_5m"] + (N_IDS - 1) * n_prefix * p["cache_read"]) / 1e6
    else:
        prefix_cost = N_IDS * n_prefix * p["input"] / 1e6
    user_in = sum(per_id.values())
    draft_est = prefix_cost + (user_in * p["input"] + N_IDS * u["output_tokens"] * p["output"]) / 1e6
    draft_bound = prefix_cost + (user_in * p["input"] + N_IDS * MAX_TOKENS * p["output"]) / 1e6
    d_mean, d_max, d_n = hand_d_cost_per_run()
    est = sample["cost_usd"] + N_DRAFTS * draft_est + N_D_RUNS * d_mean
    bound = sample["cost_usd"] + N_DRAFTS * draft_bound + N_D_RUNS * d_max
    out = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "model": costs.TAGGER_MODEL, "prices_usd_per_mtok": costs.TAGGER_PRICES,
        "prices_read_on": costs.PRICES_READ_ON, "pricing_url": costs.PRICING_URL,
        "min_cacheable_tokens": costs.TAGGER_MIN_CACHEABLE_TOKENS, "prefix_tokens": n_prefix,
        "prefix_cached": cache, "user_message_tokens": per_id, "user_message_tokens_total": user_in,
        "sample_call": {k: v for k, v in sample.items() if k != "response"},
        "sample_response_text": response_text(sample),
        "draft_cost_estimate_usd": round(draft_est, 6), "draft_cost_bound_usd": round(draft_bound, 6),
        "hand_d": {"runs": d_n, "mean_cost_per_run_usd": round(d_mean, 6),
                   "max_cost_per_run_usd": round(d_max, 6)},
        "total_estimate_usd": round(est, 6), "total_bound_usd": round(bound, 6),
        "cap_usd": costs.COST_CAP_USD, "over_cap": est > costs.COST_CAP_USD,
    }
    costs.COST_CHECK.parent.mkdir(parents=True, exist_ok=True)
    costs.COST_CHECK.write_text(json.dumps(out, indent=1) + "\n")
    print(f"User messages: {user_in} input tokens over {N_IDS} ids")
    print(f"Per draft: estimate ${draft_est:.4f} (sample output tokens per call), "
          f"bound ${draft_bound:.4f} ({MAX_TOKENS} output tokens per call)")
    print(f"Setup D: {N_D_RUNS} x ${d_mean:.6f} mean (max ${d_max:.6f}) from {HAND_D.relative_to(ROOT)}")
    print(f"TOTAL estimate ${est:.4f} (bound ${bound:.4f}); cap ${costs.COST_CAP_USD:.2f}")
    if est > costs.COST_CAP_USD:
        print("STOP: estimated total over the cap")
        sys.exit(2)


def draft(n):
    c = client()
    n_prefix = prefix_tokens(c)
    cache = n_prefix >= costs.TAGGER_MIN_CACHEABLE_TOKENS
    raw_dir = DRAFTS / "raw" / f"draft_{n}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"draft_{n}: prefix {n_prefix} tokens -> {'cached' if cache else 'uncached'}")
    t_start = time.time()
    for tag_id in packet_ids():
        path = raw_dir / f"{tag_id}.json"
        if path.exists():
            continue
        raw = call_tagger(c, tag_id, cache)
        path.write_text(json.dumps(raw, indent=1) + "\n")
        u = raw["usage"]
        print(f"  {tag_id}: in {u['input_tokens']} cw {u.get('cache_creation_input_tokens') or 0} "
              f"cr {u.get('cache_read_input_tokens') or 0} out {u['output_tokens']} "
              f"${raw['cost_usd']:.5f} {raw['seconds']}s {raw['stop_reason']} | "
              f"spent ${costs.spent_so_far():.4f}", flush=True)
    wall = round(time.time() - t_start, 2)

    entries, notes, tokens, cost, secs = [], {}, {}, 0.0, 0.0
    for tag_id in packet_ids():
        raw = json.loads((raw_dir / f"{tag_id}.json").read_text())
        obj, n1 = parse_fields(response_text(raw))
        entry, n2 = build_entry(tag_id, load_packet(tag_id), obj)
        entries.append(entry)
        if n1 + n2 or raw["stop_reason"] != "end_turn":
            notes[tag_id] = n1 + n2 + ([f"stop_reason {raw['stop_reason']}"]
                                       if raw["stop_reason"] != "end_turn" else [])
        for k, v in raw["usage"].items():
            if isinstance(v, int):
                tokens[k] = tokens.get(k, 0) + v
        cost += raw["cost_usd"]
        secs += raw["seconds"]
    out = DRAFTS / f"draft_{n}.yaml"
    out.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True))
    meta = {"draft": n, "model": costs.TAGGER_MODEL, "ids": len(entries), "prefix_tokens": n_prefix,
            "prefix_cached": cache, "wall_clock_seconds_this_process": wall,
            "sum_call_seconds": round(secs, 2), "tokens": tokens, "cost_usd": round(cost, 6),
            "parse_notes": notes,
            "unparsed_ids": sorted(k for k, v in notes.items() if any("not valid JSON" in x
                                                                      or "not an object" in x for x in v))}
    (DRAFTS / f"draft_{n}_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"wrote {out.relative_to(ROOT)}: {len(entries)} entries, ${cost:.4f}, {secs:.0f}s of calls, "
          f"unparsed {meta['unparsed_ids']}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cost-check", action="store_true")
    g.add_argument("--draft", type=int, choices=[1, 2, 3])
    args = ap.parse_args()
    if args.cost_check:
        cost_check()
    else:
        if not costs.COST_CHECK.exists():
            sys.exit("run --cost-check first")
        if json.loads(costs.COST_CHECK.read_text())["over_cap"]:
            sys.exit("STOP: the cost check estimated a total over the cap")
        draft(args.draft)


if __name__ == "__main__":
    main()
