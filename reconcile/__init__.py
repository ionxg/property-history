"""Reconcile conflicting property records from several sources."""

from . import llm
from .records import address_key, group_by_property, load_records
from .rules import resolve_property, sales_history


def resolve_with_model(records, use_llm=False, usage=None):
    """Resolve one property's records, optionally asking the model about low-confidence fields."""
    resolved = resolve_property(records)
    if use_llm:
        for field, result in resolved.items():
            if result["confidence"] == "low":
                resolved[field] = llm.second_opinion(records, field, result, usage)
    return resolved


def build_history(records, use_llm=False, usage=None):
    """Resolve every property. Returns ({address_key: {field: result}}, unmatched records)."""
    groups, unmatched = group_by_property(records)
    history = {key: resolve_with_model(group, use_llm, usage)
               for key, group in sorted(groups.items())}
    return history, unmatched
