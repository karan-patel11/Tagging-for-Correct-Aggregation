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
