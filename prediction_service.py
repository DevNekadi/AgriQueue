"""
AgriQueue - Waiting Time Prediction Service
Extracts live database queue states, builds valid feature vectors,
invokes the trained scikit-learn model, and falls back gracefully if unavailable.
"""

import os
import json
from datetime import datetime, date
import pandas as pd
from database import get_db, get_direct_connection
from ml_model import (
    load_trained_model,
    rule_based_fallback_wait,
    ALL_FEATURES
)

# Global model cache to avoid re-reading disk on every web request
_CACHED_MODEL = None
_CACHED_METADATA = None


def get_cached_model():
    """Retrieve or load cached model pipeline into memory."""
    global _CACHED_MODEL, _CACHED_METADATA
    if _CACHED_MODEL is None:
        _CACHED_MODEL, _CACHED_METADATA = load_trained_model()
    return _CACHED_MODEL, _CACHED_METADATA


def reload_model():
    """Force reload of model artifact (used after manual retraining)."""
    global _CACHED_MODEL, _CACHED_METADATA
    _CACHED_MODEL, _CACHED_METADATA = load_trained_model()
    return _CACHED_MODEL is not None


def compute_queue_position_and_ahead(booking_id, conn=None):
    """
    Dynamically calculate the queue position and number of eligible farmers ahead.
    Ordering rule:
    1. Active farmers being served: 'IN_PROGRESS', 'CALLED'
    2. Arrived farmers waiting: 'WAITING' ordered by arrival_time ASC, id ASC
    3. Booked farmers arriving today: 'CONFIRMED', 'REQUESTED' ordered by time_slot ASC, id ASC
    
    Returns: (position, farmers_ahead, total_active_in_queue, center_total_load)
    """
    db = conn or get_db()
    
    # Get target booking details
    booking = db.execute(
        """
        SELECT id, center_id, booking_date, status, arrival_time, time_slot, estimated_quantity
        FROM bookings WHERE id = ?
        """,
        (booking_id,)
    ).fetchone()

    if not booking:
        return 0, 0, 0, 0.0

    status = booking["status"]
    center_id = booking["center_id"]
    booking_date = booking["booking_date"]

    # Terminated states have 0 waiting time
    if status in ("COMPLETED", "CANCELLED", "REJECTED"):
        return 0, 0, 0, 0.0

    # If currently being served
    if status == "IN_PROGRESS":
        return 1, 0, 1, 0.0

    # Fetch all active eligible bookings for this center and date
    query = """
        SELECT id, status, arrival_time, time_slot, estimated_quantity
        FROM bookings
        WHERE center_id = ? 
          AND booking_date = ? 
          AND status IN ('IN_PROGRESS', 'CALLED', 'WAITING', 'CONFIRMED', 'REQUESTED')
    """
    rows = db.execute(query, (center_id, booking_date)).fetchall()

    # Priority ranking function for ordering
    def queue_sort_key(r):
        st = r["status"]
        if st == "IN_PROGRESS":
            prio = 1
        elif st == "CALLED":
            prio = 2
        elif st == "WAITING":
            prio = 3
        elif st == "CONFIRMED":
            prio = 4
        else: # REQUESTED
            prio = 5
        arr = r["arrival_time"] or "9999-99-99"
        slot = r["time_slot"] or "99:99"
        return (prio, arr, slot, r["id"])

    sorted_queue = sorted(rows, key=queue_sort_key)
    
    total_active = len(sorted_queue)
    position = 1
    farmers_ahead = 0
    center_total_load = 0.0

    target_found = False
    for idx, item in enumerate(sorted_queue, start=1):
        if item["id"] == booking_id:
            position = idx
            farmers_ahead = idx - 1
            target_found = True
        else:
            # Accumulate load ahead
            if not target_found:
                center_total_load += float(item["estimated_quantity"] or 0.0)

    if not target_found:
        # Fallback if somehow not in list
        position = total_active + 1
        farmers_ahead = total_active

    return position, farmers_ahead, total_active, round(center_total_load, 1)


def predict_waiting_time_for_booking(booking_id, conn=None, save_record=True):
    """
    Generate waiting-time prediction for a specific booking.
    Extracts features from database, queries the trained model,
    clamps invalid values, and records telemetry.
    """
    db = conn or get_db()
    
    # Query complete booking and center context
    query = """
        SELECT 
            b.id AS booking_id,
            b.token_number,
            b.booking_date,
            b.time_slot,
            b.estimated_quantity,
            b.status,
            c.id AS center_id,
            c.name AS center_name,
            c.active_counters,
            cr.name AS crop_name,
            u.name AS farmer_name,
            u.phone AS farmer_phone
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        WHERE b.id = ?
    """
    row = db.execute(query, (booking_id,)).fetchone()
    if not row:
        return None

    status = row["status"]
    now = datetime.now()

    # Immediate return for terminal states
    if status == "COMPLETED":
        return {
            "booking_id": booking_id,
            "token_number": row["token_number"],
            "queue_position": 0,
            "farmers_ahead": 0,
            "predicted_wait_minutes": 0.0,
            "formatted_wait": "Procurement Completed",
            "status": status,
            "source": "Terminal State",
            "is_fallback": False,
            "explanation": "Procurement has already been completed and verified.",
            "timestamp": now.strftime("%I:%M %p, %d %b %Y")
        }

    if status in ("CANCELLED", "REJECTED", "SKIPPED"):
        return {
            "booking_id": booking_id,
            "token_number": row["token_number"],
            "queue_position": 0,
            "farmers_ahead": 0,
            "predicted_wait_minutes": 0.0,
            "formatted_wait": f"Status: {status.title()}",
            "status": status,
            "source": "Inactive State",
            "is_fallback": False,
            "explanation": f"Booking is currently in '{status}' status.",
            "timestamp": now.strftime("%I:%M %p, %d %b %Y")
        }

    if status == "IN_PROGRESS":
        return {
            "booking_id": booking_id,
            "token_number": row["token_number"],
            "queue_position": 1,
            "farmers_ahead": 0,
            "predicted_wait_minutes": 0.0,
            "formatted_wait": "At Counter (In Service)",
            "status": status,
            "source": "Live Counter",
            "is_fallback": False,
            "explanation": "Produce weighing and quality inspection is currently underway.",
            "timestamp": now.strftime("%I:%M %p, %d %b %Y")
        }

    # Dynamic queue calculation
    pos, ahead, total_active, center_load = compute_queue_position_and_ahead(booking_id, conn=db)
    
    # Feature extraction
    active_counters = max(1, int(row["active_counters"] or 2))
    arrival_hour = now.hour
    day_of_week = now.weekday()
    crop_name = row["crop_name"]
    est_qty = float(row["estimated_quantity"] or 30.0)

    model, meta = get_cached_model()
    is_fallback = False
    source = "AI Model (Random Forest)"
    predicted_wait = 0.0

    if ahead == 0:
        predicted_wait = 0.0
        formatted = "Next in Line (0 min wait)"
        explanation = "You are at the front of the queue. Please proceed to the verification counter."
    else:
        if model is not None:
            try:
                features_dict = {
                    "farmers_ahead": [ahead],
                    "crop_name": [crop_name],
                    "estimated_quantity": [est_qty],
                    "active_counters": [active_counters],
                    "arrival_hour": [arrival_hour],
                    "day_of_week": [day_of_week],
                    "center_total_load_quintals": [center_load]
                }
                X_input = pd.DataFrame(features_dict)
                raw_pred = float(model.predict(X_input)[0])
                # Safety clamp: non-negative and realistic minimum when farmers ahead > 0
                predicted_wait = max(3.0, round(raw_pred, 1))
            except Exception as e:
                print(f"Prediction inference error: {e}, falling back to operational heuristic.")
                predicted_wait = rule_based_fallback_wait(ahead, est_qty, active_counters)
                is_fallback = True
                source = "Heuristic Operational Fallback"
        else:
            predicted_wait = rule_based_fallback_wait(ahead, est_qty, active_counters)
            is_fallback = True
            source = "Heuristic Operational Fallback"

        formatted = f"About {int(round(predicted_wait))} minutes"
        explanation = (
            f"Estimated wait time until your turn begins, based on {ahead} farmer(s) ahead, "
            f"{active_counters} counter(s) open, and {round(est_qty, 1)} quintals of {crop_name}."
        )

    # Persist prediction snapshot for auditing and evaluation
    if save_record:
        try:
            snapshot_features = {
                "farmers_ahead": ahead,
                "crop": crop_name,
                "quantity": est_qty,
                "counters": active_counters,
                "center_load": center_load
            }
            db.execute(
                """
                INSERT INTO prediction_records (booking_id, queue_position, farmers_ahead, 
                                               predicted_wait_minutes, model_version, is_fallback, features_snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (booking_id, pos, ahead, predicted_wait, "rf_regressor_v1", 1 if is_fallback else 0, json.dumps(snapshot_features))
            )
            if not conn:
                db.commit()
        except Exception as e:
            print(f"Error persisting prediction log: {e}")

    return {
        "booking_id": booking_id,
        "token_number": row["token_number"],
        "farmer_name": row["farmer_name"],
        "center_name": row["center_name"],
        "crop_name": crop_name,
        "estimated_quantity": est_qty,
        "queue_position": pos,
        "farmers_ahead": ahead,
        "total_active_in_queue": total_active,
        "predicted_wait_minutes": predicted_wait,
        "formatted_wait": formatted,
        "status": status,
        "active_counters": active_counters,
        "source": source,
        "is_fallback": is_fallback,
        "explanation": explanation,
        "timestamp": now.strftime("%I:%M %p, %d %b %Y")
    }
