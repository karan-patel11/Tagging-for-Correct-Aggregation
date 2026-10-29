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


# ---------- follow-up section (report/followup_section.py) ----------
# Every number is recomputed here from the committed files, independently of followup_section.load().

import re  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
import followup_section as fs  # noqa: E402
import score  # noqa: E402

AUTOTAG = ROOT / "followup" / "autotag"
REPO = yaml.safe_load((ROOT / "report" / "replays.yaml").read_text())["links"]["repo"]


def _last_lines(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["question_id"], r["run"])] = r
    return out


def _scored(path):
    qs = {q["id"]: q for q in yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())}
    runs = _last_lines(path)
    return {k: score.score_run(r, qs[k[0]])["correct"] for k, r in runs.items()}, runs


@pytest.fixture(scope="module")
def built():
    data = fs.load()
    return data, fs.section(data, REPO)


@pytest.fixture(scope="module")
def raw():
    hand, _ = _scored(ROOT / "eval" / "results" / "D.jsonl")
    draft, runs = _scored(AUTOTAG / "results" / "D_autotag.jsonl")
    return {"hand": hand, "draft": draft, "runs": runs,
            "st": json.loads((AUTOTAG / "results" / "score_tags.json").read_text()),
            "replay": json.loads((ROOT / "followup" / "engine_fix" / "replay.json").read_text()),
            "meta": {n: json.loads((AUTOTAG / "drafts" / f"{n}_meta.json").read_text()) for n in fs.DRAFTS}}


def _text(html_):
    import html as h
    return re.sub(r"\s+", " ", h.unescape(re.sub(r"<[^>]+>", " ", html_.split("</style>", 1)[1])))


def test_followup_accuracy_card(built, raw):
    _, sec = built
    h, d = raw["hand"], raw["draft"]
    assert f"{sum(h.values())}/{len(h)} → {sum(d.values())}/{len(d)}" in _text(sec)
    assert (sum(h.values()), sum(d.values()), len(d)) == (124, 62, 126)


def test_followup_silent_card(built, raw):
    # PREREG decision 9's order, applied to every lost draft-1 run.
    silent = 0
    for k, ok in raw["draft"].items():
        r = raw["runs"][k]
        f = r.get("final")
        if ok or not r.get("parsed") or r.get("error") or f.get("refused") is True:
            continue
        numeric = isinstance(f.get("answer"), (int, float)) and not isinstance(f.get("answer"), bool)
        if not numeric and any(tc["is_error"] for tc in r["tool_calls"]):
            continue
        silent += f.get("warning") is not True
    t = _text(built[1])
    assert f"Silent wrong answers on the questions tested {silent} permissive methods not exercised, see below" in t


def test_followup_validator_time_cost_and_replay_cards(built, raw):
    t = _text(built[1])
    st, rp = raw["st"], raw["replay"]
    passing = sum(st["drafts"][n]["m3"]["pass"] for n in fs.DRAFTS)
    dang = [sum(len(v) for v in st["drafts"][n]["m2"].values()) for n in fs.DRAFTS]
    assert f"{passing} of 3" in t and f"dangerous errors per draft: {', '.join(map(str, dang))}" in t
    for i, n in enumerate(fs.DRAFTS, 1):
        m = raw["meta"][n]
        assert f"draft {i}: {m['wall_clock_seconds_this_process'] / 60:.1f} min, ${m['cost_usd']:.2f}" in t
    assert f"{rp['hand']['identical']}/{rp['hand']['calls']} identical" in t


def test_followup_root_causes_sum_to_lost_runs(built, raw):
    data, sec = built
    lost = [k for k, ok in raw["draft"].items() if not ok]
    assert len(lost) == len(raw["draft"]) - sum(raw["draft"].values())
    counts = {g[1]: g[5] for g in data["groups"]}
    assert sum(counts.values()) == len(raw["draft"]) - sum(raw["draft"].values())
    # Recount from the tool outputs, with the priority lineage > hierarchy > reported quarter.
    recount = {"lineage": 0, "hierarchy": 0, "reported": 0, "none": 0}
    for k in lost:
        texts = [json.loads(tc["output"]).get("explanation") or "" for tc in raw["runs"][k]["tool_calls"]
                 if tc["is_error"]]
        if any(t.endswith("lineage has no url") for t in texts):
            recount["lineage"] += 1
        elif any("AttributeError: 'NoneType' object has no attribute 'split'" in t for t in texts):
            recount["hierarchy"] += 1
        elif any(t.startswith("insufficient data: no reported Q ") for t in texts):
            recount["reported"] += 1
        else:
            recount["none"] += 1
    assert counts == {"Tagging judgment: time_rollup on flows": recount["reported"],
                      "Missing source URL in the inputs": recount["lineage"],
                      "Missing hierarchy, and the engine crashed": recount["hierarchy"],
                      "No tag involved": recount["none"]}
    t = _text(sec)
    for label, n in counts.items():
        assert f"{n} {label}" in t
    assert "(input gap, not a model error)" in t


def test_followup_worked_example_quotes_committed_files(built, raw):
    t = _text(built[1])
    d1 = {x["id"]: x for x in yaml.safe_load((AUTOTAG / "drafts" / "draft_1.yaml").read_text())}
    assert "Values are cumulative within the fiscal year." in d1[fs.EXAMPLE_TAG]["description"]
    assert "Values are cumulative within the fiscal year." in t
    assert (d1[fs.EXAMPLE_TAG]["additive_over_time"], d1[fs.EXAMPLE_TAG]["time_rollup"]) == (False, "reported_fy_value")
    assert "additive_over_time: false, time_rollup: reported_fy_value" in t
    assert "additive_over_time: true, time_rollup: sum" in t
    refusals = [json.loads(tc["output"])["explanation"] for (q, _), r in raw["runs"].items() if q == fs.EXAMPLE_Q
                for tc in r["tool_calls"] if tc["is_error"]]
    quoted = built[0]["example"]["refusal"]["text"]
    assert quoted in refusals and quoted in t


def test_followup_verdicts_and_hardening(built, raw):
    t = _text(built[1])
    for f, v in raw["st"]["verdicts"].items():
        assert f"{f} {v['entries_per_draft']['draft_1']} {v['verdict']}" in t
    rp = raw["replay"]
    assert f"Engine exceptions on draft 1's recorded tool calls {rp['draft_1']['old_exceptions']} {rp['draft_1']['new_exceptions']}" in t
    assert f"(permissive pairs and the counterfactual) {rp['permissive']['numbers_before']} {rp['permissive']['numbers_after']}" in t
    assert f"catch {rp['validator']['caught']} of the {rp['validator']['errors']} draft errors" in t
    assert "derived from these same drafts" in t


def test_followup_limits_and_links(built, raw):
    t = _text(built[1])
    assert f"{len(raw['st']['drafts']['draft_1']['m1'])} measures, one domain, one tagging model." in t
    assert f"{max(r for _, r in raw['draft'])} runs per question." in t
    for name in ("RESULTS.md", "REPLAY.md", "PREREG.md", "PREREG_DEVIATIONS.md"):
        assert f">{name}</a>" in built[1]
    assert f"/blob/{built[0]['prereg_commit']}/followup/autotag/PREREG.md" in built[1]


def test_followup_section_has_no_missing_values(built):
    t = _text(built[1])
    assert not re.search(r"\bNone\b|\bnan\b|\bNaN\b|\bnull\b|undefined", t), re.findall(r".{40}(?:None|nan|null).{40}", t)


def test_page_has_the_built_section_and_top_line(built):
    page = (ROOT / "docs" / "index.html").read_text()
    assert fs.top_line() in page and built[1] in page
    assert page.index('<section id="results">') < page.index('<section id="followup">') < page.index('<section id="replays">')


def test_readme_numbers_match_the_data(built, raw):
    readme = (ROOT / "README.md").read_text()
    head = readme[:readme.index("## Main study: detailed results")]
    data, rp = built[0], raw["replay"]
    h, d = raw["hand"], raw["draft"]
    counts = {g[1]: g[5] for g in data["groups"]}
    for s in [f"from {sum(h.values())}/{len(h)} to {sum(d.values())}/{len(d)} correct runs",
              f"None of the {data['lost']} lost runs",
              f"{counts['Tagging judgment: time_rollup on flows']} a tagging judgment",
              f"{counts['Missing source URL in the inputs']} a missing source URL",
              f"{counts['Missing hierarchy, and the engine crashed']} a missing hierarchy",
              f"{counts['No tag involved']} with no tag involved",
              f"from {rp['draft_1']['old_exceptions']} to {rp['draft_1']['new_exceptions']}",
              f"from {rp['permissive']['numbers_before']} to {rp['permissive']['numbers_after']}",
              f"{rp['hand']['calls']} recorded setup D tool calls gave identical outputs for "
              f"{rp['hand']['identical']} of {rp['hand']['calls']}",
              f"All {sum(raw['st']['drafts'][n]['m3']['pass'] for n in fs.DRAFTS)} drafts passed"]:
        assert s in head, s
    costs = sorted(f"${raw['meta'][n]['cost_usd']:.2f}" for n in fs.DRAFTS)
    assert f"{costs[0]}–{costs[-1]}" in head
    assert "TODO: video link" in head
