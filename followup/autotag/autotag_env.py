"""Load the evaluation stack (tags -> semantics -> mcp_server -> run_eval) on an alternate tags file.

eval/run_eval.py puts src/ on sys.path and imports the top-level modules `tags`, `semantics` and
`mcp_server`; semantics.py builds TAGS and FUNDAMENTALS at import from `load_tags()`, whose default
path was bound when the function was defined. So, in a fresh interpreter and before semantics is
imported, the default of that same function object is replaced. Reassigning tags.TAGS_PATH would
have no effect. No protected file is edited.

install() must be the first thing that imports semantics in the process; it refuses otherwise.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PROTECTED_RESULTS = ROOT / "eval" / "results"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install(tags_path):
    """Import the stack with `tags_path` as the tags file. Returns (tags, semantics, run_eval)."""
    tags_path = Path(tags_path).resolve()
    for name in ("semantics", "mcp_server", "run_eval"):
        if name in sys.modules:
            raise RuntimeError(f"{name} is already imported; install() must run in a fresh process")
    for p in (ROOT / "src", ROOT / "eval"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    import tags
    tags.load_tags.__defaults__ = (tags_path,)

    import run_eval  # imports mcp_server, which imports semantics, which calls load_tags()
    import semantics

    # The modules run_eval uses must be the ones just patched, and built from tags_path.
    assert run_eval.mcp_server.semantics is semantics
    assert sys.modules["tags"] is tags
    expected = {t.id: t for t in tags.load_tags(tags_path)}
    if semantics.TAGS != expected:
        raise RuntimeError(f"semantics.TAGS was not built from {tags_path}")
    expected_f = {t.filter["metric"]: t for t in expected.values()
                  if t.table == "fundamentals" and isinstance((t.filter or {}).get("metric"), str)}
    if semantics.FUNDAMENTALS != expected_f:
        raise RuntimeError(f"semantics.FUNDAMENTALS was not built from {tags_path}")

    run_eval.RESULTS = RESULTS  # never eval/results
    return tags, semantics, run_eval


def check_output_path(path):
    """Refuse any output under eval/."""
    path = Path(path).resolve()
    if path.is_relative_to(ROOT / "eval"):
        raise ValueError(f"refusing to write under eval/: {path}")
    return path
