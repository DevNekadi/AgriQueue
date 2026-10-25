"""
AgriQueue - Automated Unit Tests for Machine Learning Waiting-Time Prediction
"""

import os
import unittest
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml_model import (
    build_pipeline,
    build_baseline_pipeline,
    evaluate_model,
    load_trained_model,
    rule_based_fallback_wait,
    ALL_FEATURES
)
from train_model import generate_synthetic_procurement_dataset
from prediction_service import predict_waiting_time_for_booking
from database import get_direct_connection, init_db, seed_demo_data
import tempfile


class PredictionsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        init_db(db_path=self.db_path)
        seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_synthetic_dataset_generation_properties(self):
        """Verify synthetic dataset contains all required features and valid targets."""
        df = generate_synthetic_procurement_dataset(n_samples=200, random_seed=99)
        self.assertEqual(len(df), 200)
        for feat in ALL_FEATURES:
            self.assertIn(feat, df.columns)
        self.assertIn("waiting_time_minutes", df.columns)
        
        # Verify no negative waiting times
        self.assertTrue((df["waiting_time_minutes"] >= 0.0).all())

    def test_model_training_and_evaluation(self):
        """Verify RandomForestRegressor outperforms the Mean baseline."""
        df = generate_synthetic_procurement_dataset(n_samples=300, random_seed=42)
        X = df[ALL_FEATURES]
        y = df["waiting_time_minutes"]

        # Baseline
        baseline = build_baseline_pipeline()
        baseline.fit(X, y)
        b_metrics = evaluate_model(baseline, X, y)

        # Random Forest
        rf = build_pipeline()
        rf.fit(X, y)
        rf_metrics = evaluate_model(rf, X, y)

        self.assertLess(rf_metrics["mae"], b_metrics["mae"])
        self.assertGreater(rf_metrics["r2"], 0.70)

    def test_unknown_crop_category_robustness(self):
        """Verify model handles unseen or newly introduced crop names gracefully without crashing."""
        model, _ = load_trained_model()
        if model is None:
            # Train a quick small model if artifact not yet saved in test runner
            df = generate_synthetic_procurement_dataset(n_samples=100)
            model = build_pipeline()
            model.fit(df[ALL_FEATURES], df["waiting_time_minutes"])

        # Create input with unknown crop name
        unseen_input = pd.DataFrame([{
            "farmers_ahead": 3,
            "crop_name": "Dragon Fruit (Unregistered)",
            "estimated_quantity": 40.0,
            "active_counters": 2,
            "arrival_hour": 11,
            "day_of_week": 2,
            "center_total_load_quintals": 120.0
        }])

        pred = model.predict(unseen_input)
        self.assertIsNotNone(pred)
        self.assertGreaterEqual(float(pred[0]), 0.0)

    def test_zero_farmers_ahead_returns_zero_or_immediate(self):
        """Verify when no farmers ahead, wait time prediction is zero."""
        conn = get_direct_connection(self.db_path)
        # Booking 6 is IN_PROGRESS (ahead = 0)
        res = predict_waiting_time_for_booking(6, conn=conn, save_record=False)
        self.assertEqual(res["predicted_wait_minutes"], 0.0)
        self.assertEqual(res["farmers_ahead"], 0)
        conn.close()

    def test_fallback_when_model_missing(self):
        """Verify heuristic fallback calculates sensible non-negative waiting time."""
        wait = rule_based_fallback_wait(farmers_ahead=4, estimated_quantity=50.0, active_counters=2)
        self.assertGreater(wait, 0.0)
        self.assertLess(wait, 120.0)

        # Zero farmers ahead
        zero_wait = rule_based_fallback_wait(farmers_ahead=0, estimated_quantity=50.0)
        self.assertEqual(zero_wait, 0.0)


if __name__ == "__main__":
    unittest.main()
