"""Phase 11: build the three eval contexts (SPEC.md §11.4) and the fact-parity table.

  eval/contexts/schema_only.txt  setup A: DESCRIBE output (table, column, type) for every table
  eval/contexts/tags.txt         setup C: tags/tags.yaml rendered one fact per line
  eval/contexts/prose.txt        setup B: the same facts as tags.txt, one plain sentence per fact
  eval/contexts/fact_parity.csv  fact_id, tags_line, prose_sentence, for checking B against C

A fact is one field of one tag (each lineage sub-field is its own fact); the tag id is the
subject, not a fact. Each prose sentence comes from a fixed template for its field, so prose.txt
states the facts in tags.txt, in the same order, and nothing else. Sentence wording for the
schema fields follows the field meanings in SPEC §8.1.

Reads tags/tags.yaml and data/warehouse.duckdb (read_only). Never reads questions.yaml.

Run: python eval/make_contexts.py
"""

import csv
import sys
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent
TAGS = ROOT / "tags" / "tags.yaml"
DB_PATH = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "eval" / "contexts"


def scalar(v):
    """YAML text for one value, on one line."""
    text = yaml.safe_dump(v, default_flow_style=True, width=10**9, allow_unicode=True).strip()
    return text[:-4].strip() if text.endswith("\n...") else text


def and_list(items):
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def filter_sentence(v):
    if v is None:
        return "It has no row filter."
    (col, val), = v.items()
    if isinstance(val, list):
        return f"Its rows are those where {col} is {' or '.join(map(str, val))}."
    return f"Its rows are those where {col} is {val}."


PERIOD_BASIS = {
    "mixed": "Its period type varies by row; read the period_basis column.",
    "quarterly": "Its values are quarterly.",
    "instant": "Its values are balances at a single date (instant).",
    "daily": "Its values are daily.",
    "monthly": "Its values are monthly.",
}
TIME_ROLLUP = {
    "sum": "A yearly figure is the sum of its periods.",
    "last": "A yearly figure is the last value in the year.",
    "reported_fy_value": "A yearly figure is the reported full-year (FY) value.",
    "mean": "A yearly figure is the mean of its periods.",
    "none": "It has no rule for getting a yearly figure.",
}
SA = {"SA": "It is seasonally adjusted.", "NSA": "It is not seasonally adjusted.",
      "n/a": "Seasonal adjustment does not apply to it."}
COMPARABILITY = {
    "by_definition_id": "Its comparability across companies is set by definition_id.",
    "same_definition": "Its values follow the same definition for every company.",
}

# One sentence template per field. Each takes the field value.
FIELD = {
    "table": lambda v: f"It belongs to the {v} table.",
    "filter": filter_sentence,
    "semantic_type": lambda v: f"Its semantic type is {v}.",
    "unit": lambda v: f"Its unit is {v}.",
    "additive_over_entities": lambda v: ("Its values can be added across companies or brands."
                                         if v else
                                         "Its values cannot be added across companies or brands."),
    "additive_over_time": lambda v: ("Its values can be added across periods." if v else
                                     "Its values cannot be added across periods."),
    "time_rollup": lambda v: TIME_ROLLUP[v],
    "valid_methods": lambda v: (f"The aggregation methods allowed for it are {and_list(v)}."
                                if v else "No aggregation method is allowed for it."),
    "period_basis": lambda v: PERIOD_BASIS[v],
    "derivation": lambda v: f"Derivation: {v}",
    "calendar": lambda v: ("Its periods refer to the fiscal calendar." if v == "fiscal" else
                           "Its periods refer to calendar dates."),
    "seasonal_adjustment": lambda v: SA[v],
    "annualized": lambda v: "It is annualized." if v else "It is not annualized.",
    "entity_grain": lambda v: f"Each row is at the {v} level.",
    "hierarchy": lambda v: f"Its hierarchy goes from {v.replace(' -> ', ' up to ')}.",
    "comparability": lambda v: COMPARABILITY[v],
    "description": lambda v: v,
}
LINEAGE = {
    "source": lambda v: f"Its source is {v}.",
    "url_template": lambda v: f"Its source URL template is {v}",
    "url": lambda v: f"Its source URL is {v}",
    "id_columns": lambda v: f"The {and_list(v)} columns identify the source record.",
    "id_column": lambda v: f"The {v} column identifies the source record.",
    "concept_column": lambda v: f"The {v} column holds the source concept name.",
    "retrieved_on": lambda v: f"It was retrieved on {v}.",
    "dedupe": lambda v: f"Deduplication rule: {v}",
    "file": lambda v: f"Its source file is {v}.",
    "release_date": lambda v: f"Its source release date is {v}.",
    "cross_checked_on": lambda v: f"It was cross-checked on {v}.",
    "inputs_retrieved_on": lambda v: f"Its inputs were retrieved on {v}.",
}


def build_facts(tags):
    """Return [(tag_id, fact_id, tags_line, prose_sentence)] in tags.yaml order."""
    facts = []
    for tag in tags:
        tid = tag["id"]
        for field, value in tag.items():
            if field == "id":
                continue
            if field == "lineage":
                for sub, sv in value.items():
                    if sub not in LINEAGE:
                        sys.exit(f"STOP: no prose template for lineage.{sub} in {tid}")
                    facts.append((tid, f"{tid}#lineage.{sub}", f"    {sub}: {scalar(sv)}",
                                  LINEAGE[sub](sv)))
                continue
            if field not in FIELD:
                sys.exit(f"STOP: no prose template for field {field} in {tid}")
            facts.append((tid, f"{tid}#{field}", f"  {field}: {scalar(value)}", FIELD[field](value)))
    return facts


def render_tags(tags, facts):
    lines, i = [], 0
    for tag in tags:
        lines.append(f"- id: {scalar(tag['id'])}")
        for field in tag:
            if field == "id":
                continue
            if field == "lineage":
                lines.append("  lineage:")
                for _ in tag["lineage"]:
                    lines.append(facts[i][2]); i += 1
            else:
                lines.append(facts[i][2]); i += 1
        lines.append("")
    return "\n".join(lines)


def render_prose(tags, facts):
    lines, i = [], 0
    for tag in tags:
        lines.append(f"{tag['id']}:")
        n = sum(len(v) if k == "lineage" else 1 for k, v in tag.items() if k != "id")
        for _ in range(n):
            lines.append(facts[i][3]); i += 1
        lines.append("")
    return "\n".join(lines)


def render_schema():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    lines = []
    for t in tables:
        lines.append(f"TABLE {t}")
        for name, ctype, *_ in con.execute(f'DESCRIBE "{t}"').fetchall():
            lines.append(f"  {name} {ctype}")
        lines.append("")
    return "\n".join(lines), tables


def main():
    tags = yaml.safe_load(TAGS.read_text())
    facts = build_facts(tags)
    OUT.mkdir(parents=True, exist_ok=True)

    tags_txt = render_tags(tags, facts)
    if yaml.safe_load(tags_txt) != tags:
        sys.exit("STOP: tags.txt does not re-parse to the same data as tags/tags.yaml")
    prose_txt = render_prose(tags, facts)
    schema_txt, tables = render_schema()

    (OUT / "tags.txt").write_text(tags_txt)
    (OUT / "prose.txt").write_text(prose_txt)
    (OUT / "schema_only.txt").write_text(schema_txt)
    with (OUT / "fact_parity.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["fact_id", "tags_line", "prose_sentence"])
        for _, fid, tl, ps in facts:
            w.writerow([fid, tl.strip(), ps])

    n_tag_lines = sum(1 for l in tags_txt.splitlines() if l.startswith("  ") and l.strip() != "lineage:")
    n_prose = sum(1 for l in prose_txt.splitlines() if l and not l.endswith(":"))
    print(f"tags: {len(tags)}; tables in schema_only.txt: {', '.join(tables)}")
    print(f"facts in tags.txt: {n_tag_lines}")
    print(f"facts in prose.txt: {n_prose}")
    print(f"rows in fact_parity.csv: {len(facts)}")
    if not n_tag_lines == n_prose == len(facts):
        sys.exit("STOP: fact counts differ")
    print("tags.txt re-parses to exactly tags/tags.yaml: yes")
    for name in ("schema_only.txt", "tags.txt", "prose.txt"):
        text = (OUT / name).read_text()
        print(f"{name:16s} {len(text):6d} chars  ~{len(text) // 4:5d} tokens (chars/4)")


if __name__ == "__main__":
    main()
