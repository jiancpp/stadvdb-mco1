"""Unit tests for etl/etl_pipeline.py. No database connection or writes.

From the project root:
    python -m unittest discover -s tests -p 'test_etl_pipeline.py' -v

Place this file in <project>/tests/test_etl_pipeline.py and keep
<project>/etl/etl_pipeline.py in its existing location.
"""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Replace DB-bound imports BEFORE importing the pipeline module. Its
        # top-level code is now testable without credentials or a database.
        cls.source = MagicMock(name="source_engine")
        cls.warehouse = MagicMock(name="warehouse_engine")
        config = types.ModuleType("config")
        config.IS_ETL_DEVELOPER = "1"
        connections = types.ModuleType("connections")
        connections.source_engine = cls.source
        connections.warehouse_engine = cls.warehouse
        # sqlalchemy.text is only needed as a SQL wrapper in these unit tests.
        sqlalchemy = types.ModuleType("sqlalchemy")
        sqlalchemy.text = lambda sql: sql
        cls.dependency_patch = patch.dict(sys.modules, {
            "config": config, "connections": connections, "sqlalchemy": sqlalchemy,
        })
        cls.dependency_patch.start()
        sys.modules.pop("etl.etl_pipeline", None)
        cls.etl = importlib.import_module("etl.etl_pipeline")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("etl.etl_pipeline", None)
        cls.dependency_patch.stop()

    def setUp(self):
        self.source.reset_mock()
        self.warehouse.reset_mock()
        self.etl.ROW_LIMIT = None
        self.etl.LIMIT_TRIP_ID = None

    def test_batch_boundaries_do_not_repeat_or_skip_ids(self):
        self.assertEqual(list(self.etl.id_ranges(0, 11, step=5)),
                         [(0, 5), (5, 10), (10, 11)])
        self.assertEqual(list(self.etl.id_ranges(10, 10)), [])
        self.assertEqual(list(self.etl.id_ranges(12, 10)), [])
        self.assertEqual(list(self.etl.id_ranges(7, 8)), [(7, 8)])

    def test_source_and_bronze_columns_align(self):
        self.assertEqual(self.etl.BRONZE_COLS[0], "source_trip_id")
        self.assertEqual(self.etl.BRONZE_COLS[1:], self.etl.SRC_COLS[1:])
        self.assertEqual(len(self.etl.BRONZE_COLS), len(self.etl.SRC_COLS))
        self.assertEqual(len(set(self.etl.BRONZE_COLS)), len(self.etl.BRONZE_COLS))

    def test_preflight_passes_when_manifest_matches_source(self):
        conn = self.source.connect.return_value.__enter__.return_value
        conn.execute.side_effect = [MagicMock(fetchall=lambda: []),
                                    MagicMock(scalar=lambda: 30),
                                    MagicMock(scalar=lambda: 30)]
        self.etl.preflight()
        self.assertEqual(conn.execute.call_count, 3)

    def test_preflight_rejects_incomplete_import(self):
        conn = self.source.connect.return_value.__enter__.return_value
        conn.execute.side_effect = [MagicMock(fetchall=lambda: [("bad.parquet", "FAILED", 10, 0)]),
                                    MagicMock(scalar=lambda: 0),
                                    MagicMock(scalar=lambda: 0)]
        with self.assertRaisesRegex(RuntimeError, "Source import incomplete"):
            self.etl.preflight()

    def test_preflight_rejects_count_mismatch(self):
        conn = self.source.connect.return_value.__enter__.return_value
        conn.execute.side_effect = [MagicMock(fetchall=lambda: []),
                                    MagicMock(scalar=lambda: 100),
                                    MagicMock(scalar=lambda: 98)]
        with self.assertRaisesRegex(RuntimeError, "Manifest says 100"):
            self.etl.preflight()

    def test_silver_rejection_rules_present_and_prioritized(self):
        sql = self.etl.SILVER_BATCH_SQL
        reasons = ["missing_timestamp", "pickup_outside_2025",
                   "nonpositive_duration", "dropoff_out_of_range",
                   "excessive_duration", "negative_distance",
                   "excessive_distance", "excessive_speed",
                   "invalid_passengers", "missing_primary_amount",
                   "vendor_out_of_range", "unmapped_vendor",
                   "amount_out_of_range"]
        positions = [sql.index("THEN '" + r + "'") for r in reasons]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("WHERE reject_reason IS NULL", sql)
        self.assertIn("WHERE reject_reason IS NOT NULL", sql)
        self.assertIn("ON CONFLICT (source_trip_id) DO NOTHING", sql)
        self.assertIn("ON CONFLICT (bronze_trip_id) DO NOTHING", sql)

    def test_silver_transformations_and_unknown_code_policy(self):
        sql = self.etl.SILVER_BATCH_SQL
        for fragment in ("COALESCE(ok_ratecode, 99)", "COALESCE(ok_payment, 5)",
                         "ROUND(trip_distance::NUMERIC, 2)",
                         "ROUND(COALESCE(extra, 0)::NUMERIC, 2)",
                         "UPPER(TRIM(store_and_fwd_flag))",
                         "EXTRACT(EPOCH FROM (tpep_dropoff_datetime - tpep_pickup_datetime))"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sql)

    def test_silver_uses_checkpoint_and_insert_in_same_transaction(self):
        self.warehouse.begin.return_value.__enter__.return_value.execute.return_value = MagicMock()
        conn = self.warehouse.connect.return_value.__enter__.return_value
        conn.execute.side_effect = [MagicMock(scalar=lambda: 0),
                                    MagicMock(scalar=lambda: 9)]
        with patch.object(self.etl, "check_silver_reference"), \
             patch.object(self.etl, "load_silver_ref_location"), \
             patch.object(self.etl, "id_ranges", return_value=[(0, 9)]):
            self.etl.transform_silver()
        tx_conn = self.warehouse.begin.return_value.__enter__.return_value
        sqls = [x.args[0] for x in tx_conn.execute.call_args_list]
        self.assertTrue(any("INSERT INTO silver.yellow_taxi_trips" in x for x in sqls))
        self.assertTrue(any("INSERT INTO silver.etl_checkpoints" in x for x in sqls))

    def test_checkpoint_query_defaults_to_zero_if_missing(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 0
        self.assertEqual(self.etl.last_checkpoint(conn, "silver"), 0)
        self.assertEqual(conn.execute.call_args.args[1], {"stage": "silver"})

    def test_gold_facts_map_official_categories_and_unknown_locations(self):
        sql = self.etl.FACT_BATCH_SQL
        for fragment in ("COALESCE(v.vendor_key,    -1)",
                         "COALESCE(pl.location_key, -1)",
                         "COALESCE(dl.location_key, -1)",
                         "p.payment_key", "r.ratecode_key",
                         "ON CONFLICT (bronze_trip_id) DO NOTHING"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sql)
        self.assertNotIn("COALESCE(p.payment_key", sql)
        self.assertNotIn("COALESCE(r.ratecode_key", sql)

    def test_date_and_time_dimensions_cover_expected_ranges(self):
        conn = MagicMock()
        self.etl.load_dim_date(conn)
        self.assertIn("2026-01-01", conn.execute.call_args.args[0])
        conn.reset_mock()
        self.etl.load_dim_time(conn)
        self.assertIn("generate_series(0, 86399)", conn.execute.call_args.args[0])

    def test_ref_lookup_rejects_missing_tables(self):
        with patch.object(self.etl, "scalar", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "ref_providers is empty"):
                self.etl.check_silver_reference()

    def test_ref_lookup_requires_official_unknown_values(self):
        # First three counts are present; ratecode 99 is absent.
        with patch.object(self.etl, "scalar", side_effect=[2, 2, 2, 0]):
            with self.assertRaisesRegex(RuntimeError, "Unknown code 99"):
                self.etl.check_silver_reference()

    def test_reconcile_detects_count_mismatch(self):
        with patch.object(self.etl, "scalar", side_effect=[100, 99, 90, 9, 90]):
            conn = self.warehouse.connect.return_value.__enter__.return_value
            conn.execute.side_effect = [
                MagicMock(scalar=lambda: 0) for _ in range(5)
            ] + [MagicMock(mappings=lambda: MagicMock(all=lambda: [
                {"stage": "silver", "revenue": 5, "distance": 10},
                {"stage": "gold", "revenue": 5, "distance": 10},
            ])), MagicMock(fetchall=lambda: [])]
            with self.assertRaisesRegex(RuntimeError, "source != bronze"):
                self.etl.reconcile()

    def test_run_pipeline_invokes_preflight_only_if_bronze_selected(self):
        with patch.object(self.etl, "preflight") as preflight, \
             patch.dict(self.etl.STEPS, {"silver": MagicMock(), "bronze": MagicMock()}):
            self.etl.run_pipeline(("silver",))
            preflight.assert_not_called()
            self.etl.run_pipeline(("bronze",))
            preflight.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
