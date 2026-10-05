"""Loading records and working out which property each one is about."""

import csv
import re
from collections import defaultdict

FIELDS = ["bedrooms", "floor_area_m2", "land_area_m2", "year_built",
          "last_sale_date", "last_sale_price"]

STREET_TYPES = {
    "st": "street", "street": "street",
    "rd": "road", "road": "road",
    "pde": "parade", "parade": "parade",
    "ave": "avenue", "avenue": "avenue",
    "tce": "terrace", "terrace": "terrace",
}

# "Unit 2, 14 Aro St" and "Flat 5, 30 The Terrace" both mean 2/14 and 5/30.
UNIT_PREFIX = re.compile(r"^(?:unit|flat|apt|apartment)\s+(\d+)\s*,?\s+(\d+)\s+")
# "Apt 45 Oriental Pde" with no second number is just number 45.
LONE_PREFIX = re.compile(r"^(?:unit|flat|apt|apartment)\s+")


def address_key(address):
    """Reduce an address to 'number street type', dropping suburb and city.

    '12 Kelburn Pde' and '12 Kelburn Parade, Kelburn' both become
    '12 kelburn parade'. The last street-type word is the one that counts, so
    '1 Parade Road' stays '1 parade road'. Returns None if the address doesn't
    start with a number or has no street type.
    """
    text = address.lower().replace(",", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = UNIT_PREFIX.sub(r"\1/\2 ", text)
    text = LONE_PREFIX.sub("", text)

    words = text.split(" ")
    if not re.fullmatch(r"\d+[a-z]?(?:/\d+[a-z]?)?", words[0]):
        return None
    type_positions = [i for i, word in enumerate(words) if i > 0 and word in STREET_TYPES]
    if not type_positions:
        return None
    i = type_positions[-1]
    return " ".join(words[:i] + [STREET_TYPES[words[i]]])


def parse_value(field, raw):
    raw = raw.strip()
    if not raw:
        return None
    if field == "last_sale_date":
        return raw
    return int(raw)


def load_records(path):
    with open(path, newline="", encoding="utf-8") as f:
        records = []
        for row in csv.DictReader(f):
            for field in FIELDS:
                row[field] = parse_value(field, row[field])
            row["key"] = address_key(row["address"])
            records.append(row)
        return records


def group_by_property(records):
    groups = defaultdict(list)
    unmatched = []
    for record in records:
        if record["key"] is None:
            unmatched.append(record)
        else:
            groups[record["key"]].append(record)
    return dict(groups), unmatched
