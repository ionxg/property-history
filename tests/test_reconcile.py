import json
import unittest
from pathlib import Path
from unittest import mock

from reconcile import build_history, llm, load_records
from reconcile.llm import check_choice
from reconcile.records import address_key
from reconcile.rules import resolve_field

DATA = Path(__file__).resolve().parent.parent / "data"


def record(record_id, recorded_on, **fields):
    return {"record_id": record_id, "recorded_on": recorded_on, **fields}


class AddressKeyTest(unittest.TestCase):
    def test_abbreviations_and_suburbs(self):
        self.assertEqual(address_key("12 Kelburn Pde"), "12 kelburn parade")
        self.assertEqual(address_key("12 Kelburn Parade, Kelburn"), "12 kelburn parade")
        self.assertEqual(address_key("12 Kelburn Parade Kelburn Wellington"), "12 kelburn parade")

    def test_unit_formats(self):
        self.assertEqual(address_key("Unit 2, 14 Aro St"), "2/14 aro street")
        self.assertEqual(address_key("2/14 Aro Street Aro Valley"), "2/14 aro street")
        self.assertEqual(address_key("Flat 5, 30 The Terrace"), "5/30 the terrace")

    def test_prefix_without_unit_number(self):
        self.assertEqual(address_key("Apt 45 Oriental Pde"), "45 oriental parade")

    def test_no_street_type(self):
        self.assertIsNone(address_key("somewhere in Wellington"))


class RulesTest(unittest.TestCase):
    def test_agreement_is_high(self):
        records = [record("A", "2024-01-01", bedrooms=3), record("B", "2025-01-01", bedrooms=3)]
        self.assertEqual(resolve_field(records, "bedrooms")["confidence"], "high")

    def test_majority_is_medium(self):
        records = [record("A", "2025-06-01", bedrooms=3),
                   record("B", "2024-01-01", bedrooms=4),
                   record("C", "2024-02-01", bedrooms=4)]
        result = resolve_field(records, "bedrooms")
        self.assertEqual((result["value"], result["confidence"]), (4, "medium"))
        self.assertEqual(result["sources"], ["B", "C"])

    def test_tie_takes_newest_and_is_low(self):
        records = [record("A", "2025-06-01", bedrooms=2), record("B", "2023-01-01", bedrooms=3)]
        result = resolve_field(records, "bedrooms")
        self.assertEqual((result["value"], result["confidence"]), (2, "low"))

    def test_missing_values_ignored(self):
        records = [record("A", "2025-06-01", bedrooms=None), record("B", "2023-01-01", bedrooms=3)]
        self.assertEqual(resolve_field(records, "bedrooms")["value"], 3)
        self.assertIsNone(resolve_field([record("A", "2025-06-01", bedrooms=None)], "bedrooms"))


class ModelGuardTest(unittest.TestCase):
    def test_accepts_a_candidate(self):
        reply = json.dumps({"value": 138, "reason": "measured", "source_ids": ["V001"]})
        self.assertEqual(check_choice(reply, [120, 135, 138])[0], 138)

    def test_rejects_invented_value(self):
        reply = json.dumps({"value": 130, "reason": "average", "source_ids": []})
        self.assertIsNone(check_choice(reply, [120, 135, 138]))

    def test_rejects_null_and_bad_json(self):
        self.assertIsNone(check_choice('{"value": null}', [1, 2]))
        self.assertIsNone(check_choice("not json", [1, 2]))


class SecondOpinionTest(unittest.TestCase):
    """The model step, with the API call replaced by a canned reply."""

    records = [record("C", "2025-07-01", floor_area_m2=160),
               record("V", "2025-04-02", floor_area_m2=192)]

    def test_model_answer_replaces_rules(self):
        result = resolve_field(self.records, "floor_area_m2")
        reply = json.dumps({"value": 192, "reason": "measured after extension", "source_ids": ["V"]})
        with mock.patch.object(llm, "chat", return_value=reply):
            updated = llm.second_opinion(self.records, "floor_area_m2", result)
        self.assertEqual((updated["value"], updated["decided_by"]), (192, "model"))

    def test_unusable_answer_keeps_rules(self):
        result = resolve_field(self.records, "floor_area_m2")
        with mock.patch.object(llm, "chat", return_value='{"value": 175}'):
            updated = llm.second_opinion(self.records, "floor_area_m2", result)
        self.assertEqual((updated["value"], updated["decided_by"]), (160, "rules"))


class SampleDataTest(unittest.TestCase):
    def test_every_record_matches_a_property(self):
        history = build_history(load_records(DATA / "records.csv"))
        self.assertEqual(len(history), 8)


if __name__ == "__main__":
    unittest.main()
