import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reconcile import build_history, llm, load_records
from reconcile.llm import check_choice
from reconcile.records import address_key
from reconcile.rules import resolve_field, resolve_last_sale, sales_history

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

    def test_street_type_word_inside_the_name(self):
        self.assertEqual(address_key("1 Parade Road Kelburn"), "1 parade road")
        self.assertEqual(address_key("9 Terrace Rd"), "9 terrace road")

    def test_needs_a_street_number(self):
        self.assertIsNone(address_key("Kelburn Parade"))
        self.assertEqual(address_key("12A Kelburn Pde"), "12a kelburn parade")


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


class SaleTest(unittest.TestCase):
    def sale(self, record_id, recorded_on, date, price):
        return record(record_id, recorded_on, last_sale_date=date, last_sale_price=price)

    def test_date_and_price_come_from_the_same_sale(self):
        records = [self.sale("A", "2025-01-01", "2020-01-01", 500),
                   self.sale("B", "2024-01-01", "2023-01-01", 700),
                   self.sale("C", "2023-01-01", "2020-01-01", 500)]
        result = resolve_last_sale(records)
        self.assertEqual(result["last_sale_date"]["value"], "2023-01-01")
        self.assertEqual(result["last_sale_price"]["value"], 700)

    def test_newer_sale_is_not_a_conflict(self):
        records = [self.sale("C", "2025-07-01", "2012-04-03", 480000),
                   self.sale("V", "2025-04-02", "2025-04-28", 1320000)]
        result = resolve_last_sale(records)
        self.assertEqual(result["last_sale_price"]["value"], 1320000)
        self.assertEqual(result["last_sale_date"]["confidence"], "medium")

    def test_single_source_is_not_high(self):
        result = resolve_field([record("A", "2025-01-01", bedrooms=3)], "bedrooms")
        self.assertEqual(result["confidence"], "medium")

    def test_sales_history_keeps_every_sale(self):
        records = [self.sale("C", "2025-07-01", "2016-11-30", 540000),
                   self.sale("V", "2025-09-12", "2025-09-30", 985000),
                   self.sale("L", "2025-09-01", None, None)]
        history = sales_history(records)
        self.assertEqual([s["date"] for s in history], ["2016-11-30", "2025-09-30"])


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
        self.assertIsNone(check_choice("[192]", [192]))

    def test_accepts_number_sent_as_text_or_float(self):
        self.assertEqual(check_choice('{"value": "192"}', [160, 192])[0], 192)
        self.assertEqual(check_choice('{"value": 192.0}', [160, 192])[0], 192)

    def test_rejects_booleans(self):
        self.assertIsNone(check_choice('{"value": true}', [1, 2]))


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

    def test_failed_call_keeps_rules_and_counts_failure(self):
        result = resolve_field(self.records, "floor_area_m2")
        usage = llm.Usage()
        with mock.patch.object(llm, "chat", side_effect=llm.ModelError("HTTP 401")):
            updated = llm.second_opinion(self.records, "floor_area_m2", result, usage)
        self.assertEqual((updated["value"], updated["decided_by"]), (160, "rules"))
        self.assertEqual(usage.failures, 1)

    def test_unknown_record_ids_are_dropped(self):
        result = resolve_field(self.records, "floor_area_m2")
        reply = json.dumps({"value": 192, "reason": "x", "source_ids": ["V", "Z999"]})
        with mock.patch.object(llm, "chat", return_value=reply):
            updated = llm.second_opinion(self.records, "floor_area_m2", result)
        self.assertEqual(updated["sources"], ["V"])


class EnvFileTest(unittest.TestCase):
    def test_reads_key_and_skips_blanks_and_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text('# comment
TEST_RECONCILE_KEY="abc"
TEST_RECONCILE_EMPTY=
', encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("TEST_RECONCILE_KEY", None)
                llm.load_env_file(path)
                self.assertEqual(os.environ["TEST_RECONCILE_KEY"], "abc")
                self.assertNotIn("TEST_RECONCILE_EMPTY", os.environ)


class SampleDataTest(unittest.TestCase):
    def test_every_record_matches_a_property(self):
        history, unmatched = build_history(load_records(DATA / "records.csv"))
        self.assertEqual(len(history), 8)
        self.assertEqual(unmatched, [])


if __name__ == "__main__":
    unittest.main()
