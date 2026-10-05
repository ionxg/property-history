"""Plain rules for settling conflicting values. No AI here.

For each field:
  - every source agrees          -> that value, confidence "high"
  - a clear majority             -> majority value, confidence "medium"
  - no majority (a tie, or all
    different)                   -> value from the most recent record,
                                    confidence "low"

The low-confidence fields are the ones worth a second look, by a person
or by the model in llm.py.
"""

from collections import Counter

from .records import FIELDS


def resolve_field(records, field):
    with_value = [r for r in records if r[field] is not None]
    if not with_value:
        return None

    counts = Counter(r[field] for r in with_value)
    candidates = sorted(counts)
    ranked = counts.most_common()
    top_value, top_count = ranked[0]

    if len(counts) == 1:
        confidence = "high"
        value = top_value
        reason = f"all {len(with_value)} sources agree"
    elif top_count > len(with_value) / 2:
        confidence = "medium"
        value = top_value
        reason = f"{top_count} of {len(with_value)} sources agree"
    else:
        newest = max(with_value, key=lambda r: r["recorded_on"])
        confidence = "low"
        value = newest[field]
        reason = f"no majority; took the most recent record ({newest['record_id']})"

    return {
        "value": value,
        "confidence": confidence,
        "reason": reason,
        "candidates": candidates,
        "sources": [r["record_id"] for r in with_value if r[field] == value],
        "decided_by": "rules",
    }


def resolve_property(records):
    resolved = {}
    for field in FIELDS:
        result = resolve_field(records, field)
        if result is not None:
            resolved[field] = result
    return resolved
