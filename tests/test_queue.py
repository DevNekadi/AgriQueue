"""
AgriQueue - Automated Unit Tests for Queue Lifecycle & State Transitions
"""

import os
import unittest
import tempfile
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from database import init_db, seed_demo_data, get_direct_connection
from prediction_service import compute_queue_position_and_ahead


class QueueLifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        app.config["DATABASE_PATH"] = self.db_path
        app.config["TESTING"] = True
        self.client = app.test_client()

        with app.app_context():
            init_db(db_path=self.db_path)
            seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def login_operator(self):
        self.client.post("/login", data={
            "identifier": "9876500001",
            "password": "Agri@1234"
        })

    def test_dynamic_queue_position_computation(self):
        """Verify dynamic calculation of queue position based on status hierarchy."""
        conn = get_direct_connection(self.db_path)
        
        # Today's live active bookings in seeded DB:
        # Token 1 (id 6): IN_PROGRESS -> position 1, 0 ahead
        # Token 2 (id 7): CALLED -> position 2, 1 ahead
        # Token 3 (id 8): WAITING -> position 3, 2 ahead
        pos, ahead, total_active, _ = compute_queue_position_and_ahead(8, conn=conn)
        self.assertEqual(pos, 3)
        self.assertEqual(ahead, 2)
        self.assertGreaterEqual(total_active, 3)
        conn.close()

    def test_operator_status_transitions(self):
        """Verify operator can mark farmer arrived, call, and start weighment."""
        self.login_operator()
        conn = get_direct_connection(self.db_path)
        
        # Find a CONFIRMED booking from today
        b = conn.execute("SELECT id FROM bookings WHERE status = 'CONFIRMED' LIMIT 1").fetchone()
        b_id = b["id"]

        # 1. Mark Arrived (CONFIRMED -> WAITING)
        resp1 = self.client.post(f"/operator/booking/{b_id}/status", data={"status": "WAITING"}, follow_redirects=True)
        self.assertEqual(resp1.status_code, 200)
        row = conn.execute("SELECT status, arrival_time FROM bookings WHERE id = ?", (b_id,)).fetchone()
        self.assertEqual(row["status"], "WAITING")
        self.assertIsNotNone(row["arrival_time"])

        # 2. Call Farmer (WAITING -> CALLED)
        resp2 = self.client.post(f"/operator/booking/{b_id}/status", data={"status": "CALLED"}, follow_redirects=True)
        self.assertEqual(resp2.status_code, 200)
        row = conn.execute("SELECT status FROM bookings WHERE id = ?", (b_id,)).fetchone()
        self.assertEqual(row["status"], "CALLED")

        # 3. Start Service (CALLED -> IN_PROGRESS)
        resp3 = self.client.post(f"/operator/booking/{b_id}/status", data={"status": "IN_PROGRESS"}, follow_redirects=True)
        self.assertEqual(resp3.status_code, 200)
        row = conn.execute("SELECT status, service_start_time FROM bookings WHERE id = ?", (b_id,)).fetchone()
        self.assertEqual(row["status"], "IN_PROGRESS")
        self.assertIsNotNone(row["service_start_time"])
        conn.close()

    def test_skip_and_requeue_workflow(self):
        """Verify operator can skip absent farmer with a recorded reason, then requeue."""
        self.login_operator()
        conn = get_direct_connection(self.db_path)
        b = conn.execute("SELECT id FROM bookings WHERE status = 'WAITING' LIMIT 1").fetchone()
        b_id = b["id"]

        # Skip with reason
        skip_reason = "Trolley punctured outside mandi gate"
        self.client.post(f"/operator/booking/{b_id}/status", data={
            "status": "SKIPPED",
            "reason": skip_reason
        }, follow_redirects=True)

        row = conn.execute("SELECT status, skip_reason FROM bookings WHERE id = ?", (b_id,)).fetchone()
        self.assertEqual(row["status"], "SKIPPED")
        self.assertEqual(row["skip_reason"], skip_reason)

        # Requeue
        self.client.post(f"/operator/booking/{b_id}/requeue", follow_redirects=True)
        row = conn.execute("SELECT status, skip_reason FROM bookings WHERE id = ?", (b_id,)).fetchone()
        self.assertEqual(row["status"], "WAITING")
        self.assertIsNone(row["skip_reason"])
        conn.close()

    def test_record_procurement_completion(self):
        """Verify completing procurement persists actual weight and calculates total amount."""
        self.login_operator()
        conn = get_direct_connection(self.db_path)
        b = conn.execute("SELECT id FROM bookings WHERE status = 'IN_PROGRESS' LIMIT 1").fetchone()
        b_id = b["id"]

        response = self.client.post(f"/operator/booking/{b_id}/procurement", data={
            "actual_quantity": "50.0",
            "rate_per_quintal": "2425.0",
            "grade_quality": "Grade A FAQ",
            "moisture_percentage": "11.5",
            "remarks": "Weighbridge #1 Verified"
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        # Check booking completed
        b_row = conn.execute("SELECT status, completion_time FROM bookings WHERE id = ?", (b_id,)).fetchone()
        self.assertEqual(b_row["status"], "COMPLETED")
        self.assertIsNotNone(b_row["completion_time"])

        # Check procurement receipt
        pr = conn.execute("SELECT * FROM procurement_records WHERE booking_id = ?", (b_id,)).fetchone()
        self.assertIsNotNone(pr)
        self.assertEqual(pr["actual_quantity"], 50.0)
        self.assertEqual(pr["total_amount"], 50.0 * 2425.0) # 1,21,250
        conn.close()


if __name__ == "__main__":
    unittest.main()
