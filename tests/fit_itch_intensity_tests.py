#!/usr/bin/env python3

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "fit_itch_intensity.py"
SPEC = importlib.util.spec_from_file_location("fit_itch_intensity", MODULE_PATH)
fit_itch_intensity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fit_itch_intensity)


class FitItchIntensityTests(unittest.TestCase):
    def test_bucket_inclusion_excludes_sparse_and_maintenance_buckets(self):
        included = fit_itch_intensity.Bucket(0.0, 1.0, 50, 2, False)
        sparse = fit_itch_intensity.Bucket(1.0, 2.0, 49, 0, False)
        maintenance = fit_itch_intensity.Bucket(2.0, 3.0, 200, 0, True)

        self.assertEqual((True, "included"), fit_itch_intensity.include_bucket(included, 50))
        self.assertEqual((False, "sparse"), fit_itch_intensity.include_bucket(sparse, 50))
        self.assertEqual((False, "maintenance"), fit_itch_intensity.include_bucket(maintenance, 50))

    def test_exponential_fit_recovers_positive_decay_from_ordered_buckets(self):
        buckets = [
            fit_itch_intensity.Bucket(0.0, 1.0, 1000, 80, False),
            fit_itch_intensity.Bucket(1.0, 2.0, 1000, 45, False),
            fit_itch_intensity.Bucket(2.0, 3.0, 1000, 25, False),
            fit_itch_intensity.Bucket(3.0, 4.0, 1000, 15, False),
        ]

        fit = fit_itch_intensity.fit_exponential(buckets)

        self.assertGreater(fit.decay_per_cent, 0.1)
        self.assertLess(fit.decay_per_cent, 1.0)
        self.assertGreater(fit.base_probability, 0.05)
        self.assertLess(fit.base_probability, 0.2)
        self.assertGreater(fit.mcfadden_pseudo_r2, 0.0)
        self.assertGreater(fit.likelihood_ratio_statistic, 0.0)
        self.assertEqual(1, fit.likelihood_ratio_degrees_of_freedom)
        self.assertGreater(fit.likelihood_ratio_p_value, 0.0)
        self.assertLess(fit.likelihood_ratio_p_value, 1.0)
        self.assertGreater(fit.decay_standard_error, 0.0)
        self.assertLess(fit.decay_ci_95_lower, fit.decay_per_cent)
        self.assertGreater(fit.decay_ci_95_upper, fit.decay_per_cent)

    def test_parity_diagnostics_use_raw_segment_prices_and_mids(self):
        buckets = [
            fit_itch_intensity.Bucket(3.0, 4.0, 100, 3, False),
            fit_itch_intensity.Bucket(4.0, 5.0, 100, 1, False),
        ]
        segments = [
            fit_itch_intensity.Segment(3.0, 3.5, 100.00, 100.035, 1),
            fit_itch_intensity.Segment(3.0, 3.5, 100.00, 100.035, 0),
            fit_itch_intensity.Segment(4.0, 4.5, 100.00, 100.045, 0),
        ]
        fit = fit_itch_intensity.FitResult(
            base_probability=0.10,
            decay_per_cent=0.20,
            negative_log_likelihood=1.0,
            null_negative_log_likelihood=2.0,
            mcfadden_pseudo_r2=0.1,
            weighted_brier_score=0.01,
            weighted_rmse=0.02,
            likelihood_ratio_statistic=2.0,
            likelihood_ratio_degrees_of_freedom=1,
            likelihood_ratio_p_value=0.1,
            decay_standard_error=0.01,
            decay_ci_95_lower=0.18,
            decay_ci_95_upper=0.22,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parity.csv"
            fit_itch_intensity.write_parity_diagnostics(path, buckets, segments, fit, 50)
            rows = path.read_text().splitlines()

        self.assertIn("whole_cent_price_share", rows[0])
        self.assertIn("3,3.5,odd,2,1", rows[1])
        self.assertIn("1,1,1,3.5,1", rows[1])


if __name__ == "__main__":
    unittest.main()
