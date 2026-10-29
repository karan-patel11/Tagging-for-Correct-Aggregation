"""The tagger's fixed prompt prefix: instructions, the tag schema and the interface format rules.

The schema block is generated from the Tag model in src/tags.py and VALID_METHOD_NAMES, so it
carries field names and allowed values only (no example entries from tags/tags.yaml). The prefix is
identical for every tag id and every draft, and is sent with cache_control.
"""
import json
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import tags  # noqa: E402

# Copied from the packet into every draft, never asked of the model (PREREG design decision 3).
COPIED_FIELDS = ("id", "table", "filter")


def _type_text(annotation):
    """Allowed values for one Tag field, read from its annotation."""
    args = typing.get_args(annotation)
    if typing.get_origin(annotation) is typing.Literal:
        return "one of " + ", ".join(json.dumps(a) for a in args)
    if args and type(None) in args:  # Optional[X]
        inner = [a for a in args if a is not type(None)][0]
        return _type_text(inner) + ", or null"
    if annotation is bool:
        return "true or false"
    if annotation is str:
        return "string"
    if annotation is dict:
        return "object"
    if typing.get_origin(annotation) is list:
        return "list"
    raise ValueError(f"no schema text for annotation {annotation!r}")


def schema_block():
    lines = ["Tag schema (every field; extra fields are rejected):"]
    for name, field in tags.Tag.model_fields.items():
        if name in COPIED_FIELDS:
            continue
        text = _type_text(field.annotation)
        if name == "valid_methods":
            text = "list, each item one of " + ", ".join(json.dumps(m) for m in sorted(tags.VALID_METHOD_NAMES))
        lines.append(f"- {name}: {text}{'' if field.is_required() else ' (optional)'}")
    lines.append("Rule: if semantic_type is one of " + ", ".join(sorted(tags.MEASURE_TYPES))
                 + ", then additive_over_entities and additive_over_time must both be set.")
    return "\n".join(lines)


FORMAT_RULES = "\n".join([
    "Interface format rules:",
    "- If an entry has a hierarchy, write it as '<child_grain> -> <parent_col>'.",
    "- lineage.url is the source's URL; lineage.url_template is the source's URL pattern, with "
    "placeholders in {braces}.",
])

INSTRUCTIONS = "\n".join([
    "You draft one semantic tag for one column or metric of a data warehouse. The tag tells an "
    "analytics tool how the values may be aggregated and where they come from.",
    "You get one input packet: the table name, the column or metric name, its data type, sample "
    "rows, simple statistics and the documentation the data vendor provides. Use only the packet.",
    "Return exactly one JSON object and nothing else. Include every schema field below; use null "
    "for a field that does not apply and [] for no valid methods. Do not include id, table or "
    "filter; those are filled in from the packet.",
])


def system_prefix():
    return "\n\n".join([INSTRUCTIONS, schema_block(), FORMAT_RULES])


def user_message(packet):
    return "Input packet:\n" + json.dumps(packet, indent=1, default=str)


if __name__ == "__main__":
    print(system_prefix())
