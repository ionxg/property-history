"""Reconcile conflicting property records from several sources."""

from . import llm
from .records import address_key, group_by_property, load_records
from .rules import resolve_property


def build_history(records, use_llm=False, usage=None):
    """Resolve every property. Returns {address_key: {field: result}}."""
    groups, _ = group_by_property(records)
    history = {}
    for key, group in sorted(groups.items()):
        resolved = resolve_property(group)
        if use_llm:
            for field, result in resolved.items():
                if result["confidence"] == "low":
                    resolved[field] = llm.second_opinion(group, field, result, usage)
        history[key] = resolved
    return history
