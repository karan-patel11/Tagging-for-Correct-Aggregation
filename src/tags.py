"""Tag model, loader and database cross-check (SPEC §8).

load_tags() validates every entry in tags/tags.yaml. check_tags_against_db() opens the warehouse
read-only and confirms each tag points at something that exists and that every non-dimension
fundamentals metric (and macro series) has a tag.
"""
from pathlib import Path
from typing import Literal, Optional

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ROOT = Path(__file__).resolve().parent.parent
TAGS_PATH = ROOT / "tags" / "tags.yaml"
DB_PATH = ROOT / "data" / "warehouse.duckdb"

# Method names from SPEC §9.3.
VALID_METHOD_NAMES = {
    "last", "sum_over_time", "sum_across_entities", "ratio_of_sums",
    "pct_change", "mean_over_time", "rollup_to_parent",
}
MEASURE_TYPES = {"flow", "stock", "ratio", "per_share", "index", "count"}


class Tag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    table: str
    filter: Optional[dict] = None
    semantic_type: Literal["flow", "stock", "ratio", "per_share", "index", "count", "identifier", "dimension"]
    unit: Optional[str] = None
    additive_over_entities: Optional[bool] = None
    additive_over_time: Optional[bool] = None
    time_rollup: Optional[Literal["sum", "last", "reported_fy_value", "mean", "none"]] = None
    valid_methods: list[str] = []
    period_basis: Optional[Literal["quarterly", "mixed", "instant", "daily", "monthly"]] = None
    derivation: Optional[str] = None
    calendar: Optional[Literal["fiscal", "calendar"]] = None
    seasonal_adjustment: Optional[Literal["SA", "NSA", "n/a"]] = None
    annualized: Optional[bool] = None
    entity_grain: Optional[str] = None
    hierarchy: Optional[str] = None
    comparability: Optional[Literal["same_definition", "by_definition_id"]] = None
    lineage: dict
    description: str

    @field_validator("valid_methods")
    @classmethod
    def _methods_known(cls, v):
        bad = [m for m in v if m not in VALID_METHOD_NAMES]
        if bad:
            raise ValueError(f"unknown valid_methods {bad}; allowed: {sorted(VALID_METHOD_NAMES)}")
        return v

    @model_validator(mode="after")
    def _measures_need_additivity(self):
        if self.semantic_type in MEASURE_TYPES:
            missing = [f for f in ("additive_over_entities", "additive_over_time") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"{self.id}: semantic_type {self.semantic_type} requires {missing} to be set")
        return self


def load_tags(path=TAGS_PATH) -> list[Tag]:
    """Validate every entry in the YAML file. Raises on any bad entry or duplicate id."""
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a top-level list of tag entries")
    tags = [Tag(**entry) for entry in raw]
    seen, dupes = set(), set()
    for t in tags:
        (dupes if t.id in seen else seen).add(t.id)
    if dupes:
        raise ValueError(f"duplicate tag ids: {sorted(dupes)}")
    return tags


def _filter_values(value):
    return value if isinstance(value, list) else [value]


def check_tags_against_db(tags, db_path=DB_PATH) -> list[str]:
    """Return a list of problems (empty if clean). Opens the database read-only."""
    problems = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        existing = {r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()}
        for t in tags:
            if t.table not in existing:
                problems.append(f"{t.id}: table '{t.table}' not in database")
                continue
            columns = {r[0] for r in con.execute(f"describe {t.table}").fetchall()}
            for col, val in (t.filter or {}).items():
                if col not in columns:
                    problems.append(f"{t.id}: filter column '{col}' not in table {t.table}")
                    continue
                present = {r[0] for r in con.execute(f"select distinct {col} from {t.table}").fetchall()}
                for v in _filter_values(val):
                    if v not in present:
                        problems.append(f"{t.id}: filter value {col}={v!r} not found in {t.table}")

        # Every stored fundamentals metric and macro series must be tagged.
        for table, col in (("fundamentals", "metric"), ("macro_monthly", "series_id")):
            stored = {r[0] for r in con.execute(f"select distinct {col} from {table}").fetchall()}
            # Only a single-value filter tags a stored metric; a list filter marks a derived tag.
            tagged = {
                (t.filter or {}).get(col)
                for t in tags
                if t.table == table and t.semantic_type not in ("dimension", "identifier")
                and isinstance((t.filter or {}).get(col), str)
            }
            for m in sorted(stored - tagged):
                problems.append(f"{table}.{col}={m!r} is stored but has no tag")
    finally:
        con.close()
    return problems


def main():
    tags = load_tags()
    problems = check_tags_against_db(tags)
    print(f"{len(tags)} tags validated")
    for p in problems:
        print("PROBLEM:", p)
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
