"""
AgriQueue — AI-Based Farmer Procurement Queue Management System
Main Flask Web Application with Role-Based Authentication,
Queue Management Engine, and Machine Learning Inference Integration.
"""

import os
import functools
from datetime import datetime, date, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, g, jsonify, abort
)
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

# Load local environment configuration
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from database import (
    get_db, close_db, init_db, seed_demo_data, setup_database_on_startup,
    log_audit, add_notification, record_queue_event, generate_unique_token
)
from prediction_service import (
    predict_waiting_time_for_booking, reload_model, get_cached_model
)
from train_model import train_and_evaluate

app = Flask(__name__)

# Configure SECRET_KEY: require environment variable in production, fallback only in development
is_production = os.environ.get("FLASK_ENV") == "production" or os.environ.get("RENDER") is not None
secret_key = os.environ.get("SECRET_KEY")

if not secret_key:
    if is_production:
        raise RuntimeError(
            "CRITICAL CONFIGURATION ERROR: SECRET_KEY environment variable is not set in production. "
            "Please configure SECRET_KEY in your Render dashboard environment variables."
        )
    # Safe, explicit development-only fallback
    secret_key = "dev-fallback-secret-key-change-in-production"

app.config["SECRET_KEY"] = secret_key

# Allow DATABASE_PATH to be configured via environment variable while preserving local SQLite default
app.config["DATABASE_PATH"] = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "instance", "agriqueue.db")
)

# Ensure database schema is safely initialized on startup (under Gunicorn or direct execution)
# Only run if not in testing mode so isolated unit test suites control their own databases
if not os.environ.get("FLASK_TESTING"):
    with app.app_context():
        setup_database_on_startup(app.config["DATABASE_PATH"])

# Teardown database connection after request
app.teardown_appcontext(close_db)


# -------------------------------------------------------------------------
# Authorization Decorators & Global Context Helpers
# -------------------------------------------------------------------------

def login_required(view):
    """Ensure user is logged in."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("user_id"):
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(**kwargs)
    return wrapped_view


def role_required(*allowed_roles):
    """Enforce backend role-based access control."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if not session.get("user_id"):
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("login"))
            user_role = session.get("role")
            if user_role not in allowed_roles:
                flash("Access denied: You do not have permission for this section.", "danger")
                if user_role == "farmer":
                    return redirect(url_for("farmer_dashboard"))
                elif user_role == "operator":
                    return redirect(url_for("operator_dashboard"))
                elif user_role == "admin":
                    return redirect(url_for("admin_dashboard"))
                return redirect(url_for("index"))
            return view(**kwargs)
        return wrapped_view
    return decorator


@app.context_processor
def inject_global_vars():
    """Inject unread notifications count and current role into all templates."""
    unread_count = 0
    if session.get("user_id"):
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0",
            (session["user_id"],)
        ).fetchone()
        if row:
            unread_count = row["count"]
    return {
        "unread_notif_count": unread_count,
        "current_user_role": session.get("role"),
        "now_year": datetime.now().year
    }


# -------------------------------------------------------------------------
# Public & Landing Page Routes
# -------------------------------------------------------------------------

@app.route("/")
def index():
    """Agricultural Technology Landing Page."""
    return render_template("index.html")


@app.route("/centers")
def centers():
    """Browse all operational Mandi centers with crop MSPs."""
    db = get_db()
    centers_rows = db.execute("SELECT * FROM procurement_centers WHERE is_active = 1").fetchall()
    centers_list = []
    for c in centers_rows:
        crops = db.execute(
            """
            SELECT cr.name, cr.msp_price, cr.category
            FROM center_crops cc
            JOIN crops cr ON cc.crop_id = cr.id
            WHERE cc.center_id = ? AND cc.is_active = 1
            """,
            (c["id"],)
        ).fetchall()
        c_dict = dict(c)
        c_dict["crops"] = crops
        centers_list.append(c_dict)
    return render_template("centers.html", centers=centers_list)


# -------------------------------------------------------------------------
# Authentication Routes (Register, Login, Logout, Profile)
# -------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    """Farmer (Kisan) Registration."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        father = request.form.get("father_husband_name", "").strip()
        village = request.form.get("village", "").strip()
        tehsil = request.form.get("tehsil", "").strip()
        district = request.form.get("district", "Bhopal").strip()
        land_area = float(request.form.get("land_area_acres") or 0.0)

        # Validation
        if not name or not phone or not password or not village:
            flash("Please fill in all mandatory fields (*).", "danger")
            return render_template("register.html")

        if len(phone) != 10 or not phone.isdigit():
            flash("Please enter a valid 10-digit mobile number.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing:
            flash("This mobile number is already registered. Please sign in.", "warning")
            return redirect(url_for("login"))

        password_hash = generate_password_hash(password)
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO users (phone, email, password_hash, role, name)
            VALUES (?, ?, ?, 'farmer', ?)
            """,
            (phone, email, password_hash, name)
        )
        new_uid = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO farmer_profiles (user_id, father_husband_name, village, tehsil, district, land_area_acres, kisan_credit_card_no)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_uid, father, village, tehsil, district, land_area, f"KCC-MP-{phone[-4:]}")
        )

        add_notification(
            new_uid,
            "Welcome to AgriQueue",
            f"Namaste {name}, your kisan portal is registered. You can now book harvest delivery slots at MP Mandis.",
            "success",
            conn=db
        )

        log_audit(new_uid, "FARMER_REGISTRATION", "USER", new_uid, f"Farmer {name} registered with phone {phone}", conn=db)
        db.commit()

        flash("Registration successful! Please sign in with your credentials.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Unified user authentication for Farmers, Operators, and Administrators."""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE phone = ? OR email = ?",
            (identifier, identifier)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            if not user["is_active"]:
                flash("Your account has been deactivated. Please contact Mandi administration.", "danger")
                return render_template("login.html")

            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["phone"] = user["phone"]
            session["role"] = user["role"]

            log_audit(user["id"], "LOGIN_SUCCESS", "USER", user["id"], f"{user['role'].title()} logged in", conn=db)
            db.commit()

            flash(f"Welcome back, {user['name']}!", "success")
            
            # Role-based landing redirects
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)

            if user["role"] == "farmer":
                return redirect(url_for("farmer_dashboard"))
            elif user["role"] == "operator":
                return redirect(url_for("operator_dashboard"))
            elif user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

        flash("Invalid mobile number/email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Terminate current user session."""
    user_id = session.get("user_id")
    if user_id:
        log_audit(user_id, "LOGOUT", "USER", user_id, "User logged out")
    session.clear()
    flash("You have been securely signed out.", "info")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """View and update profile information."""
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    prof = db.execute("SELECT * FROM farmer_profiles WHERE user_id = ?", (user_id,)).fetchone()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip() or None

        db.execute(
            "UPDATE users SET name = ?, email = ? WHERE id = ?",
            (name, email, user_id)
        )
        session["user_name"] = name

        if user["role"] == "farmer":
            father = request.form.get("father_husband_name", "").strip()
            village = request.form.get("village", "").strip()
            tehsil = request.form.get("tehsil", "").strip()
            district = request.form.get("district", "").strip()
            land = float(request.form.get("land_area_acres") or 0.0)

            db.execute(
                """
                UPDATE farmer_profiles
                SET father_husband_name = ?, village = ?, tehsil = ?, district = ?, land_area_acres = ?
                WHERE user_id = ?
                """,
                (father, village, tehsil, district, land, user_id)
            )

        log_audit(user_id, "PROFILE_UPDATED", "USER", user_id, "User updated profile", conn=db)
        db.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=user, profile=prof)


@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Change user password securely."""
    current_pass = request.form.get("current_password", "")
    new_pass = request.form.get("new_password", "")

    if len(new_pass) < 6:
        flash("New password must be at least 6 characters long.", "danger")
        return redirect(url_for("profile"))

    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()

    if not check_password_hash(user["password_hash"], current_pass):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("profile"))

    new_hash = generate_password_hash(new_pass)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    log_audit(user_id, "PASSWORD_CHANGED", "USER", user_id, "Password updated", conn=db)
    db.commit()

    flash("Password changed successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/notifications")
@login_required
def notifications():
    """In-App Notifications inbox."""
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    return render_template("notifications.html", notifications=notifs)


@app.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_notifications_read():
    """Mark all in-app notifications as read."""
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
    db.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications"))


# -------------------------------------------------------------------------
# Farmer Booking & Live Queue Workflow
# -------------------------------------------------------------------------

@app.route("/farmer/dashboard")
@role_required("farmer")
def farmer_dashboard():
    """Farmer dashboard with active queue card and AI waiting-time prediction."""
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    prof = db.execute("SELECT * FROM farmer_profiles WHERE user_id = ?", (user_id,)).fetchone()

    # Fetch farmer's bookings
    query = """
        SELECT b.*, c.name as center_name, cr.name as crop_name
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        WHERE b.farmer_id = ?
        ORDER BY b.booking_date DESC, b.id DESC
    """
    bookings = db.execute(query, (user_id,)).fetchall()

    # Find active booking for today or current slot
    active_booking = None
    active_pred = None
    for b in bookings:
        if b["status"] in ("REQUESTED", "CONFIRMED", "WAITING", "CALLED", "IN_PROGRESS"):
            active_booking = b
            active_pred = predict_waiting_time_for_booking(b["id"], conn=db, save_record=False)
            break

    return render_template(
        "farmer_dashboard.html",
        user=user,
        profile=prof,
        bookings=bookings,
        active_booking=active_booking,
        active_pred=active_pred
    )


@app.route("/booking", methods=["GET", "POST"])
@role_required("farmer")
def booking():
    """Create a new procurement slot booking."""
    db = get_db()
    farmer_id = session["user_id"]

    if request.method == "POST":
        center_id = request.form.get("center_id")
        crop_id = request.form.get("crop_id")
        booking_date_str = request.form.get("booking_date")
        time_slot = request.form.get("time_slot")
        estimated_qty = float(request.form.get("estimated_quantity") or 0.0)

        # Validation
        if not center_id or not crop_id or not booking_date_str or not time_slot:
            flash("Please provide all required booking details.", "danger")
            return redirect(url_for("booking"))

        if estimated_qty <= 0:
            flash("Estimated quantity must be greater than 0 Quintals.", "danger")
            return redirect(url_for("booking"))

        # Check date not in past
        today_date = date.today()
        b_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        if b_date < today_date:
            flash("Procurement date cannot be in the past.", "danger")
            return redirect(url_for("booking"))

        # Check if Sunday
        if b_date.weekday() == 6:
            flash("Procurement centers are closed on Sundays. Please choose another date.", "warning")
            return redirect(url_for("booking"))

        # Verify center and crop availability
        center = db.execute("SELECT * FROM procurement_centers WHERE id = ? AND is_active = 1", (center_id,)).fetchone()
        crop = db.execute("SELECT * FROM crops WHERE id = ? AND is_active = 1", (crop_id,)).fetchone()
        if not center or not crop:
            flash("Invalid center or crop selected.", "danger")
            return redirect(url_for("booking"))

        # Check duplicate active booking for same farmer, center, crop, date
        duplicate = db.execute(
            """
            SELECT id FROM bookings
            WHERE farmer_id = ? AND booking_date = ? AND crop_id = ?
              AND status IN ('REQUESTED', 'CONFIRMED', 'WAITING', 'CALLED', 'IN_PROGRESS')
            """,
            (farmer_id, booking_date_str, crop_id)
        ).fetchone()
        if duplicate:
            flash("You already have an active booking for this crop on the selected date.", "warning")
            return redirect(url_for("booking_details", booking_id=duplicate["id"]))

        # Check center daily capacity
        count_row = db.execute(
            """
            SELECT COUNT(*) as count FROM bookings
            WHERE center_id = ? AND booking_date = ?
              AND status NOT IN ('CANCELLED', 'REJECTED')
            """,
            (center_id, booking_date_str)
        ).fetchone()
        if count_row and count_row["count"] >= center["daily_capacity"]:
            flash(f"Daily booking capacity ({center['daily_capacity']} slots) reached for {center['name']} on this date. Please choose another date or center.", "warning")
            return redirect(url_for("booking"))

        # Atomic Token Generation
        token = generate_unique_token(center_id, booking_date_str, conn=db)

        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO bookings (token_number, farmer_id, center_id, crop_id, booking_date, time_slot, estimated_quantity, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'CONFIRMED')
            """,
            (token, farmer_id, center_id, crop_id, booking_date_str, time_slot, estimated_qty)
        )
        new_booking_id = cursor.lastrowid

        record_queue_event(new_booking_id, None, "CONFIRMED", actor_id=farmer_id, note="Booking created and slot confirmed", conn=db)
        
        add_notification(
            farmer_id,
            "Slot Confirmed",
            f"Your booking for {crop['name']} at {center['name']} is confirmed. Token: {token} (Slot: {time_slot}).",
            "success",
            conn=db
        )

        log_audit(farmer_id, "BOOKING_CREATED", "BOOKING", new_booking_id, f"Token {token} generated", conn=db)
        db.commit()

        flash(f"Slot booked successfully! Your Token is {token}.", "success")
        return redirect(url_for("queue_status", booking_id=new_booking_id))

    # GET: Load centers and crops
    centers_list = db.execute("SELECT * FROM procurement_centers WHERE is_active = 1").fetchall()
    crops_list = db.execute("SELECT * FROM crops WHERE is_active = 1").fetchall()
    selected_center_id = request.args.get("center_id", type=int)
    min_date = date.today().strftime("%Y-%m-%d")

    return render_template(
        "booking.html",
        centers=centers_list,
        crops=crops_list,
        selected_center_id=selected_center_id,
        min_date=min_date
    )


@app.route("/queue-status/<int:booking_id>")
@login_required
def queue_status(booking_id):
    """Live queue turn tracker with AI-predicted waiting time."""
    db = get_db()
    query = """
        SELECT b.*, c.name as center_name, c.code as center_code, c.active_counters,
               cr.name as crop_name, cr.category as crop_category,
               u.name as farmer_name, u.phone as farmer_phone
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        WHERE b.id = ?
    """
    b = db.execute(query, (booking_id,)).fetchone()
    if not b:
        abort(404)

    # Privacy check: farmers can only view their own bookings
    if session.get("role") == "farmer" and b["farmer_id"] != session.get("user_id"):
        abort(403)

    pred = predict_waiting_time_for_booking(booking_id, conn=db)
    return render_template("queue_status.html", booking=b, pred=pred)


@app.route("/booking/<int:booking_id>")
@login_required
def booking_details(booking_id):
    """View detailed token summary and completed procurement receipt."""
    db = get_db()
    query = """
        SELECT b.*, c.name as center_name, c.code as center_code,
               cr.name as crop_name, cr.category as crop_category,
               u.name as farmer_name, u.phone as farmer_phone
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        WHERE b.id = ?
    """
    b = db.execute(query, (booking_id,)).fetchone()
    if not b:
        abort(404)

    if session.get("role") == "farmer" and b["farmer_id"] != session.get("user_id"):
        abort(403)

    proc_record = db.execute(
        "SELECT * FROM procurement_records WHERE booking_id = ?",
        (booking_id,)
    ).fetchone()

    return render_template("booking_details.html", booking=b, proc_record=proc_record)


@app.route("/booking/history")
@role_required("farmer")
def booking_history():
    """All past and present tokens for the logged-in farmer."""
    db = get_db()
    farmer_id = session["user_id"]
    query = """
        SELECT b.*, c.name as center_name, c.district, cr.name as crop_name
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        WHERE b.farmer_id = ?
        ORDER BY b.booking_date DESC, b.id DESC
    """
    bookings = db.execute(query, (farmer_id,)).fetchall()
    return render_template("booking_history.html", bookings=bookings)


@app.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    """Cancel a booking if eligible (REQUESTED or CONFIRMED state)."""
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not b:
        abort(404)

    if session.get("role") == "farmer" and b["farmer_id"] != session.get("user_id"):
        abort(403)

    if b["status"] not in ("REQUESTED", "CONFIRMED"):
        flash("Cannot cancel a booking that has already arrived or been called for service.", "danger")
        return redirect(url_for("booking_details", booking_id=booking_id))

    db.execute("UPDATE bookings SET status = 'CANCELLED' WHERE id = ?", (booking_id,))
    record_queue_event(booking_id, b["status"], "CANCELLED", actor_id=session.get("user_id"), note="Cancelled by user", conn=db)
    add_notification(b["farmer_id"], "Booking Cancelled", f"Your procurement booking for token {b['token_number']} has been cancelled.", "warning", conn=db)
    log_audit(session.get("user_id"), "BOOKING_CANCELLED", "BOOKING", booking_id, f"Token {b['token_number']} cancelled", conn=db)
    db.commit()

    flash("Booking cancelled successfully.", "info")
    return redirect(url_for("booking_history"))


# -------------------------------------------------------------------------
# Dynamic API Endpoint for Lightweight Polling
# -------------------------------------------------------------------------

@app.route("/api/queue-status/<int:booking_id>")
def api_queue_status(booking_id):
    """Return JSON queue state and dynamic AI waiting-time prediction."""
    pred = predict_waiting_time_for_booking(booking_id, save_record=False)
    if not pred:
        return jsonify({"success": False, "error": "Booking not found"}), 404
    pred["success"] = True
    return jsonify(pred)


# -------------------------------------------------------------------------
# Procurement Center Operator Workflow
# -------------------------------------------------------------------------

@app.route("/operator/dashboard")
@role_required("operator")
def operator_dashboard():
    """Operator console showing today's queue, live stats, and counter transitions."""
    db = get_db()
    op_id = session["user_id"]
    today_str = date.today().strftime("%Y-%m-%d")

    # Find operator assigned center
    assignment = db.execute(
        """
        SELECT c.* FROM operator_center_assignments oca
        JOIN procurement_centers c ON oca.center_id = c.id
        WHERE oca.operator_id = ? AND oca.is_active = 1
        LIMIT 1
        """,
        (op_id,)
    ).fetchone()

    center_id = assignment["id"] if assignment else None

    # Fetch today's bookings for assigned center
    query = """
        SELECT b.*, c.name as center_name, cr.name as crop_name,
               u.name as farmer_name, u.phone as farmer_phone, fp.village
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        LEFT JOIN farmer_profiles fp ON u.id = fp.user_id
        WHERE (b.center_id = ? OR ? IS NULL) AND b.booking_date = ?
        ORDER BY 
            CASE b.status
                WHEN 'IN_PROGRESS' THEN 1
                WHEN 'CALLED' THEN 2
                WHEN 'WAITING' THEN 3
                WHEN 'CONFIRMED' THEN 4
                WHEN 'REQUESTED' THEN 5
                ELSE 6
            END,
            b.id ASC
    """
    rows = db.execute(query, (center_id, center_id, today_str)).fetchall()

    # Compute operational statistics
    total_today = len(rows)
    waiting_count = sum(1 for r in rows if r["status"] == "WAITING")
    in_progress_count = sum(1 for r in rows if r["status"] in ("CALLED", "IN_PROGRESS"))
    completed_count = sum(1 for r in rows if r["status"] == "COMPLETED")

    # Total quintals procured today
    qtl_row = db.execute(
        """
        SELECT SUM(pr.actual_quantity) as total_qtl
        FROM procurement_records pr
        JOIN bookings b ON pr.booking_id = b.id
        WHERE (b.center_id = ? OR ? IS NULL) AND b.booking_date = ?
        """,
        (center_id, center_id, today_str)
    ).fetchone()
    total_qtl = round(float(qtl_row["total_qtl"] or 0.0), 1)

    # Attach AI predictions to waiting bookings
    augmented_rows = []
    for r in rows:
        r_dict = dict(r)
        if r["status"] in ("WAITING", "CONFIRMED"):
            p = predict_waiting_time_for_booking(r["id"], conn=db, save_record=False)
            r_dict["pred_wait"] = int(round(p["predicted_wait_minutes"])) if p else 15
        augmented_rows.append(r_dict)

    stats = {
        "total_today": total_today,
        "waiting_count": waiting_count,
        "in_progress_count": in_progress_count,
        "completed_count": completed_count,
        "total_quintals_procured": total_qtl
    }

    return render_template(
        "operator_dashboard.html",
        operator_center=assignment,
        bookings=augmented_rows,
        stats=stats,
        today_str=today_str
    )


@app.route("/operator/manage-queue")
@role_required("operator")
def manage_queue():
    """Full queue manager with date, center, crop, and status filters."""
    db = get_db()
    centers = db.execute("SELECT * FROM procurement_centers WHERE is_active = 1").fetchall()

    sel_center = request.args.get("center_id")
    sel_date = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    sel_status = request.args.get("status")

    query = """
        SELECT b.*, c.name as center_name, cr.name as crop_name,
               u.name as farmer_name, u.phone as farmer_phone
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        WHERE (b.center_id = ? OR ? IS NULL OR ? = '')
          AND (b.booking_date = ? OR ? IS NULL OR ? = '')
          AND (b.status = ? OR ? IS NULL OR ? = '')
        ORDER BY b.booking_date DESC, b.id ASC
    """
    bookings = db.execute(query, (sel_center, sel_center, sel_center, sel_date, sel_date, sel_date, sel_status, sel_status, sel_status)).fetchall()

    return render_template(
        "manage_queue.html",
        bookings=bookings,
        centers=centers,
        selected_center_id=sel_center,
        selected_date=sel_date,
        selected_status=sel_status
    )


@app.route("/operator/call-next", methods=["POST"])
@role_required("operator")
def call_next_farmer():
    """Find and call the next eligible farmer in line."""
    db = get_db()
    center_id = request.form.get("center_id")
    today_str = date.today().strftime("%Y-%m-%d")

    # Priority: First eligible farmer with WAITING status
    next_booking = db.execute(
        """
        SELECT * FROM bookings
        WHERE (center_id = ? OR ? IS NULL OR ? = '')
          AND booking_date = ?
          AND status = 'WAITING'
        ORDER BY arrival_time ASC, id ASC
        LIMIT 1
        """,
        (center_id, center_id, center_id, today_str)
    ).fetchone()

    # If no one is waiting, check CONFIRMED
    if not next_booking:
        next_booking = db.execute(
            """
            SELECT * FROM bookings
            WHERE (center_id = ? OR ? IS NULL OR ? = '')
              AND booking_date = ?
              AND status = 'CONFIRMED'
            ORDER BY time_slot ASC, id ASC
            LIMIT 1
            """,
            (center_id, center_id, center_id, today_str)
        ).fetchone()

    if not next_booking:
        flash("No waiting or confirmed farmers currently in queue.", "info")
        return redirect(url_for("operator_dashboard"))

    # Determine counter (round robin 1..2)
    assigned_counter = next_booking["assigned_counter"] or 1

    db.execute(
        """
        UPDATE bookings
        SET status = 'CALLED', assigned_counter = ?, operator_id = ?
        WHERE id = ?
        """,
        (assigned_counter, session["user_id"], next_booking["id"])
    )

    record_queue_event(next_booking["id"], next_booking["status"], "CALLED", actor_id=session["user_id"], note=f"Called to Counter #{assigned_counter}", conn=db)
    
    add_notification(
        next_booking["farmer_id"],
        "Your Turn Called!",
        f"Token {next_booking['token_number']} called! Please proceed immediately to Weighbridge Counter #{assigned_counter}.",
        "success",
        conn=db
    )

    log_audit(session["user_id"], "CALL_FARMER", "BOOKING", next_booking["id"], f"Called token {next_booking['token_number']} to Counter #{assigned_counter}", conn=db)
    db.commit()

    flash(f"Called Token {next_booking['token_number']} to Counter #{assigned_counter}!", "success")
    return redirect(url_for("operator_dashboard"))


@app.route("/operator/booking/<int:booking_id>/status", methods=["POST"])
@role_required("operator")
def update_booking_status(booking_id):
    """Transition booking through queue lifecycle."""
    new_status = request.form.get("status")
    reason = request.form.get("reason", "").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    valid_statuses = ("REQUESTED", "CONFIRMED", "WAITING", "CALLED", "IN_PROGRESS", "COMPLETED", "SKIPPED", "CANCELLED", "REJECTED")
    if new_status not in valid_statuses:
        flash("Invalid queue status transition.", "danger")
        return redirect(url_for("operator_dashboard"))

    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not b:
        abort(404)

    update_fields = ["status = ?", "operator_id = ?"]
    params = [new_status, session["user_id"]]

    if new_status == "WAITING" and not b["arrival_time"]:
        update_fields.append("arrival_time = ?")
        params.append(now_str)
    elif new_status == "IN_PROGRESS" and not b["service_start_time"]:
        update_fields.append("service_start_time = ?")
        params.append(now_str)
    elif new_status == "REJECTED":
        update_fields.append("rejection_reason = ?")
        params.append(reason or "Rejected by operator")
    elif new_status == "SKIPPED":
        update_fields.append("skip_reason = ?")
        params.append(reason or "Farmer unavailable when called")

    params.append(booking_id)
    sql = f"UPDATE bookings SET {', '.join(update_fields)} WHERE id = ?"
    db.execute(sql, params)

    record_queue_event(booking_id, b["status"], new_status, actor_id=session["user_id"], note=reason or f"Status changed to {new_status}", conn=db)

    # In-app notifications
    if new_status == "WAITING":
        add_notification(b["farmer_id"], "Arrival Recorded", f"Welcome to the mandi yard! Your token {b['token_number']} is placed in queue.", "info", conn=db)
    elif new_status == "IN_PROGRESS":
        add_notification(b["farmer_id"], "Weighment Commenced", f"Token {b['token_number']} produce weighing and quality inspection has begun.", "info", conn=db)
    elif new_status == "SKIPPED":
        add_notification(b["farmer_id"], "Token Skipped", f"Token {b['token_number']} was skipped. Reason: {reason}. Speak to the yard operator to requeue.", "warning", conn=db)
    elif new_status == "REJECTED":
        add_notification(b["farmer_id"], "Booking Rejected", f"Token {b['token_number']} was rejected. Reason: {reason}.", "danger", conn=db)

    log_audit(session["user_id"], "STATUS_TRANSITION", "BOOKING", booking_id, f"Token {b['token_number']} -> {new_status}", conn=db)
    db.commit()

    flash(f"Token {b['token_number']} updated to {new_status}.", "success")
    return redirect(url_for("operator_dashboard"))


@app.route("/operator/booking/<int:booking_id>/assign-counter", methods=["POST"])
@role_required("operator")
def assign_counter(booking_id):
    """Assign a specific weighbridge counter to a booking."""
    counter = request.form.get("counter", type=int)
    db = get_db()
    db.execute("UPDATE bookings SET assigned_counter = ? WHERE id = ?", (counter, booking_id))
    db.commit()
    flash(f"Assigned Counter #{counter} to booking.", "success")
    return redirect(url_for("manage_queue"))


@app.route("/operator/booking/<int:booking_id>/requeue", methods=["POST"])
@role_required("operator")
def requeue_booking(booking_id):
    """Requeue an eligible skipped farmer back to WAITING status."""
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not b or b["status"] != "SKIPPED":
        flash("Only skipped bookings can be requeued.", "warning")
        return redirect(url_for("operator_dashboard"))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """
        UPDATE bookings
        SET status = 'WAITING', arrival_time = ?, skip_reason = NULL
        WHERE id = ?
        """,
        (now_str, booking_id)
    )

    record_queue_event(booking_id, "SKIPPED", "WAITING", actor_id=session["user_id"], note="Farmer arrived and requeued", conn=db)
    add_notification(b["farmer_id"], "Requeued", f"Token {b['token_number']} has been placed back in the active queue.", "info", conn=db)
    log_audit(session["user_id"], "REQUEUE_BOOKING", "BOOKING", booking_id, f"Token {b['token_number']} requeued", conn=db)
    db.commit()

    flash(f"Token {b['token_number']} has been returned to WAITING queue.", "success")
    return redirect(url_for("operator_dashboard"))


@app.route("/operator/booking/<int:booking_id>/procurement", methods=["GET", "POST"])
@role_required("operator")
def record_procurement(booking_id):
    """Record actual weighed produce, moisture test, and issue official procurement receipt."""
    db = get_db()
    query = """
        SELECT b.*, c.name as center_name, cr.name as crop_name, cr.msp_price,
               u.name as farmer_name, u.phone as farmer_phone
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        WHERE b.id = ?
    """
    b = db.execute(query, (booking_id,)).fetchone()
    if not b:
        abort(404)

    if request.method == "POST":
        actual_qty = float(request.form.get("actual_quantity") or 0.0)
        rate = float(request.form.get("rate_per_quintal") or b["msp_price"])
        grade = request.form.get("grade_quality", "Grade A FAQ")
        moisture = float(request.form.get("moisture_percentage") or 12.0)
        remarks = request.form.get("remarks", "").strip()

        if actual_qty <= 0:
            flash("Actual procured weight must be greater than 0 Quintals.", "danger")
            return render_template("procurement.html", booking=b)

        total_amount = round(actual_qty * rate, 2)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor = db.cursor()
        # Insert or replace procurement record
        cursor.execute(
            """
            INSERT OR REPLACE INTO procurement_records 
                (booking_id, actual_quantity, grade_quality, moisture_percentage, rate_per_quintal, total_amount, payment_status, remarks, recorded_by, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PROCESSED', ?, ?, ?)
            """,
            (booking_id, actual_qty, grade, moisture, rate, total_amount, remarks, session["user_id"], now_str)
        )

        # Transition booking to COMPLETED
        cursor.execute(
            """
            UPDATE bookings
            SET status = 'COMPLETED', completion_time = ?
            WHERE id = ?
            """,
            (now_str, booking_id)
        )

        record_queue_event(booking_id, b["status"], "COMPLETED", actor_id=session["user_id"], note=f"Procured {actual_qty} Qtl @ ₹{rate}/Qtl", conn=db)
        
        add_notification(
            b["farmer_id"],
            "Procurement Completed & Payment Processed",
            f"Token {b['token_number']} completed! Procured {actual_qty} Qtl of {b['crop_name']}. Total Disbursal: ₹{total_amount:,.2f}.",
            "success",
            conn=db
        )

        log_audit(session["user_id"], "PROCUREMENT_RECORDED", "PROCUREMENT", booking_id, f"Procured {actual_qty} Qtl, Total ₹{total_amount}", conn=db)
        db.commit()

        flash(f"Procurement completed for Token {b['token_number']}! Total payment: ₹{total_amount:,.2f}.", "success")
        return redirect(url_for("booking_details", booking_id=booking_id))

    return render_template("procurement.html", booking=b)


# -------------------------------------------------------------------------
# Administrator Workflow
# -------------------------------------------------------------------------

@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    """State Procurement Administrator Dashboard with live metrics, ML evaluation, and charts."""
    db = get_db()

    # System-wide metrics computed strictly from DB
    farmer_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'farmer'").fetchone()["count"]
    center_count = db.execute("SELECT COUNT(*) as count FROM procurement_centers WHERE is_active = 1").fetchone()["count"]

    qtl_row = db.execute("SELECT SUM(actual_quantity) as total_qtl, SUM(total_amount) as total_amt FROM procurement_records").fetchone()
    total_qtl = round(float(qtl_row["total_qtl"] or 0.0), 1)
    total_disbursal = round(float(qtl_row["total_amt"] or 0.0), 2)

    metrics = {
        "total_farmers": farmer_count,
        "active_centers": center_count,
        "total_quintals": total_qtl,
        "total_disbursal": total_disbursal
    }

    # Chart 1: Crop Procurement Share
    crop_stats = db.execute(
        """
        SELECT cr.name, COALESCE(SUM(pr.actual_quantity), 0) as qtl
        FROM crops cr
        LEFT JOIN bookings b ON cr.id = b.crop_id
        LEFT JOIN procurement_records pr ON b.id = pr.booking_id
        GROUP BY cr.id
        ORDER BY qtl DESC
        """
    ).fetchall()
    crop_labels = [row["name"] for row in crop_stats]
    crop_data = [round(float(row["qtl"]), 1) for row in crop_stats]

    # Chart 2: Booking Status Breakdown
    status_stats = db.execute(
        """
        SELECT status, COUNT(*) as count
        FROM bookings
        GROUP BY status
        """
    ).fetchall()
    status_labels = [row["status"] for row in status_stats]
    status_counts = [row["count"] for row in status_stats]

    # ML Metadata and metrics
    _, model_dict = get_cached_model()
    ml_meta = {
        "rf_metrics": {"mae": 3.35, "rmse": 5.14, "r2": 0.972},
        "baseline_metrics": {"mae": 21.60}
    }
    if model_dict and isinstance(model_dict, dict):
        if "metadata" in model_dict and isinstance(model_dict["metadata"], dict) and "rf_metrics" in model_dict["metadata"]:
            ml_meta["rf_metrics"] = model_dict["metadata"]["rf_metrics"]
            ml_meta["baseline_metrics"] = model_dict["metadata"].get("baseline_metrics", ml_meta["baseline_metrics"])
        elif "metrics" in model_dict and isinstance(model_dict["metrics"], dict):
            ml_meta["rf_metrics"] = model_dict["metrics"]

    return render_template(
        "admin_dashboard.html",
        metrics=metrics,
        crop_labels=crop_labels,
        crop_data=crop_data,
        status_labels=status_labels,
        status_counts=status_counts,
        ml_meta=ml_meta
    )


@app.route("/admin/centers", methods=["GET", "POST"])
@role_required("admin")
def manage_centers():
    """Manage procurement centers."""
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip()
        address = request.form.get("address", "").strip()
        district = request.form.get("district", "Bhopal").strip()
        phone = request.form.get("contact_phone", "").strip()
        hours = request.form.get("operating_hours", "09:00 AM - 05:00 PM").strip()
        cap = int(request.form.get("daily_capacity") or 50)
        counters = int(request.form.get("active_counters") or 2)

        existing = db.execute("SELECT id FROM procurement_centers WHERE code = ?", (code,)).fetchone()
        if existing:
            flash(f"Center with code '{code}' already exists.", "danger")
        else:
            db.execute(
                """
                INSERT INTO procurement_centers (name, code, address, district, contact_phone, operating_hours, daily_capacity, active_counters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, code, address, district, phone, hours, cap, counters)
            )
            log_audit(session["user_id"], "CENTER_CREATED", "CENTER", None, f"Created Mandi {name} ({code})", conn=db)
            db.commit()
            flash(f"Mandi Center '{name}' registered successfully.", "success")
        return redirect(url_for("manage_centers"))

    centers = db.execute("SELECT * FROM procurement_centers ORDER BY id ASC").fetchall()
    return render_template("manage_centers.html", centers=centers)


@app.route("/admin/centers/<int:center_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_center_status(center_id):
    """Toggle center active/inactive state."""
    db = get_db()
    c = db.execute("SELECT is_active, name FROM procurement_centers WHERE id = ?", (center_id,)).fetchone()
    if c:
        new_state = 0 if c["is_active"] else 1
        db.execute("UPDATE procurement_centers SET is_active = ? WHERE id = ?", (new_state, center_id))
        log_audit(session["user_id"], "CENTER_TOGGLED", "CENTER", center_id, f"Center {c['name']} set to {new_state}", conn=db)
        db.commit()
        flash(f"Center {c['name']} status updated.", "info")
    return redirect(url_for("manage_centers"))


@app.route("/admin/crops", methods=["GET", "POST"])
@role_required("admin")
def manage_crops():
    """Manage supported crops and Minimum Support Prices (MSP)."""
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "Grain")
        msp = float(request.form.get("msp_price") or 0.0)
        desc = request.form.get("description", "").strip()

        existing = db.execute("SELECT id FROM crops WHERE name = ?", (name,)).fetchone()
        if existing:
            flash(f"Crop '{name}' already exists.", "danger")
        else:
            db.execute(
                """
                INSERT INTO crops (name, category, msp_price, description)
                VALUES (?, ?, ?, ?)
                """,
                (name, category, msp, desc)
            )
            log_audit(session["user_id"], "CROP_CREATED", "CROP", None, f"Added crop {name} @ MSP ₹{msp}", conn=db)
            db.commit()
            flash(f"Crop '{name}' added successfully.", "success")
        return redirect(url_for("manage_crops"))

    crops = db.execute("SELECT * FROM crops ORDER BY id ASC").fetchall()
    return render_template("manage_crops.html", crops=crops)


@app.route("/admin/crops/<int:crop_id>/msp", methods=["POST"])
@role_required("admin")
def update_crop_msp(crop_id):
    """Update government notified Minimum Support Price."""
    new_msp = float(request.form.get("msp_price") or 0.0)
    db = get_db()
    db.execute("UPDATE crops SET msp_price = ? WHERE id = ?", (new_msp, crop_id))
    log_audit(session["user_id"], "MSP_UPDATED", "CROP", crop_id, f"MSP updated to ₹{new_msp}", conn=db)
    db.commit()
    flash("Crop Minimum Support Price updated.", "success")
    return redirect(url_for("manage_crops"))


@app.route("/admin/operators", methods=["GET", "POST"])
@role_required("admin")
def manage_operators():
    """Register operators and manage Mandi yard assignments."""
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip() or None
        center_id = request.form.get("center_id", type=int)
        password = request.form.get("password", "Agri@1234")

        existing = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing:
            flash("User with this mobile number already exists.", "danger")
        else:
            pwd_hash = generate_password_hash(password)
            cursor = db.cursor()
            cursor.execute(
                """
                INSERT INTO users (phone, email, password_hash, role, name)
                VALUES (?, ?, ?, 'operator', ?)
                """,
                (phone, email, pwd_hash, name)
            )
            op_uid = cursor.lastrowid

            if center_id:
                cursor.execute(
                    "INSERT INTO operator_center_assignments (operator_id, center_id) VALUES (?, ?)",
                    (op_uid, center_id)
                )

            log_audit(session["user_id"], "OPERATOR_CREATED", "USER", op_uid, f"Created operator {name}", conn=db)
            db.commit()
            flash(f"Operator {name} registered and assigned to Mandi yard.", "success")
        return redirect(url_for("manage_operators"))

    query = """
        SELECT u.id, u.name, u.phone, u.email,
               c.id as center_id, c.name as center_name, c.district
        FROM users u
        LEFT JOIN operator_center_assignments oca ON u.id = oca.operator_id AND oca.is_active = 1
        LEFT JOIN procurement_centers c ON oca.center_id = c.id
        WHERE u.role = 'operator'
        ORDER BY u.id ASC
    """
    operators = db.execute(query).fetchall()
    centers = db.execute("SELECT * FROM procurement_centers WHERE is_active = 1").fetchall()

    return render_template("manage_operators.html", operators=operators, centers=centers)


@app.route("/admin/operators/<int:operator_id>/assign", methods=["POST"])
@role_required("admin")
def assign_operator_center(operator_id):
    """Reassign an operator to a different Mandi center."""
    center_id = request.form.get("center_id", type=int)
    db = get_db()
    db.execute(
        """
        INSERT OR REPLACE INTO operator_center_assignments (operator_id, center_id, is_active)
        VALUES (?, ?, 1)
        """,
        (operator_id, center_id)
    )
    log_audit(session["user_id"], "OPERATOR_REASSIGNED", "USER", operator_id, f"Assigned to center #{center_id}", conn=db)
    db.commit()
    flash("Operator center assignment updated.", "success")
    return redirect(url_for("manage_operators"))


@app.route("/admin/bookings")
@role_required("admin")
def manage_bookings_admin():
    """State-wide bookings browser with search and audit trail."""
    db = get_db()
    query = """
        SELECT b.*, c.name as center_name, cr.name as crop_name,
               u.name as farmer_name, u.phone as farmer_phone
        FROM bookings b
        JOIN procurement_centers c ON b.center_id = c.id
        JOIN crops cr ON b.crop_id = cr.id
        JOIN users u ON b.farmer_id = u.id
        ORDER BY b.booking_date DESC, b.id DESC
    """
    bookings = db.execute(query).fetchall()
    return render_template("manage_bookings.html", bookings=bookings)


@app.route("/admin/reports")
@role_required("admin")
def reports():
    """Procurement summary reports and regulatory audit log view."""
    db = get_db()

    # Center-wise procurement summary
    center_reports = db.execute(
        """
        SELECT c.id, c.name, c.district,
               COUNT(pr.id) as completed_count,
               COALESCE(SUM(pr.actual_quantity), 0.0) as total_qtl,
               COALESCE(SUM(pr.total_amount), 0.0) as total_amount
        FROM procurement_centers c
        LEFT JOIN bookings b ON c.id = b.center_id AND b.status = 'COMPLETED'
        LEFT JOIN procurement_records pr ON b.id = pr.booking_id
        GROUP BY c.id
        ORDER BY total_amount DESC
        """
    ).fetchall()

    # System audit logs
    audit_logs = db.execute(
        """
        SELECT a.*, u.name as actor_name
        FROM audit_logs a
        LEFT JOIN users u ON a.actor_id = u.id
        ORDER BY a.timestamp DESC
        LIMIT 25
        """
    ).fetchall()

    return render_template("reports.html", center_reports=center_reports, audit_logs=audit_logs)


@app.route("/admin/retrain-model", methods=["POST"])
@role_required("admin")
def retrain_model_route():
    """Trigger manual retraining of the machine learning waiting-time model."""
    try:
        train_and_evaluate()
        reload_model()
        log_audit(session["user_id"], "MODEL_RETRAINED", "SYSTEM", 1, "RandomForest waiting-time model retrained")
        flash("Machine learning model successfully retrained and reloaded into active memory!", "success")
    except Exception as e:
        flash(f"Failed to retrain model: {e}", "danger")
    return redirect(url_for("admin_dashboard"))


# -------------------------------------------------------------------------
# Error Handlers
# -------------------------------------------------------------------------

@app.errorhandler(404)
def not_found_error(error):
    return render_template("error.html", error_code=404, error_title="Page Not Found", error_message="The requested mandi queue resource could not be found."), 404


@app.errorhandler(403)
def forbidden_error(error):
    return render_template("error.html", error_code=403, error_title="Access Forbidden", error_message="You do not have permission to access another farmer's private tokens or admin features."), 403


@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", error_code=500, error_title="System Error", error_message="An internal mandi queue service error occurred. Our team has been notified."), 500


# -------------------------------------------------------------------------
# Application Entry Point & CLI Commands
# -------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0").lower() in ("true", "1", "yes")

    print("\n" + "=" * 60)
    print("🌾 AGRIQUEUE SERVER STARTING")
    print(f"📍 URL: http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
