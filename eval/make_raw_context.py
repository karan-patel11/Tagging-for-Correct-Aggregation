"""Exploratory setup A_raw: write eval/contexts/schema_raw.txt.

Built exactly like schema_only.txt (make_contexts.render_schema: DESCRIBE of every table, as
table, column, type), but from data/warehouse_raw.duckdb (src/build_raw_views.py). Prints the
diff against schema_only.txt and stops unless the only differences are the dropped columns.

Run: python eval/make_raw_context.py
"""

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
from build_raw_views import DROPPED, RAW_DB  # noqa: E402
from make_contexts import OUT, render_schema  # noqa: E402


def main():
    text, _ = render_schema(RAW_DB)
    (OUT / "schema_raw.txt").write_text(text)
    old = (OUT / "schema_only.txt").read_text().splitlines()
    new = text.splitlines()
    diff = list(difflib.unified_diff(old, new, "eval/contexts/schema_only.txt",
                                     "eval/contexts/schema_raw.txt", lineterm="", n=1))
    print("\n".join(diff))
    removed = [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")]
    added = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
    expected = set()
    for line in old:
        if line.startswith("TABLE "):
            table = line.split()[1]
        elif line.strip() and line.split()[0] in DROPPED.get(table, []):
            expected.add(line)
    print(f"\nlines removed: {len(removed)}; lines added: {len(added)}; "
          f"dropped columns expected: {len(expected)}")
    if added or set(removed) != expected or len(removed) != len(expected):
        sys.exit("STOP: schema_raw.txt differs from schema_only.txt by more than the dropped columns")
    print("PASS: the only differences are the dropped columns")


if __name__ == "__main__":
    main()
