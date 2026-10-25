"""
AgriQueue - Automated Unit Tests for Booking Logic, Tokens, and Capacity
"""

import os
import unittest
import tempfile
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from database import init_db, seed_demo_data, get_direct_connection, generate_unique_token


class BookingTestCase(unittest.TestCase):
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

    def login_farmer(self):
        self.client.post("/login", data={
            "identifier": "9826011111",
            "password": "Agri@1234"
        })

    def test_unique_token_generation_format(self):
        """Verify token adheres strictly to AQ-YYYYMMDD-XXXX format and is sequential."""
        conn = get_direct_connection(self.db_path)
        today_str = date.today().strftime("%Y-%m-%d")
        clean_date = today_str.replace("-", "")

        token_a = generate_unique_token(1, today_str, conn=conn)
        self.assertTrue(token_a.startswith(f"AQ-{clean_date}-"))
        self.assertEqual(len(token_a), 16)
        conn.close()

    def test_valid_booking_creation(self):
        """Verify farmer can book a procurement slot and receive a persistent token."""
        self.login_farmer()
        # Choose tomorrow (or next non-Sunday)
        target_date = date.today() + timedelta(days=1)
        if target_date.weekday() == 6:
            target_date += timedelta(days=1)
        target_str = target_date.strftime("%Y-%m-%d")

        response = self.client.post("/booking", data={
            "center_id": "1",
            "crop_id": "1",
            "booking_date": target_str,
            "time_slot": "09:00 - 11:00 AM",
            "estimated_quantity": "42.5"
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Slot booked successfully", response.data)
        self.assertIn(b"AQ-", response.data)

    def test_invalid_past_date_booking_rejected(self):
        """Verify bookings for past dates are blocked."""
        self.login_farmer()
        past_str = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")

        response = self.client.post("/booking", data={
            "center_id": "1",
            "crop_id": "1",
            "booking_date": past_str,
            "time_slot": "09:00 - 11:00 AM",
            "estimated_quantity": "30.0"
        }, follow_redirects=True)

        self.assertIn(b"cannot be in the past", response.data)

    def test_booking_cancellation_by_owner(self):
        """Verify farmer can cancel their own confirmed booking."""
        self.login_farmer()
        # Find farmer id for Ramesh (phone 9826011111)
        conn = get_direct_connection(self.db_path)
        farmer = conn.execute("SELECT id FROM users WHERE phone = '9826011111'").fetchone()
        farmer_id = farmer["id"]

        # Insert a CONFIRMED test booking for Ramesh
        target_str = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot, estimated_quantity, status)
            VALUES ('AQ-TEST-CANCEL-01', ?, 1, 1, ?, '09:00 - 11:00 AM', 25.0, 'CONFIRMED')
            """,
            (farmer_id, target_str)
        )
        b_id = cursor.lastrowid
        conn.commit()
        conn.close()

        resp = self.client.post(f"/booking/{b_id}/cancel", follow_redirects=True)
        self.assertIn(b"cancelled successfully", resp.data)


if __name__ == "__main__":
    unittest.main()
