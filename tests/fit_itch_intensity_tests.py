#!/usr/bin/env python3

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
