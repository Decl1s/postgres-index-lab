"""Я проверяю контракт и обработку plan JSON без запущенной БД."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from index_lab.__main__ import main
from index_lab.cluster import LabError, binaries
from index_lab.core import Config, canonical, plan_metrics, summarize
from index_lab.output import publish, verify


def plan(ms=2.0):
    return [{"Execution Time": ms, "Plan": {"Node Type": "Limit", "Shared Hit Blocks": 20,
            "Shared Read Blocks": 2, "Actual Rows": 3, "Plans": [{"Node Type": "Seq Scan", "Shared Hit Blocks": 20}]}}]


def evidence():
    summary = summarize([plan()])
    return {"postgres": "16.x", "sizes": {"table_rows": 1004, "index_bytes": 100},
            "rows_returned": 3, "results_equal": True, "before": summary, "after": summary,
            "result": [{"order_id": 1}], "before_plans": [plan()], "after_plans": [plan()]}


class CoreTests(unittest.TestCase):
    def test_config_boundaries(self):
        Config(1000, 1, 1, 1).validate()
        Config(200000, 100, 1000, 9).validate()

    def test_config_rejects_bad_values(self):
        for values in [dict(rows=999), dict(rows=200001), dict(merchant=0), dict(merchant=101),
                       dict(limit=0), dict(limit=1001), dict(runs=0), dict(runs=10), dict(rows=True), dict(runs=1.5)]:
            with self.subTest(values=values), self.assertRaises(LabError):
                Config(**values).validate()

    def test_plan_metrics_do_not_double_count_buffers(self):
        result = plan_metrics(plan())
        self.assertEqual((result["shared_hit_blocks"], result["shared_read_blocks"]), (20, 2))
        self.assertEqual(result["nodes"], ["Limit", "Seq Scan"])

    def test_index_name_is_reported(self):
        value = plan()
        value[0]["Plan"]["Plans"] = [{"Node Type": "Index Only Scan", "Index Name": "orders_paid_recent"}]
        self.assertEqual(plan_metrics(value)["indexes"], ["orders_paid_recent"])

    def test_summary_reports_all_samples(self):
        result = summarize([plan(9), plan(1), plan(5)])
        self.assertEqual(result["samples"], 3)
        self.assertEqual(result["execution_ms"], {"min": 1, "median": 5, "max": 9})

    def test_summary_rejects_empty_measurement(self):
        with self.assertRaises(LabError):
            summarize([])

    def test_bad_document_shape(self):
        for value in [{}, [], [1], [{}, {}], [{}]]:
            with self.subTest(value=value), self.assertRaises(LabError):
                plan_metrics(value)

    def test_invalid_timings(self):
        for value in [True, "1", -1, math.nan, math.inf]:
            document = plan()
            document[0]["Execution Time"] = value
            with self.subTest(value=value), self.assertRaises(LabError):
                plan_metrics(document)

    def test_invalid_counts(self):
        for field in ["Shared Hit Blocks", "Shared Read Blocks", "Actual Rows"]:
            for value in [True, 1.5, -1]:
                document = plan()
                document[0]["Plan"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(LabError):
                    plan_metrics(document)

    def test_invalid_children(self):
        for value in ["oops", [None], [{"Node Type": 3}]]:
            document = plan()
            document[0]["Plan"]["Plans"] = value
            with self.subTest(value=value), self.assertRaises(LabError):
                plan_metrics(document)

    def test_canonical_dict_order(self):
        self.assertEqual(canonical({"a": 1, "b": 2}), canonical({"b": 2, "a": 1}))
        with self.assertRaises(ValueError):
            canonical({"bad": math.nan})

    def test_publish_and_verify(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "result"
            publish(destination, evidence())
            verify(destination)
            self.assertEqual(len(list(destination.iterdir())), 6)
            self.assertIn("20 / 2", (destination / "REPORT.md").read_text())

    def test_existing_destination_is_preserved(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "result"
            destination.mkdir()
            (destination / "mine").write_text("keep")
            with self.assertRaises(LabError):
                publish(destination, evidence())
            self.assertEqual((destination / "mine").read_text(), "keep")

    def test_existing_lock_is_preserved(self):
        with TemporaryDirectory() as folder:
            lock = Path(folder) / "result.lock"
            lock.write_text("other writer")
            with self.assertRaises(LabError):
                publish(Path(folder) / "result", evidence())
            self.assertEqual(lock.read_text(), "other writer")

    def test_failure_before_rename_cleans_own_staging(self):
        with TemporaryDirectory() as folder:
            with patch("index_lab.output.verify", side_effect=LabError("injected")):
                with self.assertRaises(LabError):
                    publish(Path(folder) / "result", evidence())
            self.assertEqual(list(Path(folder).iterdir()), [])
            publish(Path(folder) / "result", evidence())
            verify(Path(folder) / "result")

    def test_output_corruption_is_detected(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "result"
            publish(destination, evidence())
            (destination / "result.json").write_text("[]")
            with self.assertRaises(LabError):
                verify(destination)

    def test_unexpected_output_is_detected(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "result"
            publish(destination, evidence())
            (destination / "extra").write_text("x")
            with self.assertRaises(LabError):
                verify(destination)

    def test_invalid_manifest_is_detected(self):
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "result"
            publish(destination, evidence())
            (destination / "manifest.json").write_text('{"../other":{}}')
            with self.assertRaises(LabError):
                verify(destination)

    def test_cli_existing_output_does_not_start_database(self):
        with TemporaryDirectory() as folder, patch("index_lab.__main__.experiment") as run:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["demo", "--output", folder]), 2)
            run.assert_not_called()

    def test_cli_invalid_config_does_not_start_database(self):
        with patch("index_lab.__main__.experiment") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["demo", "--rows", "0"]), 2)
            run.assert_not_called()

    def test_missing_binary_fails_early(self):
        with TemporaryDirectory() as folder, self.assertRaises(LabError):
            binaries(Path(folder))


if __name__ == "__main__":
    unittest.main()
