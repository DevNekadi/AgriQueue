-- AgriQueue: AI-Based Farmer Procurement Queue Management System
-- SQLite Schema with Foreign Key Support

PRAGMA foreign_keys = ON;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone VARCHAR(15) UNIQUE NOT NULL,
    email VARCHAR(100),
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL CHECK(role IN ('farmer', 'operator', 'admin')),
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- 2. Farmer Profiles
CREATE TABLE IF NOT EXISTS farmer_profiles (
    user_id INTEGER PRIMARY KEY,
    father_husband_name VARCHAR(100),
    village VARCHAR(100),
    tehsil VARCHAR(100),
    district VARCHAR(100) DEFAULT 'Bhopal',
    state VARCHAR(100) DEFAULT 'Madhya Pradesh',
    land_area_acres REAL DEFAULT 0.0,
    kisan_credit_card_no VARCHAR(50),
    preferred_language VARCHAR(10) DEFAULT 'en',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. Procurement Centers
CREATE TABLE IF NOT EXISTS procurement_centers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(150) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    address TEXT NOT NULL,
    district VARCHAR(100) NOT NULL,
    state VARCHAR(100) DEFAULT 'Madhya Pradesh',
    contact_phone VARCHAR(15),
    operating_hours VARCHAR(50) DEFAULT '09:00 AM - 05:00 PM',
    daily_capacity INTEGER DEFAULT 50,
    active_counters INTEGER DEFAULT 2,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Operator to Center Assignments
CREATE TABLE IF NOT EXISTS operator_center_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id INTEGER NOT NULL,
    center_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (center_id) REFERENCES procurement_centers(id) ON DELETE CASCADE,
    UNIQUE(operator_id, center_id)
);

-- 5. Crops Table
CREATE TABLE IF NOT EXISTS crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) DEFAULT 'Grain',
    msp_price REAL DEFAULT 0.0,
    unit VARCHAR(20) DEFAULT 'Quintal',
    description TEXT,
    is_active BOOLEAN DEFAULT 1
);

-- 6. Center Crops Availability
CREATE TABLE IF NOT EXISTS center_crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    center_id INTEGER NOT NULL,
    crop_id INTEGER NOT NULL,
    max_daily_capacity_quintals REAL DEFAULT 500.0,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (center_id) REFERENCES procurement_centers(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(id) ON DELETE CASCADE,
    UNIQUE(center_id, crop_id)
);

-- 7. Bookings Table
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_number VARCHAR(30) UNIQUE NOT NULL,
    farmer_id INTEGER NOT NULL,
    center_id INTEGER NOT NULL,
    crop_id INTEGER NOT NULL,
    booking_date DATE NOT NULL,
    time_slot VARCHAR(30) NOT NULL,
    estimated_quantity REAL NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'REQUESTED' 
        CHECK(status IN ('REQUESTED', 'CONFIRMED', 'WAITING', 'CALLED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'CANCELLED', 'REJECTED')),
    rejection_reason TEXT,
    skip_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    arrival_time TIMESTAMP,
    service_start_time TIMESTAMP,
    completion_time TIMESTAMP,
    assigned_counter INTEGER,
    operator_id INTEGER,
    FOREIGN KEY (farmer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (center_id) REFERENCES procurement_centers(id) ON DELETE RESTRICT,
    FOREIGN KEY (crop_id) REFERENCES crops(id) ON DELETE RESTRICT,
    FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 8. Procurement Records
CREATE TABLE IF NOT EXISTS procurement_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL UNIQUE,
    actual_quantity REAL NOT NULL,
    grade_quality VARCHAR(20) DEFAULT 'Grade A',
    moisture_percentage REAL DEFAULT 12.0,
    rate_per_quintal REAL NOT NULL,
    total_amount REAL NOT NULL,
    payment_status VARCHAR(30) DEFAULT 'PENDING_DISBURSAL'
        CHECK(payment_status IN ('PENDING_DISBURSAL', 'PROCESSED', 'COMPLETED')),
    remarks TEXT,
    recorded_by INTEGER NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
);

-- 9. Queue Event History
CREATE TABLE IF NOT EXISTS queue_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    previous_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    actor_id INTEGER,
    action_note TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 10. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(30) DEFAULT 'info',
    is_read BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 11. Prediction Records Table (for evaluation & monitoring)
CREATE TABLE IF NOT EXISTS prediction_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    prediction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    queue_position INTEGER NOT NULL,
    farmers_ahead INTEGER NOT NULL,
    predicted_wait_minutes REAL NOT NULL,
    model_version VARCHAR(50) DEFAULT 'random_forest_v1',
    is_fallback BOOLEAN DEFAULT 0,
    features_snapshot_json TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

-- 12. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id INTEGER,
    details TEXT,
    ip_address VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Indexes for fast queue and booking queries
CREATE INDEX IF NOT EXISTS idx_bookings_center_date_status ON bookings(center_id, booking_date, status);
CREATE INDEX IF NOT EXISTS idx_bookings_farmer ON bookings(farmer_id);
CREATE INDEX IF NOT EXISTS idx_bookings_token ON bookings(token_number);
CREATE INDEX IF NOT EXISTS idx_queue_events_booking ON queue_events(booking_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read);
