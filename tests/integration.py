"""Я проверяю реальный PostgreSQL отдельно от быстрых unit-тестов."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from index_lab.cluster import LabError, temporary_cluster
from index_lab.core import Config, canonical, experiment
from index_lab.output import publish, verify

BIN = Path(os.environ.get("INDEX_LAB_PG_BIN", "/usr/lib/postgresql/16/bin"))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = experiment(BIN, Config())

    def test_same_ordered_result_before_and_after(self):
        r = self.report
        self.assertTrue(r["results_equal"])
        self.assertEqual(r["rows_returned"], 50)
        self.assertEqual(len({v["order_id"] for v in r["result"]}), 50)
        self.assertEqual(r["result"], sorted(r["result"], key=lambda v: (v["created_at"], v["order_id"]), reverse=True))

    def test_boundaries_and_source_size(self):
        self.assertEqual(self.report["sizes"]["table_rows"], 60004)
        self.assertEqual(self.report["boundary_order_ids"], [60001, 60004])
        self.assertTrue(self.report["sizes"]["tcp_disabled"])
        self.assertGreater(self.report["sizes"]["index_bytes"], 0)

    def test_measurements_are_observations_not_latency_threshold(self):
        for stage in ["before", "after"]:
            self.assertEqual(self.report[stage]["samples"], 5)
            self.assertTrue(all(v["rows"] == 50 for v in self.report[stage]["sample_metrics"]))
        # Я не утверждаю фиксированное ускорение или обязательный узел для любой ОС.
        self.assertEqual(len(self.report["before_plans"]), 5)
        self.assertEqual(len(self.report["after_plans"]), 5)

    def test_real_report_round_trip(self):
        with TemporaryDirectory() as folder:
            publish(Path(folder) / "run", self.report)
            verify(Path(folder) / "run")

    def test_sql_failure_and_environment_do_not_escape_own_cluster(self):
        with patch.dict(os.environ, {"PGHOST": "invalid-host", "PGDATABASE": "never-use-this", "PGOPTIONS": "bad"}):
            with temporary_cluster(BIN) as session:
                self.assertEqual(session.sql("SHOW listen_addresses;"), "")
                with self.assertRaises(LabError):
                    session.sql("SELECT * FROM missing_table;")
                self.assertEqual(session.sql("SELECT 1;"), "1")
                runtime = session.socket_dir.parent
            self.assertFalse(runtime.exists())

    def test_exception_stops_and_removes_own_cluster(self):
        runtime = None
        with self.assertRaisesRegex(RuntimeError, "controlled failure"):
            with temporary_cluster(BIN) as session:
                runtime = session.socket_dir.parent
                raise RuntimeError("controlled failure")
        self.assertFalse(runtime.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
