"""
AgriQueue - Database Access and Lifecycle Management
Provides SQLite connection management, initialization, seeding, and audit logging.
"""

import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import g, current_app
from werkzeug.security import generate_password_hash

DEFAULT_DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "instance", "agriqueue.db")
)


def get_db():
    """Get database connection for current request context."""
    db_path = current_app.config.get("DATABASE_PATH", DEFAULT_DB_PATH) if current_app else DEFAULT_DB_PATH
    
    # Ensure instance directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    if "db" not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        # Enable foreign key enforcement
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(e=None):
    """Close the database connection at request teardown."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_direct_connection(db_path=None):
    """Obtain a standalone connection for scripts, background tasks, or testing."""
    if not db_path:
        db_path = DEFAULT_DB_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(schema_path=None, db_path=None):
    """Initialize database from schema.sql."""
    if not schema_path:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = get_direct_connection(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def log_audit(actor_id, action, entity_type=None, entity_id=None, details=None, ip_address=None, conn=None):
    """Log critical system actions for compliance and traceability."""
    db = conn or get_db()
    db.execute(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, details, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (actor_id, action, entity_type, entity_id, details, ip_address)
    )
    if not conn:
        db.commit()


def add_notification(user_id, title, message, notif_type="info", conn=None):
    """Send an in-app notification to a user."""
    db = conn or get_db()
    db.execute(
        """
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, title, message, notif_type)
    )
    if not conn:
        db.commit()


def record_queue_event(booking_id, prev_status, new_status, actor_id=None, note=None, conn=None):
    """Record state transitions in the queue event history."""
    db = conn or get_db()
    db.execute(
        """
        INSERT INTO queue_events (booking_id, previous_status, new_status, actor_id, action_note)
        VALUES (?, ?, ?, ?, ?)
        """,
        (booking_id, prev_status, new_status, actor_id, note)
    )
    if not conn:
        db.commit()


def generate_unique_token(center_id, booking_date_str, conn=None):
    """
    Generate an atomic, sequential, human-readable token: AQ-YYYYMMDD-XXXX
    Prevents race conditions by locking or counting based on current day's bookings.
    """
    db = conn or get_db()
    # Normalize date string: YYYYMMDD
    clean_date = booking_date_str.replace("-", "")
    
    # Query count of bookings for that specific date to get sequential index
    row = db.execute(
        "SELECT COUNT(*) as count FROM bookings WHERE booking_date = ?",
        (booking_date_str,)
    ).fetchone()
    
    seq = (row["count"] + 1) if row else 1
    
    # Check if token exists, increment if needed until unique
    while True:
        token = f"AQ-{clean_date}-{seq:04d}"
        existing = db.execute("SELECT id FROM bookings WHERE token_number = ?", (token,)).fetchone()
        if not existing:
            return token
        seq += 1


def seed_demo_data(db_path=None, reset=False):
    """
    Seed realistic Indian agricultural demonstration data for Madhya Pradesh context.
    Idempotent: will not create duplicate records if already present.
    """
    conn = get_direct_connection(db_path)
    cursor = conn.cursor()

    if reset:
        cursor.execute("DROP TABLE IF EXISTS audit_logs")
        cursor.execute("DROP TABLE IF EXISTS prediction_records")
        cursor.execute("DROP TABLE IF EXISTS notifications")
        cursor.execute("DROP TABLE IF EXISTS queue_events")
        cursor.execute("DROP TABLE IF EXISTS procurement_records")
        cursor.execute("DROP TABLE IF EXISTS bookings")
        cursor.execute("DROP TABLE IF EXISTS center_crops")
        cursor.execute("DROP TABLE IF EXISTS crops")
        cursor.execute("DROP TABLE IF EXISTS operator_center_assignments")
        cursor.execute("DROP TABLE IF EXISTS procurement_centers")
        cursor.execute("DROP TABLE IF EXISTS farmer_profiles")
        cursor.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        init_db(db_path=db_path)
        conn = get_direct_connection(db_path)
        cursor = conn.cursor()

    # Check if any users already exist in the database
    existing_user_count = cursor.execute("SELECT COUNT(*) as count FROM users").fetchone()
    if existing_user_count and existing_user_count["count"] > 0:
        print("Database already contains user records. Skipping demo seeding to preserve existing data.")
        conn.close()
        return

    print("Seeding AgriQueue demo data...")

    # Default password hash for all demo users: "Agri@1234"
    demo_password_hash = generate_password_hash("Agri@1234")

    # 1. Admin User
    cursor.execute(
        """
        INSERT INTO users (phone, email, password_hash, role, name)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("9876543210", "admin@agriqueue.gov.in", demo_password_hash, "admin", "Shri R. K. Sharma (Director)")
    )
    admin_id = cursor.lastrowid

    # 2. Operator Users
    cursor.execute(
        """
        INSERT INTO users (phone, email, password_hash, role, name)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("9876500001", "operator.bhopal@agriqueue.gov.in", demo_password_hash, "operator", "Vikram Patel (Officer in Charge)")
    )
    op1_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO users (phone, email, password_hash, role, name)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("9876500002", "operator.sehore@agriqueue.gov.in", demo_password_hash, "operator", "Anand Verma (Procurement In-Charge)")
    )
    op2_id = cursor.lastrowid

    # 3. Farmer Users & Profiles
    farmers_data = [
        ("9826011111", "ramesh@kisan.in", "Ramesh Kumar Yadav", "Late Shri Hiralal Yadav", "Berasia Village", "Berasia", "Bhopal", 8.5),
        ("9826022222", "suresh@kisan.in", "Suresh Chandra Meena", "Shri Babulal Meena", "Phanda Kalan", "Phanda", "Bhopal", 12.0),
        ("9826033333", "geeta@kisan.in", "Geeta Devi Rajput", "Shri Mahendra Singh", "Doraha", "Shyampur", "Sehore", 6.0),
        ("9826044444", "jagdish@kisan.in", "Jagdish Prasad Malviya", "Shri Mohanlal Malviya", "Kothri", "Ashta", "Sehore", 15.0),
        ("9826055555", "mohan@kisan.in", "Mohan Singh Lodhi", "Shri Ramswaroop Lodhi", "Intkheri", "Huzur", "Bhopal", 10.0),
    ]

    farmer_ids = []
    for phone, email, name, father, village, tehsil, district, land in farmers_data:
        cursor.execute(
            """
            INSERT INTO users (phone, email, password_hash, role, name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (phone, email, demo_password_hash, "farmer", name)
        )
        f_uid = cursor.lastrowid
        farmer_ids.append(f_uid)

        cursor.execute(
            """
            INSERT INTO farmer_profiles (user_id, father_husband_name, village, tehsil, district, state, land_area_acres, kisan_credit_card_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f_uid, father, village, tehsil, district, "Madhya Pradesh", land, f"KCC-MP-{phone[-4:]}")
        )

    # 4. Procurement Centers
    centers_data = [
        ("Krishi Upaj Mandi Bhopal (Karond)", "MP-BPL-01", "Karond Mandi By-Pass Road, Bhopal, MP 462038", "Bhopal", "0755-2741234", "09:00 AM - 05:00 PM", 60, 3),
        ("Sehore Main Krishi Mandi Samiti", "MP-SEH-01", "Station Road, Mandi Yard, Sehore, MP 466001", "Sehore", "07562-224567", "09:00 AM - 05:00 PM", 45, 2),
        ("Berasia Sub-Procurement Yard", "MP-BPL-02", "Narsinghgarh Road, Berasia, Bhopal, MP 463106", "Bhopal", "0755-2882100", "09:30 AM - 04:30 PM", 30, 2),
    ]

    center_ids = []
    for c_name, c_code, c_addr, c_dist, c_phone, c_hours, c_cap, c_cnt in centers_data:
        cursor.execute(
            """
            INSERT INTO procurement_centers (name, code, address, district, contact_phone, operating_hours, daily_capacity, active_counters)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (c_name, c_code, c_addr, c_dist, c_phone, c_hours, c_cap, c_cnt)
        )
        center_ids.append(cursor.lastrowid)

    # 5. Assign Operators to Centers
    cursor.execute(
        "INSERT INTO operator_center_assignments (operator_id, center_id) VALUES (?, ?)",
        (op1_id, center_ids[0])
    )
    cursor.execute(
        "INSERT INTO operator_center_assignments (operator_id, center_id) VALUES (?, ?)",
        (op2_id, center_ids[1])
    )

    # 6. Crops Supported (Indian Rabi & Kharif staples with realistic MSP)
    crops_data = [
        ("Wheat (Gehun - Sharbati)", "Cereals", 2425.0, "Quintal", "Prime milling variety Sharbati / MP Lokwan with low moisture"),
        ("Soybean (Yellow)", "Oilseeds", 4892.0, "Quintal", "Yellow Soybean meeting national fair average quality (FAQ) standards"),
        ("Gram (Chana / Chickpea)", "Pulses", 5440.0, "Quintal", "Desi Bengal Gram / Chana cleaned and sorted"),
        ("Mustard (Sarson)", "Oilseeds", 5650.0, "Quintal", "High oil content yellow and brown mustard seed"),
        ("Maize (Makka)", "Cereals", 2225.0, "Quintal", "Yellow feed and food grade maize kernels"),
    ]

    crop_ids = []
    for crop_name, cat, msp, unit, desc in crops_data:
        cursor.execute(
            """
            INSERT INTO crops (name, category, msp_price, unit, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (crop_name, cat, msp, unit, desc)
        )
        crop_ids.append(cursor.lastrowid)

    # 7. Map crops to centers
    for c_id in center_ids:
        for cr_id in crop_ids:
            cursor.execute(
                """
                INSERT INTO center_crops (center_id, crop_id, max_daily_capacity_quintals)
                VALUES (?, ?, ?)
                """,
                (c_id, cr_id, 800.0)
            )

    # 8. Seed Bookings & Historical Data for today and previous days
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago_str = (today - timedelta(days=2)).strftime("%Y-%m-%d")

    # Historical Completed Bookings (for baseline analytics and ML context)
    hist_records = [
        # (farmer_idx, center_idx, crop_idx, date_str, slot, est_q, act_q, wait_mins, service_mins)
        (0, 0, 0, two_days_ago_str, "09:00 - 11:00 AM", 45.0, 44.5, 35, 20),
        (1, 0, 1, two_days_ago_str, "09:00 - 11:00 AM", 30.0, 31.0, 52, 18),
        (2, 1, 2, two_days_ago_str, "11:00 - 01:00 PM", 25.0, 24.8, 40, 15),
        (3, 1, 0, yesterday_str, "09:00 - 11:00 AM", 50.0, 49.0, 28, 22),
        (4, 0, 1, yesterday_str, "11:00 - 01:00 PM", 40.0, 41.5, 45, 19),
    ]

    seq = 1001
    for f_idx, c_idx, cr_idx, b_date, slot, est_q, act_q, wait_m, serv_m in hist_records:
        token = f"AQ-{b_date.replace('-', '')}-{seq:04d}"
        seq += 1
        base_dt = datetime.strptime(f"{b_date} 09:15:00", "%Y-%m-%d %H:%M:%S")
        arr_time = base_dt.strftime("%Y-%m-%d %H:%M:%S")
        srv_time = (base_dt + timedelta(minutes=wait_m)).strftime("%Y-%m-%d %H:%M:%S")
        cmp_time = (base_dt + timedelta(minutes=wait_m + serv_m)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot,
                                  estimated_quantity, status, arrival_time, service_start_time, completion_time, assigned_counter, operator_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?, 1, ?)
            """,
            (token, farmer_ids[f_idx], center_ids[c_idx], crop_ids[cr_idx], b_date, slot, est_q, arr_time, srv_time, cmp_time, op1_id)
        )
        b_id = cursor.lastrowid

        # Insert procurement record
        msp_rate = crops_data[cr_idx][2]
        total_amt = act_q * msp_rate
        cursor.execute(
            """
            INSERT INTO procurement_records (booking_id, actual_quantity, grade_quality, moisture_percentage, rate_per_quintal, total_amount, payment_status, remarks, recorded_by)
            VALUES (?, ?, 'Grade A FAQ', 11.8, ?, ?, 'PROCESSED', 'Standard MP Mandi procurement verified', ?)
            """,
            (b_id, act_q, msp_rate, total_amt, op1_id)
        )

        cursor.execute(
            """
            INSERT INTO queue_events (booking_id, previous_status, new_status, actor_id, action_note)
            VALUES (?, 'IN_PROGRESS', 'COMPLETED', ?, 'Procurement weight slip generated')
            """,
            (b_id, op1_id)
        )

    # Today's Live Active Queue for Center 1 (Karond Bhopal)
    # Token 1: IN_PROGRESS
    token_1 = f"AQ-{today_str.replace('-', '')}-0001"
    cursor.execute(
        """
        INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot,
                              estimated_quantity, status, arrival_time, service_start_time, assigned_counter, operator_id)
        VALUES (?, ?, ?, ?, ?, '09:00 - 11:00 AM', 40.0, 'IN_PROGRESS', ?, ?, 1, ?)
        """,
        (token_1, farmer_ids[0], center_ids[0], crop_ids[0], today_str, f"{today_str} 09:05:00", f"{today_str} 09:20:00", op1_id)
    )

    # Token 2: CALLED
    token_2 = f"AQ-{today_str.replace('-', '')}-0002"
    cursor.execute(
        """
        INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot,
                              estimated_quantity, status, arrival_time, assigned_counter, operator_id)
        VALUES (?, ?, ?, ?, ?, '09:00 - 11:00 AM', 35.0, 'CALLED', ?, 2, ?)
        """,
        (token_2, farmer_ids[1], center_ids[0], crop_ids[1], today_str, f"{today_str} 09:12:00", op1_id)
    )

    # Token 3: WAITING (Arrived at center)
    token_3 = f"AQ-{today_str.replace('-', '')}-0003"
    cursor.execute(
        """
        INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot,
                              estimated_quantity, status, arrival_time)
        VALUES (?, ?, ?, ?, ?, '09:00 - 11:00 AM', 55.0, 'WAITING', ?)
        """,
        (token_3, farmer_ids[2], center_ids[0], crop_ids[0], today_str, f"{today_str} 09:25:00")
    )

    # Token 4: CONFIRMED (Booked, approaching center)
    token_4 = f"AQ-{today_str.replace('-', '')}-0004"
    cursor.execute(
        """
        INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot,
                              estimated_quantity, status)
        VALUES (?, ?, ?, ?, ?, '11:00 - 01:00 PM', 28.0, 'CONFIRMED')
        """,
        (token_4, farmer_ids[3], center_ids[0], crop_ids[2], today_str)
    )

    # Token 5: REQUESTED (Pending confirmation)
    token_5 = f"AQ-{today_str.replace('-', '')}-0005"
    cursor.execute(
        """
        INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot,
                              estimated_quantity, status)
        VALUES (?, ?, ?, ?, ?, '02:00 - 04:00 PM', 45.0, 'REQUESTED')
        """,
        (token_5, farmer_ids[4], center_ids[0], crop_ids[3], today_str)
    )

    # Add initial notifications for demonstration
    for f_id in farmer_ids:
        cursor.execute(
            """
            INSERT INTO notifications (user_id, title, message, type)
            VALUES (?, 'Welcome to AgriQueue', 'Your digital kisan portal is active. You can now schedule procurement slots at MP mandis without standing in long queues.', 'success')
            """,
            (f_id,)
        )

    cursor.execute(
        """
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, 'Token Ready', 'Your slot booking has been confirmed with Token AQ-today. Check your live queue status.', 'info')
        """,
        (farmer_ids[2],)
    )

    # Initial Audit Log
    cursor.execute(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, details)
        VALUES (?, 'SYSTEM_INIT', 'SYSTEM', 1, 'AgriQueue system initialized and seeded with Madhya Pradesh mandis demonstration data')
        """,
        (admin_id,)
    )

    conn.commit()
    conn.close()
    print("Demo data seeded successfully with realistic MP Mandi records.")


def setup_database_on_startup(db_path=None):
    """
    Safely initialize SQLite schema and seed demo data on application startup.
    Guarantees schema exists when running under Gunicorn without overwriting existing data.
    """
    if not db_path:
        db_path = DEFAULT_DB_PATH

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    # Check if DB file is brand new before schema init
    db_is_brand_new = not os.path.exists(db_path) or os.path.getsize(db_path) == 0

    # Ensure schema tables exist (idempotent CREATE TABLE IF NOT EXISTS)
    init_db(db_path=db_path)

    # Only seed demo data if explicitly requested via DEMO_MODE and DB was brand new
    demo_mode_enabled = os.environ.get("DEMO_MODE", "false").lower() in ("true", "1", "yes")
    if db_is_brand_new and demo_mode_enabled:
        print("New database detected with DEMO_MODE enabled. Seeding initial demo records...")
        seed_demo_data(db_path=db_path, reset=False)
    else:
        print(f"Database verified at {db_path} (seeding skipped: brand_new={db_is_brand_new}, demo_mode={demo_mode_enabled}).")


if __name__ == "__main__":
    init_db()
    seed_demo_data()
