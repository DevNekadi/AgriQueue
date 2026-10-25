"""
AgriQueue - Machine Learning Model Architecture & Helpers
Defines feature schema, preprocessing pipelines, model loading, and waiting-time prediction.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

MODEL_FILE_PATH = os.path.join(os.path.dirname(__file__), "ml", "waiting_time_model.joblib")

# Numerical and Categorical feature definitions
NUMERIC_FEATURES = [
    "farmers_ahead",
    "estimated_quantity",
    "active_counters",
    "arrival_hour",
    "day_of_week",
    "center_total_load_quintals"
]

CATEGORICAL_FEATURES = [
    "crop_name"
]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def build_pipeline():
    """
    Construct an end-to-end scikit-learn Pipeline with ColumnTransformer
    handling categorical one-hot encoding with unknown handling and standard scaling.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES)
        ],
        remainder="drop"
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("regressor", RandomForestRegressor(
                n_estimators=100,
                max_depth=12,
                min_samples_split=4,
                min_samples_leaf=2,
                random_state=42
            ))
        ]
    )
    return pipeline


def build_baseline_pipeline():
    """Construct a baseline DummyRegressor (mean prediction) for performance comparison."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES)
        ]
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("regressor", DummyRegressor(strategy="mean"))
        ]
    )


def evaluate_model(model, X_test, y_test):
    """
    Compute rigorous regression metrics: MAE, RMSE, and R-squared.
    Does NOT use bogus 'accuracy %' for a regression task.
    """
    y_pred = model.predict(X_test)
    # Ensure non-negative predictions
    y_pred_clamped = np.maximum(0.0, y_pred)
    
    mae = mean_absolute_error(y_test, y_pred_clamped)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred_clamped))
    r2 = r2_score(y_test, y_pred_clamped)
    
    return {
        "mae": round(float(mae), 2),
        "rmse": round(float(rmse), 2),
        "r2": round(float(r2), 3),
        "samples_tested": len(y_test)
    }


def save_trained_model(pipeline, metrics, metadata=None, filepath=None):
    """Save pipeline artifact with training metadata and evaluation metrics."""
    if not filepath:
        filepath = MODEL_FILE_PATH
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    payload = {
        "pipeline": pipeline,
        "metrics": metrics,
        "metadata": metadata or {},
        "features": ALL_FEATURES
    }
    joblib.dump(payload, filepath)
    print(f"Model artifact saved to {filepath}")


def load_trained_model(filepath=None):
    """
    Load saved model artifact.
    Returns (pipeline, metadata_dict) or (None, None) if missing/invalid.
    """
    if not filepath:
        filepath = MODEL_FILE_PATH
    if not os.path.exists(filepath):
        return None, None
    try:
        data = joblib.load(filepath)
        if isinstance(data, dict) and "pipeline" in data:
            return data["pipeline"], data
        return data, {"metrics": {}}
    except Exception as e:
        print(f"Warning: Failed to load ML model from {filepath}: {e}")
        return None, None


def rule_based_fallback_wait(farmers_ahead, estimated_quantity, active_counters=2, avg_mins_per_farmer=15):
    """
    Beginner-friendly heuristic fallback when ML model is not yet trained or loaded.
    Considers queue ahead, active counters, and quantity scaling.
    """
    if farmers_ahead <= 0:
        return 0.0
    
    counters = max(1, active_counters)
    # Approximate service time: base 10 mins + 0.15 mins per quintal
    service_est = 10.0 + (estimated_quantity * 0.15)
    
    # Waiting time is roughly farmers ahead distributed across counters
    wait = (farmers_ahead * service_est) / counters
    return max(2.0, round(wait, 1))
