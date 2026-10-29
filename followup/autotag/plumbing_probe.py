"""Load the evaluation stack on a tags file through autotag_env.install() and print what it loaded,
as JSON: semantics.TAGS, semantics.FUNDAMENTALS, the tags file SHA-256, and the result of
aggregate(fundamentals.total_assets, [CMG], FY2025, sum_over_time). Run in a fresh process.

Run: python followup/autotag/plumbing_probe.py <tags.yaml>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autotag_env  # noqa: E402


def main(path):
    _, semantics, run_eval = autotag_env.install(path)
    out = {
        "tags_path": str(Path(path).resolve()),
        "tags_sha256": autotag_env.sha256(path),
        "results_dir": str(run_eval.RESULTS),
        "TAGS": {k: v.model_dump() for k, v in semantics.TAGS.items()},
        "FUNDAMENTALS": {k: v.id for k, v in semantics.FUNDAMENTALS.items()},
        "total_assets_sum_over_time": semantics.aggregate(
            "fundamentals.total_assets", ["CMG"], "FY2025", "sum_over_time"),
    }
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main(sys.argv[1])
