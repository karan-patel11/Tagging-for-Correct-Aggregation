"""Checks for the report helpers (report/analyze_over_warnings.py, report/build_key.py)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "report"))

import analyze_over_warnings as aow  # noqa: E402
import build_key  # noqa: E402


def test_keyword_pattern_matches_filing_metadata_sentence():
    text = "The total is 588.2M.\nCaveat: the six-month row has a filing date in 2026. FINAL: {}"
    sentence, word = aow.matched_sentence(text)
    assert word.lower() == "filing date"
    assert sentence.startswith("Caveat:")


def test_keyword_pattern_ignores_unit_assumption_caveat():
    assert aow.matched_sentence("The table has no unit metadata, so I assumed millions.") == (None, None)


def test_over_warning_counts_match_summary():
    data = json.loads((ROOT / "report" / "over_warning_reasons.json").read_text())
    summary = json.loads((ROOT / "eval" / "results" / "summary.json").read_text())
    for s, v in data["setups"].items():
        assert v["warning_runs"] == summary["setups"][s]["over_warning_runs"]
        assert v["matched"] + v["unmatched"] == v["warning_runs"]


def test_key_expands_id_ranges():
    assert build_key.mentioned_ids("see q022–q024 and q030") == {"q022", "q023", "q024", "q030"}


def test_manual_corrections_are_recorded():
    data = json.loads((ROOT / "report" / "over_warning_reasons.json").read_text())
    overrides = json.loads((ROOT / "report" / "over_warning_overrides.json").read_text())
    assert data["n_manual_corrections"] == len(overrides) == len(data["manual_corrections"])
    for c in data["manual_corrections"]:
        assert c["matched"] != c["keyword_result"]


# ---------- docs/index.html: the problem-first story (report/story.py) ----------

import html  # noqa: E402
import re  # noqa: E402

import yaml  # noqa: E402

PAGE = ROOT / "docs" / "index.html"
FIXTURE = ROOT / "tests" / "fixtures" / "page_numbers_62ea6fe.json"
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def visible_text(page_html):
    t = re.sub(r"<style.*?</style>|<script.*?</script>", " ", page_html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return " ".join(html.unescape(t).split())


def page_numbers(page_html):
    """Every number token in the page's visible text (used to build the fixture from 62ea6fe)."""
    return sorted(set(NUM_RE.findall(visible_text(page_html))))


def _page():
    return PAGE.read_text()


def _above_divider():
    page = _page()
    i = page.index('id="full-detail"')
    return page[:i]


def _story():
    sys.path.insert(0, str(ROOT / "report"))
    import story
    import yaml as _y
    import csv
    import io
    summary = json.loads((ROOT / "eval" / "results" / "summary.json").read_text())
    questions = {q["id"]: q for q in _y.safe_load((ROOT / "eval" / "questions.yaml").read_text())}
    vlog = list(csv.DictReader(io.StringIO((ROOT / "eval" / "verification_log.csv").read_text())))
    replays = _y.safe_load((ROOT / "report" / "replays.yaml").read_text())
    return story.story_data(summary, questions, vlog, replays)


def test_story_numbers_match_sources():
    d = _story()
    summary = json.loads((ROOT / "eval" / "results" / "summary.json").read_text())
    questions = {q["id"]: q for q in yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())}
    replay = json.loads((ROOT / "followup" / "engine_fix" / "replay.json").read_text())
    st = json.loads((ROOT / "followup" / "autotag" / "results" / "score_tags.json").read_text())
    # Main results.
    accs = [summary["setups"][s]["accuracy"]["mean"] for s in "ABCD"]
    assert (d["acc_min"], d["acc_max"]) == (min(accs), max(accs))
    assert d["n_answers"] == sum(summary["setups"][s]["n"] for s in "ABCD")
    assert d["n_questions"] == len(questions)
    # Problem example: Darden fiscal Q4 2026 revenue.
    q = questions["q017"]
    assert d["problem"]["correct"] == q["correct"] == 3718800000
    assert d["problem"]["full_year"] == q["trap_answers"]["used_fy_value"]
    assert d["problem"]["nine_months"] == q["trap_answers"]["used_ytd9_value"]
    # Auto-tag follow-up, counted straight from the jsonl lines (the last line of a run counts).
    recs = {}
    for line in (ROOT / "followup" / "autotag" / "results" / "D_autotag.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            recs[(r["question_id"], r["run"])] = r
    assert d["autotag"]["draft_n"] == len(recs)
    assert d["autotag"]["hand_correct"] == summary["setups"]["D"]["correct_runs"]
    sys.path.insert(0, str(ROOT / "eval"))
    import score
    wrong = [r for (qid, _), r in recs.items() if not score.score_run(r, questions[qid])["correct"]]
    assert d["autotag"]["draft_correct"] == len(recs) - len(wrong) == 62
    assert d["autotag"]["refused"] == sum(1 for r in wrong if r.get("final") and r["final"].get("refused") is True)
    assert d["autotag"]["numeric_wrong"] == sum(
        1 for r in wrong if isinstance((r.get("final") or {}).get("answer"), (int, float)))
    assert d["drafts"]["passed"] == sum(v["m3"]["pass"] for v in st["drafts"].values())
    metas = [json.loads((ROOT / "followup" / "autotag" / "drafts" / f"draft_{i}_meta.json").read_text())
             for i in (1, 2, 3)]
    assert d["drafts"]["min_cost"] == min(m["cost_usd"] for m in metas)
    assert d["drafts"]["max_s"] == max(m["wall_clock_seconds_this_process"] for m in metas)
    # Engine hardening.
    g = d["engine"]
    assert (g["crashes_before"], g["crashes_after"]) == (replay["draft_1"]["old_exceptions"],
                                                         replay["draft_1"]["new_exceptions"])
    assert (g["forbidden_before"], g["forbidden_after"]) == (replay["permissive"]["numbers_before"],
                                                             replay["permissive"]["numbers_after"])
    assert (g["hand_identical"], g["hand_calls"]) == (replay["hand"]["identical"], replay["hand"]["calls"])
    assert (g["rule_caught"], g["rule_errors"]) == (replay["validator"]["caught"], replay["validator"]["errors"])
    # Per-field verdicts.
    assert [v for _, _, v in d["per_field"]] == [v["verdict"] for v in st["verdicts"].values()]


def test_story_numbers_are_on_the_page():
    d = _story()
    text = visible_text(_above_divider())
    for s in [f"${d['problem']['correct']:,}", f"${d['problem']['full_year']:,}",
              f"{d['autotag']['hand_correct']} → {d['autotag']['draft_correct']}",
              f"{d['engine']['crashes_before']} → {d['engine']['crashes_after']}",
              f"{d['engine']['forbidden_before']} → {d['engine']['forbidden_after']}",
              f"{d['engine']['hand_identical']} of {d['engine']['hand_calls']}",
              f"{d['engine']['rule_caught']} of {d['engine']['rule_errors']}"]:
        assert s in text, s


def test_root_cause_groups_sum_to_wrong_runs():
    d = _story()
    a = d["autotag"]
    groups = {c["label"]: c["runs"] for c in d["causes"]}
    assert sum(groups.values()) == a["draft_n"] - a["draft_correct"] == 126 - 62
    assert sorted(groups.values()) == [2, 20, 21, 21]


def test_no_none_or_nan_rendered():
    text = visible_text(_page())
    assert not re.search(r"\bNone\b|\bnan\b|\bNaN\b", text)


def test_no_ids_or_field_names_above_divider():
    upper = re.sub(r"<style.*?</style>|<script.*?</script>", " ", _above_divider(), flags=re.S)
    text = visible_text(upper)
    assert not re.search(r"q\d{3}", upper)
    for word in ["additive_over_time", "time_rollup", "valid_methods", "semantic_type", "setup D"]:
        assert word not in upper, word
    assert "Full detail" in text


def test_story_sentences_are_short():
    """Writing rule: at most 25 words per sentence above the divider. Block elements and run-in bold
    headings end a sentence; quoted texts (the question, the AI's reply) count as one word."""
    upper = re.sub(r"<style.*?</style>|<script.*?</script>|<p class=\"rsrc\">.*?</p>", " ",
                   _above_divider(), flags=re.S)
    upper = re.sub(r"</?(p|li|dd|dt|dl|ol|ul|div|h\d|blockquote|figcaption|nav|b|span)\b[^>]*>", "\n", upper)
    text = html.unescape(re.sub(r"<[^>]+>", " ", upper))
    text = re.sub(r"“[^”]*”", "QUOTE", text)
    for block in text.split("\n"):
        for s in re.split(r"(?<=[.!?;])\s+", " ".join(block.split())):
            assert len(s.split()) <= 25, s


def test_every_number_from_the_previous_page_remains():
    old = json.loads(FIXTURE.read_text())["numbers"]
    new = set(page_numbers(_page()))
    assert [n for n in old if n not in new] == []


def test_readme_summary_numbers_are_on_the_page():
    readme = (ROOT / "README.md").read_text()
    summary = readme.split("## Detailed results")[0]
    page = set(page_numbers(_page()))
    nums = [n for n in NUM_RE.findall(summary) if len(n.strip("%").replace(",", "")) > 1]
    assert nums
    assert [n for n in nums if n not in page] == []
