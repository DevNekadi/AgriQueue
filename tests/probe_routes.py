"""
Quick end-to-end integration probe for AgriQueue web pages and workflows.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app

client = app.test_client()

# 1. Public Pages
pages = ["/", "/centers", "/login", "/register"]
for page in pages:
    res = client.get(page)
    assert res.status_code == 200, f"Page {page} failed with {res.status_code}"
    print(f"[OK] Page '{page}' -> 200 ({len(res.data)} bytes)")

# 2. Farmer Login & Dashboard
res_login = client.post("/login", data={"identifier": "9826011111", "password": "Agri@1234"}, follow_redirects=True)
assert res_login.status_code == 200
assert b"Ramesh Kumar Yadav" in res_login.data
print("[OK] Farmer Login Successful")

res_dash = client.get("/farmer/dashboard")
assert res_dash.status_code == 200
print(f"[OK] Farmer Dashboard -> 200 ({len(res_dash.data)} bytes)")

# 3. Live Turn Tracker & Dynamic AI Prediction for Ramesh's own booking (id 6)
res_queue = client.get("/queue-status/6")
assert res_queue.status_code == 200, f"Queue status failed with {res_queue.status_code}"
assert b"Live Queue Turn Tracker" in res_queue.data
print(f"[OK] Live Turn Tracker for Ramesh's Token (id 6) -> 200 ({len(res_queue.data)} bytes)")

# Verify Privacy Enforcement: Ramesh CANNOT access Geeta's booking (id 8)
res_unauthorized = client.get("/queue-status/8")
assert res_unauthorized.status_code == 403, f"Expected 403 Forbidden, got {res_unauthorized.status_code}"
print("[OK] Privacy Enforcement Verified: Farmer cannot access another farmer's token (403 Forbidden)")

# 4. JSON API endpoint for live polling
res_api = client.get("/api/queue-status/6")
assert res_api.status_code == 200
data = res_api.get_json()
assert data["success"] is True
print(f"[OK] Live Polling API -> 200, Pos: #{data['queue_position']}, Ahead: {data['farmers_ahead']}, Wait: {data['formatted_wait']}")

# 5. Operator Login & Dashboard
client.get("/logout")
res_op_login = client.post("/login", data={"identifier": "9876500001", "password": "Agri@1234"}, follow_redirects=True)
assert res_op_login.status_code == 200
assert b"Operator Console" in res_op_login.data
print("[OK] Operator Console Loaded")

# 6. Admin Login & System Control Dashboard
client.get("/logout")
res_admin_login = client.post("/login", data={"identifier": "9876543210", "password": "Agri@1234"}, follow_redirects=True)
assert res_admin_login.status_code == 200
assert b"System Control" in res_admin_login.data
print("[OK] Administrator Dashboard Loaded")

res_reports = client.get("/admin/reports")
assert res_reports.status_code == 200
assert b"Procurement Reports" in res_reports.data
print(f"[OK] Admin Reports -> 200 ({len(res_reports.data)} bytes)")

print("\nALL INTEGRATION PROBES PASSED SUCCESSFULLY!")
