import csv
import tempfile
import unittest
from pathlib import Path

from etl.process_billing_data import build_fact_table, clean_billing_data, load_raw_billing, run_pipeline


FIXTURE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cloud_billing_sample.csv"


class EtlPipelineTest(unittest.TestCase):
    def test_clean_billing_data_flags_unallocated_rows(self) -> None:
        raw = load_raw_billing(FIXTURE)
        cleaned = clean_billing_data(raw)

        self.assertGreater(min(row["cost"] for row in cleaned), 0)
        self.assertEqual(sum(row["is_unallocated"] for row in cleaned), 4)
        self.assertTrue(any(row["environment"] == "unknown" for row in cleaned))

    def test_build_fact_table_has_stable_cost_ids(self) -> None:
        raw = load_raw_billing(FIXTURE)
        fact = build_fact_table(clean_billing_data(raw))

        self.assertEqual(len({row["cost_id"] for row in fact}), len(fact))
        self.assertEqual(fact[0]["cost_id"], 1)
        self.assertTrue({"cost_id", "billing_date", "service", "cost", "is_unallocated"}.issubset(fact[0]))

    def test_run_pipeline_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "processed"
            db_path = output_dir / "cloud_costs.db"

            result = run_pipeline(FIXTURE, output_dir, db_path)

            fact_path = output_dir / "fact_cloud_costs.csv"
            summary_path = output_dir / "executive_summary.csv"
            self.assertTrue(fact_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(db_path.exists())
            self.assertEqual(result["rows_processed"], 30)

            with fact_path.open(newline="") as csv_file:
                fact = list(csv.DictReader(csv_file))
            with summary_path.open(newline="") as csv_file:
                summary = list(csv.DictReader(csv_file))

            total_spend = round(sum(float(row["cost"]) for row in fact), 2)
            self.assertEqual(total_spend, round(float(summary[0]["total_spend"]), 2))
            self.assertGreater(float(summary[0]["forecasted_month_end_spend"]), float(summary[0]["total_spend"]))
            self.assertEqual(result["top_service"], summary[0]["top_service"])


if __name__ == "__main__":
    unittest.main()
