"""
AgriQueue - Automated Unit Tests for Authentication & Role-Based Authorization
"""

import os
import unittest
import tempfile
import sys

# Ensure application package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from database import init_db, seed_demo_data
from werkzeug.security import generate_password_hash, check_password_hash


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        app.config["DATABASE_PATH"] = self.db_path
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
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

    def test_password_hashing(self):
        """Verify Werkzeug generates secure one-way password hashes."""
        raw_pass = "Kisan@Pass123"
        hashed = generate_password_hash(raw_pass)
        self.assertNotEqual(raw_pass, hashed)
        self.assertTrue(check_password_hash(hashed, raw_pass))
        self.assertFalse(check_password_hash(hashed, "WrongPass"))

    def test_farmer_registration_success(self):
        """Verify a new farmer can register with complete agricultural details."""
        response = self.client.post("/register", data={
            "name": "Balram Singh",
            "phone": "9826999999",
            "email": "balram@kisan.in",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "father_husband_name": "Shri Shivraj Singh",
            "village": "Pipaliya",
            "tehsil": "Huzur",
            "district": "Bhopal",
            "land_area_acres": "14.5"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registration successful", response.data)

    def test_farmer_registration_duplicate_phone_rejected(self):
        """Verify phone uniqueness is strictly enforced."""
        # Ramesh's phone 9826011111 is already seeded
        response = self.client.post("/register", data={
            "name": "Ramesh Imposter",
            "phone": "9826011111",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "village": "Berasia"
        }, follow_redirects=True)
        self.assertIn(b"already registered", response.data)

    def test_farmer_login_and_logout(self):
        """Verify farmer can log in and sign out securely."""
        response = self.client.post("/login", data={
            "identifier": "9826011111",
            "password": "Agri@1234"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ramesh Kumar Yadav", response.data)

        # Logout
        logout_resp = self.client.get("/logout", follow_redirects=True)
        self.assertIn(b"securely signed out", logout_resp.data)

    def test_role_authorization_farmer_cannot_access_admin_dashboard(self):
        """Verify a farmer user is barred from administrative routes."""
        # Login as farmer
        self.client.post("/login", data={
            "identifier": "9826011111",
            "password": "Agri@1234"
        })
        # Try to access admin dashboard
        response = self.client.get("/admin/dashboard", follow_redirects=True)
        self.assertIn(b"Access denied", response.data)

    def test_operator_login_redirect(self):
        """Verify operator lands on operator dashboard."""
        response = self.client.post("/login", data={
            "identifier": "9876500001",
            "password": "Agri@1234"
        }, follow_redirects=True)
        self.assertIn(b"Operator Console", response.data)


if __name__ == "__main__":
    unittest.main()
