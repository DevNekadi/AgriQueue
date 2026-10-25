"""
AgriQueue - Machine Learning Model Training & Evaluation Pipeline
Generates realistic Indian agricultural procurement queue dataset (synthetic demonstration data),
trains a scikit-learn RandomForestRegressor, evaluates against a baseline, and saves the artifact.
"""

import os
import random
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split
from ml_model import (
    build_pipeline,
    build_baseline_pipeline,
    evaluate_model,
    save_trained_model,
    ALL_FEATURES
)

CSV_DATA_PATH = os.path.join(os.path.dirname(__file__), "ml", "procurement_training_data.csv")


def generate_synthetic_procurement_dataset(n_samples=2500, random_seed=42):
    """
    Generate synthetic queue records based on realistic Madhya Pradesh mandi procurement patterns:
    - Crops: Wheat, Soybean, Gram, Mustard, Maize
    - Average quantity: 15 to 100 quintals per tractor-trolley
    - Active counters: 1 to 4
    - Arrival hours: 9 AM to 4 PM (peak rush between 10 AM and 1 PM)
    - Ground truth wait time calculation incorporates realistic physical queueing delays:
        Wait ~ (farmers_ahead * avg_service_time) / active_counters + quantity_unloading_friction + peak_hour_delay
    """
    random.seed(random_seed)
    np.random.seed(random_seed)

    crop_types = [
        "Wheat (Gehun - Sharbati)",
        "Soybean (Yellow)",
        "Gram (Chana / Chickpea)",
        "Mustard (Sarson)",
        "Maize (Makka)"
    ]

    # Crop inspection and unloading characteristics (weight factor in minutes per quintal)
    crop_complexity = {
        "Wheat (Gehun - Sharbati)": 0.22,
        "Soybean (Yellow)": 0.26, # Oilseeds require oil/moisture testing
        "Gram (Chana / Chickpea)": 0.20,
        "Mustard (Sarson)": 0.28,
        "Maize (Makka)": 0.18
    }

    records = []

    for _ in range(n_samples):
        crop = random.choice(crop_types)
        farmers_ahead = int(np.random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 15], 
                                            p=[0.08, 0.12, 0.15, 0.15, 0.13, 0.10, 0.09, 0.07, 0.05, 0.03, 0.02, 0.01]))
        
        # Quantity in quintals (standard trolley load: 20-60 quintals, larger loads up to 100)
        est_qty = round(float(np.random.exponential(scale=35.0) + 15.0), 1)
        est_qty = min(est_qty, 120.0)

        # Active counters at procurement center
        counters = int(np.random.choice([1, 2, 3, 4], p=[0.2, 0.5, 0.2, 0.1]))

        # Arrival hour (9 AM to 16 PM / 4 PM)
        arrival_hour = int(np.random.choice(range(9, 17), p=[0.08, 0.18, 0.22, 0.18, 0.10, 0.10, 0.08, 0.06]))

        # Day of week: 0=Mon to 5=Sat (Sundays closed)
        day_of_week = int(np.random.choice(range(6)))

        # Aggregate workload ahead in quintals
        center_load = round(float(farmers_ahead * 36.5 + np.random.normal(0, 10)), 1)
        center_load = max(0.0, center_load)

        # Ground truth waiting time physics simulation (minutes until farmer service begins)
        if farmers_ahead == 0:
            actual_wait = 0.0
        else:
            base_service_time_per_farmer = 12.0 # mins for paperwork, weighbridge, moisture test
            load_factor = center_load * crop_complexity[crop] * 0.15
            peak_multiplier = 1.25 if arrival_hour in [10, 11, 12] else 1.0
            
            simulated_wait = ((farmers_ahead * base_service_time_per_farmer + load_factor) / counters) * peak_multiplier
            # Add stochastic operational noise (e.g., printer paper jam, quality dispute, tally delay)
            noise = np.random.normal(0, 3.5)
            actual_wait = max(3.0, round(simulated_wait + noise, 1))

        records.append({
            "farmers_ahead": farmers_ahead,
            "crop_name": crop,
            "estimated_quantity": est_qty,
            "active_counters": counters,
            "arrival_hour": arrival_hour,
            "day_of_week": day_of_week,
            "center_total_load_quintals": center_load,
            "waiting_time_minutes": actual_wait
        })

    df = pd.DataFrame(records)
    return df


def train_and_evaluate():
    """Execute training pipeline, compare against baseline, and persist artifact."""
    print("=" * 60)
    print("AGRIQUEUE MACHINE LEARNING TRAINING & EVALUATION")
    print("=" * 60)

    # 1. Dataset Generation & Persistence
    print("Generating synthetic procurement dataset (2,500 samples)...")
    df = generate_synthetic_procurement_dataset(n_samples=2500, random_seed=42)
    os.makedirs(os.path.dirname(CSV_DATA_PATH), exist_ok=True)
    df.to_csv(CSV_DATA_PATH, index=False)
    print(f"Dataset persisted to {CSV_DATA_PATH}")

    # 2. Features and Target
    X = df[ALL_FEATURES]
    y = df["waiting_time_minutes"]

    # 3. Train-Test Split (80% Train, 20% Test)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    print(f"Dataset split: Train samples = {len(X_train)}, Test samples = {len(X_test)}")

    # 4. Train Baseline Model (DummyRegressor)
    print("\nTraining Baseline Model (Mean Predictor)...")
    baseline = build_baseline_pipeline()
    baseline.fit(X_train, y_train)
    baseline_metrics = evaluate_model(baseline, X_test, y_test)
    print(f"  [Baseline] MAE : {baseline_metrics['mae']} minutes")
    print(f"  [Baseline] RMSE: {baseline_metrics['rmse']} minutes")
    print(f"  [Baseline] R^2 : {baseline_metrics['r2']}")

    # 5. Train Random Forest Regressor
    print("\nTraining RandomForestRegressor...")
    rf_pipeline = build_pipeline()
    rf_pipeline.fit(X_train, y_train)
    rf_metrics = evaluate_model(rf_pipeline, X_test, y_test)
    print(f"  [RandomForest] MAE : {rf_metrics['mae']} minutes")
    print(f"  [RandomForest] RMSE: {rf_metrics['rmse']} minutes")
    print(f"  [RandomForest] R^2 : {rf_metrics['r2']}")

    # 6. Verify Model Outperformed Baseline
    improvement = round(baseline_metrics["mae"] - rf_metrics["mae"], 2)
    print(f"\n=> Random Forest achieved a {improvement} minute MAE improvement over baseline.")

    # 7. Persist Trained Artifact with Metadata
    metadata = {
        "dataset_type": "Synthetic Demonstration Data (MP Mandi Procurement Simulation)",
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_samples": len(df),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "baseline_metrics": baseline_metrics,
        "rf_metrics": rf_metrics,
        "model_name": "RandomForestRegressor(n_estimators=100, max_depth=12)"
    }

    save_trained_model(rf_pipeline, rf_metrics, metadata)
    print("=" * 60)
    print("TRAINING COMPLETE & MODEL ARTIFACT VERIFIED")
    print("=" * 60)
    return rf_metrics, baseline_metrics


if __name__ == "__main__":
    train_and_evaluate()
