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


# ---------- report/build_report.py (Phase 15a results page) ----------

import copy  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
from dataclasses import replace  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

import build_report as br  # noqa: E402

RESULTS = ROOT / "eval" / "results"


@pytest.fixture(scope="module")
def built():
    return br.build(br.Paths())


def results_copy(tmp_path, summary=None):
    """A results dir with the real transcripts and an optionally edited summary.json."""
    d = tmp_path / "results"
    d.mkdir()
    for s in "ABCD":
        (d / f"{s}.jsonl").symlink_to(RESULTS / f"{s}.jsonl")
    if summary is None:
        shutil.copy(RESULTS / "summary.json", d / "summary.json")
    else:
        (d / "summary.json").write_text(json.dumps(summary))
    return d


def paths_for(tmp_path, **kw):
    return replace(br.Paths(), out=tmp_path / "index.html", links=tmp_path / "links.txt", **kw)


def summary_key_paths(s):
    """Every key the summary carries at the levels the page reads (one sample entry for per-item maps)."""
    out = [(k,) for k in s]
    out += [("setups", k) for k in s["setups"]]
    a = s["setups"]["A"]
    out += [("setups", "A", k) for k in a]
    for k in ("accuracy", "avg_tokens"):
        out += [("setups", "A", k, j) for j in a[k]]
    for k in ("accuracy_by_category", "trap_hits", "per_question"):
        first = sorted(a[k])[0]
        out += [("setups", "A", k, first)] + [("setups", "A", k, first, j) for j in a[k][first]]
    out += [("b_vs_c", k) for k in s["b_vs_c"]]
    out += [("scorer_notes", 0, k) for k in s["scorer_notes"][0]]
    return out


def test_build_succeeds_on_current_results(built):
    assert "<section id=\"problem\"" in built.page and not built.pilot
    assert len(built.audit) == 10 and all(all(row) for row in built.audit)
    assert len(built.page.encode()) < br.MAX_BYTES


def test_missing_summary_key_fails_naming_it(tmp_path):
    real = json.loads((RESULTS / "summary.json").read_text())
    paths = summary_key_paths(real)
    assert len(paths) > 50
    for i, path in enumerate(paths):
        s = copy.deepcopy(real)
        parent = s
        for k in path[:-1]:
            parent = parent[k]
        del parent[path[-1]]
        d = tmp_path / f"k{i}"
        d.mkdir()
        with pytest.raises(br.BuildError) as exc:
            br.build(paths_for(d, results=results_copy(d, s)))
        assert ".".join(map(str, path)) in str(exc.value), (path, str(exc.value))


def test_replay_declaring_trap_where_score_is_correct_fails(tmp_path):
    r = yaml.safe_load((ROOT / "report" / "replays.yaml").read_text())
    q003 = next(x for x in r["replays"] if x["question_id"] == "q003")
    q003["expect"]["A"] = "trap"
    (tmp_path / "replays.yaml").write_text(yaml.safe_dump(r, allow_unicode=True))
    with pytest.raises(br.BuildError, match=r"q003 setup A run 1 is 'trap', but the recorded score is 'correct'"):
        br.build(paths_for(tmp_path, replays=tmp_path / "replays.yaml"))


def test_default_replay_that_A_always_got_right_fails(tmp_path):
    r = yaml.safe_load((ROOT / "report" / "replays.yaml").read_text())
    r["default_replay"] = "q003"
    (tmp_path / "replays.yaml").write_text(yaml.safe_dump(r, allow_unicode=True))
    with pytest.raises(br.BuildError, match="pick a different default_replay"):
        br.build(paths_for(tmp_path, replays=tmp_path / "replays.yaml"))


def test_missing_error_analysis_fails(tmp_path):
    with pytest.raises(br.BuildError, match="missing file .*error_analysis.md"):
        br.build(paths_for(tmp_path, error_analysis=tmp_path / "error_analysis.md"))


def test_pilot_summary_puts_banner_on_every_section(tmp_path):
    s = json.loads((RESULTS / "summary.json").read_text())
    s["pilot"] = True
    res = br.build(paths_for(tmp_path, results=results_copy(tmp_path, s)))
    sections = re.findall(r"<section id=\"[^\"]+\".*?</section>", res.page, re.S)
    assert res.pilot and len(sections) == 10
    for sec in sections:
        assert "PILOT DATA — NOT FINAL" in sec
    assert "pilot-fixed" in res.page


def test_no_typed_digits_in_template_or_prose():
    assert br.template_digits((ROOT / "report" / "template.html").read_text()) == []
    assert br.prose_digits(yaml.safe_load((ROOT / "report" / "replays.yaml").read_text())) == []
    assert br.template_digits("<p>{{X}} and 42 runs</p>") == ["42"]


def test_no_banned_words_in_output(built):
    assert br.banned_words(built.page) == []
    assert br.banned_words("<p>ready for production</p>") == ["production"]
    # recorded transcripts are shown as recorded and are not claims
    assert br.banned_words('<div class="steps" data-verbatim><div>production</div></div>') == []


def test_b_vs_c_verdict_rule():
    below, p = br.b_vs_c_verdict(0, 6)  # p = 2 / 64 = 0.03125
    assert p < 0.05 and below.startswith("C (structured tags) outperformed B") and "6 of 6" in below
    above, p = br.b_vs_c_verdict(0, 5)  # p = 2 / 32 = 0.0625
    assert p > 0.05 and above.startswith("No detectable difference")
    above, p = br.b_vs_c_verdict(1, 7)  # p = 2 * 9 / 256 = 0.0703
    assert p > 0.05 and above.startswith("No detectable difference")
    below, p = br.b_vs_c_verdict(1, 8)  # p = 2 * 10 / 512 = 0.0391
    assert p < 0.05 and "8 of 9" in below
    none, p = br.b_vs_c_verdict(0, 0)
    assert p == 1.0 and "(0 vs 0 discordant questions" in none
    b_better, p = br.b_vs_c_verdict(6, 0)
    assert p < 0.05 and b_better.startswith("B (prose with the same facts) outperformed C")


def test_accuracy_claim_only_calls_non_overlapping_ranges_real():
    same = br.accuracy_claim({"A": (0.9, 0.8, 1.0), "B": (0.95, 0.9, 1.0)})
    assert "overlapping run-to-run ranges" in same and "do not overlap" not in same
    apart = br.accuracy_claim({"A": (0.5, 0.4, 0.6), "B": (0.9, 0.8, 1.0)})
    assert apart.startswith("Run ranges do not overlap for B above A")


def test_perfect_d_adds_coverage_caveat():
    assert br.d_claim((10, 10), (3, 4)).startswith("D's tools were built for these categories")
    assert br.d_claim((9, 10), (3, 4)) is None


def test_transcript_script_tag_is_escaped():
    rec = {"text": ["<script>alert(1)</script>"],
           "tool_calls": [{"turn": 0, "name": "run_sql", "input": {"sql": "<script>x</script>"},
                           "output": "<script>y</script>", "is_error": False}]}
    out = br.render_steps(rec)
    assert "<script>" not in out and out.count("&lt;script&gt;") == 3


def test_rail_and_deep_links_resolve(built):
    page = built.page
    ids = set(re.findall(r'\bid="([^"]+)"', page))
    rail = re.search(r'<nav class="rail".*?</nav>', page, re.S).group(0)
    rail_ids = re.findall(r'href="#([^"?]+)"', rail)
    assert len(rail_ids) == 10 and set(rail_ids) <= ids
    replays = set(re.findall(r'<div class="replay" data-q="([^"]+)"', page))
    deep = re.findall(r'href="#replay\?([^"]+)"', page)
    assert deep
    for d in deep:
        p = dict(kv.split("=") for kv in d.replace("&amp;", "&").split("&"))
        assert p["q"] in replays and p["left"] in "ABCD" and p["right"] in "ABCD", d
    for anchor in re.findall(r'href="#([^"?]+)"', page):
        assert anchor in ids, anchor


# ---------- results-page revision: q017 hero, plain headline, D failures first, verification counts ----------

import csv  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
import score  # noqa: E402


def _section(page, sid):
    m = re.search(rf'<section id="{sid}".*?</section>', page, re.S)
    assert m, sid
    return m.group(0)


def test_hero_is_q017_with_trap_count_read_from_the_jsonl(built):
    q = {x["id"]: x for x in yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())}["q017"]
    hits = n = ok = 0
    for s in "ABCD":
        for line in (RESULTS / f"{s}.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r["question_id"] == "q017":
                sc = score.score_run(r, q)
                n, hits, ok = n + 1, hits + (sc["trap_hit"] == "used_fy_value"), ok + sc["correct"]
    assert hits >= 1
    hero = _section(built.page, "problem")
    text = br.page_text(hero)
    assert f"{hits} of {n} recorded runs on this question fell into this trap" in text
    assert f"The other {n - hits} were correct." in text and ok == n - hits
    assert f"{q['correct']:,}" in text and f"{q['trap_answers']['used_fy_value']:,}" in text
    # both filing links: the full-year 10-K and the nine-month 10-Q
    for acc in ("000094094426000025", "000094094426000009"):
        assert f"https://www.sec.gov/Archives/edgar/data/940944/{acc}/" in hero, acc
    assert "Yum" not in text and "total assets" not in text.lower()


def test_headline_rule():
    few = br.headline_claim("m", {"A": (4, 126), "B": (0, 126), "C": (2, 126), "D": (2, 126)}, 1.0)
    assert few[0] == "With these tables and this model (m), every setup made few errors: 0 to 4 wrong runs out of 126 per setup."
    assert few[1].endswith("showed no detectable difference.")
    assert few[2].startswith("Setup A, with no tags at all, was already 96.8% correct")
    many = br.headline_claim("m", {"A": (40, 126), "B": (0, 126), "C": (2, 126), "D": (2, 126)}, 0.01)
    assert "few errors" not in " ".join(many) and len(many) == 2
    assert "differed (exact sign test, p = 0.01)" in many[1]


def test_headline_on_page_is_generated_from_summary(built):
    s = json.loads((RESULTS / "summary.json").read_text())
    wrong = {x: (v["n"] - v["correct_runs"], v["n"]) for x, v in s["setups"].items()}
    _, p = br.b_vs_c_verdict(len(s["b_vs_c"]["b_right_c_wrong"]), len(s["b_vs_c"]["c_right_b_wrong"]))
    text = br.page_text(_section(built.page, "problem"))
    for sentence in br.headline_claim(", ".join(s["model"]), wrong, p):
        assert sentence in text


def test_failures_section_starts_with_d_breakages(built):
    fails = _section(built.page, "failures")
    groups = re.findall(r'<div class="fail-group"><h3>([ABCD]) ', fails)
    assert groups == ["D", "A", "B", "C"]
    first = fails.split('<div class="fail-group">')[1]
    assert re.findall(r"<b>(q\d{3}), run \d+</b>", first) == ["q030", "q034"]


def test_verification_counts_match_the_two_files():
    log = list(csv.DictReader((ROOT / "eval" / "verification_log.csv").open()))
    ai = {r["input_key"]: r for r in csv.DictReader((ROOT / "eval" / "verification_ai.csv").open())}
    keys = {re.match(r"\[([^\]]+)\]", r["where_in_source"])[1] for r in log}
    hand = {re.match(r"\[([^\]]+)\]", r["where_in_source"])[1] for r in log
            if "hand-read by" in r["notes"] or "hand spot-check by" in r["notes"]}
    sourced = {k for k in keys if ai[k]["status"] != "n/a"}
    v = br.verification_counts(log, list(ai.values()))
    assert (v["inputs"], v["sourced"], v["unsourced"]) == (len(keys), len(sourced), len(keys - sourced))
    assert v["hand"] == len(hand) and v["ai_read"] == sum(ai[k]["matches"] in ("yes", "no") for k in sourced)
    assert v["mismatches"] == sum(ai[k]["matches"] == "no" for k in sourced)
    assert v["revisions"] == sum(r["revision"] not in ("", "none") for r in ai.values())
    assert v["trap_only"] == sum(r["status"] == "trap_only" for r in ai.values())


def test_checks_section_shows_verification_counts_and_scorer_cause(built):
    text = br.page_text(_section(built.page, "checks"))
    log = list(csv.DictReader((ROOT / "eval" / "verification_log.csv").open()))
    ai = list(csv.DictReader((ROOT / "eval" / "verification_ai.csv").open()))
    for sentence in br.verification_claims(br.verification_counts(log, ai)):
        assert sentence in text
    note = json.loads((RESULTS / "summary.json").read_text())["scorer_notes"][0]
    assert "Post-hoc scorer fix" in text and note["description"] in text
    assert "rows by hand against the source; the rest were" not in text  # the old hand-check sentence


def test_logged_input_missing_from_verification_ai_fails(tmp_path):
    rows = list(csv.DictReader((ROOT / "eval" / "verification_ai.csv").open()))
    with (tmp_path / "ai.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(r for r in rows if r["input_key"] != "sec:DRI:revenue:FY:FY2026")
    with pytest.raises(br.BuildError, match="verification_ai.csv has no row for logged inputs"):
        br.build(paths_for(tmp_path, vlog_ai=tmp_path / "ai.csv"))


def test_without_a_raw_next_steps_says_not_run(built):
    assert not (RESULTS / "A_raw.jsonl").exists()
    assert 'id="exploratory"' not in built.page
    assert br.A_RAW_NOT_RUN in br.page_text(_section(built.page, "next"))


def test_with_a_raw_exploratory_section_follows_results(tmp_path):
    d = results_copy(tmp_path)
    (d / "A_raw.jsonl").symlink_to(RESULTS / "A.jsonl")  # identical runs: no discordant questions
    res = br.build(paths_for(tmp_path, results=d))
    ids = re.findall(r'<section id="([^"]+)"', res.page)
    assert ids[ids.index("results") + 1] == "exploratory"
    text = br.page_text(_section(res.page, "exploratory"))
    assert "Exploratory, added after seeing the main results" in text
    assert "No detectable difference between A and A_raw (0 vs 0 discordant questions; exact sign test, p = 1.00)" in text
    assert br.A_RAW_NOT_RUN not in res.page and len(res.audit) == 11


def test_hand_check_labels_disagreeing_between_files_fails(tmp_path):
    rows = list(csv.DictReader((ROOT / "eval" / "verification_ai.csv").open()))
    for r in rows:
        if r["input_key"] == "views:KFC:CY2024Q4":
            r["status"] = "pending"
    with (tmp_path / "ai.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(br.BuildError, match="hand checks disagree"):
        br.build(paths_for(tmp_path, vlog_ai=tmp_path / "ai.csv"))
