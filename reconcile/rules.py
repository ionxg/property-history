"""Plain rules for settling conflicting values. No AI here.

For each physical field (bedrooms, floor area, land area, year built):
  - only one source has it       -> that value, confidence "medium"
  - every source agrees          -> that value, confidence "high"
  - a clear majority             -> majority value, confidence "medium"
  - no majority (a tie, or all
    different)                   -> value from the most recent record,
                                    confidence "low"

Sales are handled differently. A date and a price belong together, so they
are settled as one event: the latest sale date any source reports is the
last sale (a newer sale isn't a disagreement, it's news), and the price is
then settled among the records that report that same sale.

The low-confidence fields are the ones worth a second look, by a person
or by the model in llm.py.
"""

from collections import Counter

PHYSICAL_FIELDS = ["bedrooms", "floor_area_m2", "land_area_m2", "year_built"]


def resolve_field(records, field):
    with_value = [r for r in records if r[field] is not None]
    if not with_value:
        return None

    counts = Counter(r[field] for r in with_value)
    candidates = sorted(counts)
    ranked = counts.most_common()
    top_value, top_count = ranked[0]

    if len(with_value) == 1:
        confidence = "medium"
        value = top_value
        reason = f"only {with_value[0]['record_id']} records it"
    elif len(counts) == 1:
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


def sales_history(records):
    """Every distinct sale the sources mention, oldest first.

    Returns [{"date", "prices": {price: [record ids]}}]. More than one price
    for the same date means the sources disagree about that sale.
    """
    sales = {}
    for r in records:
        if r["last_sale_date"] is None:
            continue
        prices = sales.setdefault(r["last_sale_date"], {})
        if r["last_sale_price"] is not None:
            prices.setdefault(r["last_sale_price"], []).append(r["record_id"])
    return [{"date": date, "prices": sales[date]} for date in sorted(sales)]


def resolve_last_sale(records):
    """Settle last_sale_date and last_sale_price together. Returns a dict of results."""
    with_date = [r for r in records if r["last_sale_date"] is not None]
    if not with_date:
        return {}

    latest = max(r["last_sale_date"] for r in with_date)
    same_sale = [r for r in with_date if r["last_sale_date"] == latest]
    older = sorted({r["record_id"] for r in with_date if r["last_sale_date"] != latest})

    if older:
        verb = "knows" if len(older) == 1 else "know"
        date_reason = f"newest sale reported; {', '.join(older)} only {verb} an earlier sale"
        date_confidence = "medium"
    elif len(with_date) == 1:
        date_reason = f"only {with_date[0]['record_id']} records it"
        date_confidence = "medium"
    else:
        date_reason = f"all {len(with_date)} sources agree"
        date_confidence = "high"

    results = {
        "last_sale_date": {
            "value": latest,
            "confidence": date_confidence,
            "reason": date_reason,
            "candidates": sorted({r["last_sale_date"] for r in with_date}),
            "sources": [r["record_id"] for r in same_sale],
            "decided_by": "rules",
        }
    }
    price = resolve_field(same_sale, "last_sale_price")
    if price is not None:
        price["reason"] += f" (sale of {latest})"
        results["last_sale_price"] = price
    return results


def resolve_property(records):
    resolved = {}
    for field in PHYSICAL_FIELDS:
        result = resolve_field(records, field)
        if result is not None:
            resolved[field] = result
    resolved.update(resolve_last_sale(records))
    return resolved
