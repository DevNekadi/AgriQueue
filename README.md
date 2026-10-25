# AgriQueue — AI-Based Farmer Procurement Queue Management System
### B.Tech Final-Year Major Project | Full-Stack Web Application

![AgriQueue Logo](static/images/logo.svg)

> **"Less Waiting. More Growing."**  
> AgriQueue digitizes and streamlines agricultural procurement queues across Indian Krishi Upaj Mandis (demonstrated in the Madhya Pradesh agricultural context: Bhopal, Sehore, and Berasia). It combines transparent slot booking, atomic queue token issuance, real-time queue tracking, and machine learning-powered waiting-time prediction.

---

## Table of Contents
1. [Project Highlights](#1-project-highlights)
2. [Unique Agricultural Brand Identity](#2-unique-agricultural-brand-identity)
3. [Technology Stack](#3-technology-stack)
4. [Project Structure](#4-project-structure)
5. [Quick Windows PowerShell Setup Guide](#5-quick-windows-powershell-setup-guide)
6. [Demo Login Credentials](#6-demo-login-credentials)
7. [Machine Learning Workflow & Evaluation](#7-machine-learning-workflow--evaluation)
8. [Database Schema & Architecture](#8-database-schema--architecture)
9. [Queue Management Lifecycle](#9-queue-management-lifecycle)
10. [Automated Testing Suite](#10-automated-testing-suite)
11. [Viva Voce Technical Explanation](#11-viva-voce-technical-explanation)
12. [GitHub Upload Instructions](#12-github-upload-instructions)
13. [Production Deployment Guide](#13-production-deployment-guide)
14. [Limitations & Future Roadmap](#14-limitations--future-roadmap)

---

## 1. Project Highlights

- **Dynamic Turn Transparency:** Solves the critical problem of chaotic, unorganized tractor-trolley queues at Mandis during peak harvesting seasons.
- **Real Scikit-Learn Waiting-Time Prediction:** Trained `RandomForestRegressor` estimates the exact minutes until a farmer's service begins, incorporating queue length, declared quantity, active weighbridge counters, arrival time of day, and crop inspection friction.
- **Fail-Safe Heuristic Fallback:** If the ML model is ever missing or offline, a calibrated operational fallback seamlessly steps in without system downtime.
- **Three Distinct User Roles:**
  - 👨‍🌾 **Farmer (Kisan):** Profile management, mandi slot reservation, unique token tracking, dynamic wait time estimation, past procurement weighment slips.
  - 🏢 **Procurement Operator:** Live queue console, "Call Next Farmer" workflow, skip/requeue handling, weighbridge counter assignment, actual weight & moisture % logging, payment slip generation.
  - 🛡️ **Administrator:** System analytics, Mandi center configurations, MSP pricing updates, staff assignments, cross-center booking audit trails, manual ML retraining trigger.
- **Security & Privacy:** Werkzeug secure password hashing, session-based authentication, role-based decorators, parameterized SQLite queries, and privacy checks preventing farmers from viewing other farmers' tokens.

---

## 2. Unique Agricultural Brand Identity

AgriQueue departs completely from generic, purple-gradient SaaS dashboards. Its visual design is intentionally rooted in healthy Indian soil, growing crops, and rural agricultural dignity:

| Color | Hex Code | Purpose |
|---|---|---|
| **Forest Green** | `#214E34` | Primary brand identity & action buttons |
| **Deep Evergreen** | `#153B2A` | Hero backgrounds, headers & footers |
| **Leaf Green** | `#4F8A45` | Positive states, active indicators |
| **Fresh Sprout Green** | `#A8C97A` | Accent badges, progress pathway nodes |
| **Soft Sage** | `#DDE8D3` | Secondary cards, subtle table headers |
| **Warm Ivory** | `#F8F6EC` | Main page background (warm & readable) |
| **Pale Wheat** | `#EEE5C8` | Agricultural accents & info pill badges |
| **Terracotta** | `#B96B45` | Warnings, cancellations, rejections |
| **Dark Soil** | `#44392D` | Primary typography & deep contrast |

---

## 3. Technology Stack

- **Backend:** Python 3.13, Flask 3.1
- **Database:** SQLite 3 (with foreign-key enforcement & atomic token transactions)
- **Machine Learning:** `pandas`, `scikit-learn` (`RandomForestRegressor`, `ColumnTransformer`, `StandardScaler`, `OneHotEncoder`), `joblib`
- **Frontend:** HTML5, CSS3 (Custom Agricultural Design System), Vanilla JavaScript (Polling & Calculations), Bootstrap 5.3 (Grid & Utilities), Lucide Icons, Chart.js
- **Testing:** Python `unittest` framework (19 automated unit & integration tests)

---

## 4. Project Structure

```text
AgriQueue/
│
├── app.py                      # Main Flask web application and all route handlers
├── database.py                 # SQLite connection lifecycle, schema execution, demo seeding
├── schema.sql                  # 12-table relational database schema with constraints & indexes
├── ml_model.py                 # Scikit-learn Pipeline architecture, evaluation & fallback logic
├── train_model.py              # ML dataset generator, training script, and evaluation reporter
├── prediction_service.py       # Live queue feature extraction & model inference integration
├── requirements.txt            # Documented Python dependencies
├── .env.example                # Example environment configuration
├── .gitignore                  # Git exclusions (SQLite db, virtualenvs, joblib artifacts)
├── README.md                   # Complete master documentation and viva guide
│
├── templates/                  # 21 Semantic Jinja2 HTML Templates
│   ├── base.html               # Master layout with agricultural navbar & footer
│   ├── index.html              # Distinctive landing page ("Less Waiting. More Growing.")
│   ├── login.html              # Login with 1-click viva demo credentials
│   ├── register.html           # Kisan registration with land holding & village details
│   ├── farmer_dashboard.html   # Kisan portal with active queue card & AI wait estimate
│   ├── centers.html            # Browse Mandi yards and notified MSP prices
│   ├── booking.html            # Schedule slot with live estimated MSP calculation
│   ├── booking_details.html    # Detailed token view & completed weighment slip
│   ├── queue_status.html       # Dynamic turn tracker with growing plant progress flow
│   ├── booking_history.html    # Tabular list of all tokens with search filter
│   ├── notifications.html      # In-app alerts for token confirmations & calls
│   ├── profile.html            # Kisan profile & password change
│   ├── operator_dashboard.html # Mandi operator console with "Call Next Farmer"
│   ├── manage_queue.html       # Full queue manager with center/crop/date filters
│   ├── procurement.html        # Weighbridge record form (weight, moisture %, payment)
│   ├── admin_dashboard.html    # Analytics dashboard, ML evaluation & Chart.js charts
│   ├── manage_centers.html     # Center creation, active counters & daily capacity
│   ├── manage_crops.html       # Crop management & Minimum Support Price updates
│   ├── manage_operators.html   # Operator registration & yard assignment
│   ├── manage_bookings.html    # State-wide token search & cancellation oversight
│   ├── reports.html            # Official Mandi procurement reports & audit trail
│   └── error.html              # Accessible 404 / 403 / 500 error page
│
├── static/
│   ├── css/
│   │   └── style.css           # Complete agricultural design system & animations
│   ├── js/
│   │   └── script.js           # Lightweight polling (12s interval), live filters & MSP preview
│   └── images/
│       ├── logo.svg            # Original seedling & queue pathway logo
│       └── hero_illustration.svg # Stylized farmland furrow & digital token preview
│
├── tests/
│   ├── test_auth.py            # Registration, login, password hashing & role access
│   ├── test_bookings.py        # Token format, booking rules, capacity & cancellation
│   ├── test_queue.py           # Position ranking, state transitions, skip/requeue, weighment
│   ├── test_predictions.py     # ML pipeline, unknown categories, zero ahead, fallback
│   └── probe_routes.py         # End-to-end integration probe across all HTTP endpoints
│
├── instance/
│   └── agriqueue.db            # Local SQLite database (auto-generated)
│
└── ml/
    ├── procurement_training_data.csv # 2,500 historical demonstration records
    └── waiting_time_model.joblib     # Persisted scikit-learn pipeline artifact
```

---

## 5. Quick Windows PowerShell Setup Guide

Follow these exact steps in Windows PowerShell to set up and launch AgriQueue locally:

### Step 1: Open PowerShell and navigate to the project directory
```powershell
cd D:\CrimeVision\AgriQueue
```

### Step 2: Create a Python virtual environment (if not already created)
```powershell
python -m venv .venv
```

### Step 3: Activate the virtual environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 4: Install dependencies
```powershell
pip install -r requirements.txt
```

### Step 5: Configure Environment
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

### Step 6: Initialize and seed the SQLite database
```powershell
python database.py
```
*(Creates 12 tables and seeds realistic MP Mandi records for Bhopal, Sehore, and Berasia).*

### Step 7: Train the Machine Learning Model
```powershell
python train_model.py
```
*(Generates the historical procurement dataset, trains RandomForestRegressor, evaluates against baseline, and saves `ml/waiting_time_model.joblib`).*

### Step 8: Run the Automated Unit Tests
```powershell
python -m unittest discover -s tests -p "test_*.py"
```
*(Runs 19 automated tests covering authentication, bookings, queue transitions, and ML inference).*

### Step 9: Launch the AgriQueue Flask Web Application
```powershell
python app.py
```

### Step 10: Open in your web browser
Open: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 6. Demo Login Credentials

For convenience during viva presentations, the login screen includes 1-click credential buttons. All demo accounts use the standard password: `Agri@1234`.

| Role | Name / Designation | Mobile / Identifier | Password | Access Highlights |
|---|---|---|---|---|
| **Farmer (Kisan)** | Ramesh Kumar Yadav (Berasia) | `9826011111` | `Agri@1234` | Slot booking, live turn tracker, MSP receipts |
| **Farmer (Kisan)** | Suresh Chandra Meena (Phanda) | `9826022222` | `Agri@1234` | Live token waiting in queue |
| **Farmer (Kisan)** | Geeta Devi Rajput (Doraha) | `9826033333` | `Agri@1234` | Waiting in mandi yard, AI wait estimate |
| **Procurement Operator** | Vikram Patel (Officer in Charge) | `9876500001` | `Agri@1234` | Assigned to Karond Mandi Bhopal; Call next farmer, weighbridge recording |
| **Procurement Operator** | Anand Verma (Mandi In-Charge) | `9876500002` | `Agri@1234` | Assigned to Sehore Mandi; Queue management |
| **Administrator** | Shri R. K. Sharma (Director) | `9876543210` | `Agri@1234` | Full state dashboard, centers, crops & MSP, ML retrain |

---

## 7. Machine Learning Workflow & Evaluation

### Objective
Predict the approximate number of **minutes between the current prediction moment and when a farmer's procurement service begins** at the weighbridge counter.

> **Target Definition:** Time until service begins (NOT total time spent at the center).

### Features Used at Prediction Time
1. `farmers_ahead`: Number of eligible farmers ahead in queue.
2. `crop_name`: Crop variety (`Wheat (Sharbati)`, `Soybean`, `Gram`, `Mustard`, `Maize`) — handled via `OneHotEncoder(handle_unknown='ignore')`.
3. `estimated_quantity`: Declared produce in quintals.
4. `active_counters`: Number of operational weighbridges at that center.
5. `arrival_hour`: Current hour of arrival (9 to 16, with peak rush between 10 AM and 1 PM).
6. `day_of_week`: Day of the week (Monday to Saturday).
7. `center_total_load_quintals`: Total pending tonnage waiting in the mandi yard.

### Architecture
- **Preprocessing:** Scikit-learn `ColumnTransformer` with `StandardScaler` on numerical features and `OneHotEncoder` on crop categories.
- **Regressor:** `RandomForestRegressor(n_estimators=100, max_depth=12, min_samples_split=4, min_samples_leaf=2, random_state=42)`.
- **Baseline Model:** `DummyRegressor(strategy='mean')` predicting the empirical average wait.

### Evaluation Metrics Comparison

| Metric | Mean Baseline Model | AgriQueue Random Forest Model | Absolute Improvement |
|---|---|---|---|
| **Mean Absolute Error (MAE)** | `21.60 minutes` | **`3.35 minutes`** | **`18.25 minutes reduction`** |
| **Root Mean Squared Error (RMSE)**| `30.86 minutes` | **`5.14 minutes`** | **`25.72 minutes reduction`** |
| **R-squared ($R^2$) Score** | `-0.00` | **`0.972`** | High explained variance |
| **Test Set Samples** | 500 records | 500 records | (80/20 train/test split on 2,500 samples) |

*Evaluation note: Demonstration data generated using realistic physical queue parameters reflecting MP mandi loading, weighbridge sampling, and moisture inspection delays.*

### Graceful Fallback
If the model artifact is missing or corrupted, `rule_based_fallback_wait()` provides a safe heuristic:
$$\text{Estimated Wait} = \frac{\text{farmers\_ahead} \times (10.0 + 0.15 \times \text{quantity})}{\text{active\_counters}}$$
The system tags predictions with `source: "AI Model (Random Forest)"` or `"Heuristic Operational Fallback"` for complete transparency.

---

## 8. Database Schema & Architecture

The database is built on normalized SQLite with explicit foreign-key constraints (`PRAGMA foreign_keys = ON;`) across 12 tables:

1. `users`: Authentication records, phone (unique), hashed password, and role (`farmer`, `operator`, `admin`).
2. `farmer_profiles`: KCC number, father/husband name, village, tehsil, district, land area (acres).
3. `procurement_centers`: Mandi yard name, code (unique), operating hours, daily capacity, active counters.
4. `operator_center_assignments`: Operator-to-mandi mapping.
5. `crops`: Supported crop varieties, category, Minimum Support Price (₹/Quintal), FAQ standard.
6. `center_crops`: Center-specific crop capacity mappings.
7. `bookings`: Master booking table with atomic token number (`AQ-YYYYMMDD-XXXX`), status, date, slot, declared load, arrival, service start, and completion timestamps.
8. `procurement_records`: Actual weighed quantity, moisture %, quality grade, rate, total amount (₹), payment status.
9. `queue_events`: Full lifecycle event audit trail (`previous_status` -> `new_status`, actor ID, timestamp, note).
10. `notifications`: In-app farmer and operator alerts with read/unread flags.
11. `prediction_records`: Historical inference telemetry snapshots (predicted minutes, farmers ahead, model version, fallback flag).
12. `audit_logs`: Regulatory system action log for compliance and security traceability.

---

## 9. Queue Management Lifecycle

Bookings follow a strictly enforced status machine:

```text
[REQUESTED]
     │
     ▼ (Operator or Auto-Confirmation)
[CONFIRMED] ── (Farmer may cancel before arrival) ──► [CANCELLED]
     │
     ▼ (Farmer physically reaches Mandi yard gate)
 [WAITING]
     │
     ├─► [SKIPPED] (Absent when called; can be [REQUEUED] back to WAITING)
     │
     ▼ (Operator calls next token to Counter)
  [CALLED]
     │
     ▼ (Tractor enters weighbridge)
[IN_PROGRESS]
     │
     ▼ (Produce weighed, moisture tested, payment slip issued)
[COMPLETED]
```

### Priority Ordering Rule
Dynamic queue positions and "farmers ahead" are calculated dynamically on every query:
1. First: Farmers currently `IN_PROGRESS` or `CALLED` at active counters.
2. Second: Farmers marked `WAITING` in the yard, ordered by `arrival_time ASC, id ASC`.
3. Third: Farmers marked `CONFIRMED` or `REQUESTED` for today, ordered by `time_slot ASC, id ASC`.

---

## 10. Automated Testing Suite

AgriQueue includes 19 automated unit and integration tests located in `tests/`:

- `tests/test_auth.py` (5 tests): Password hashing, farmer registration, duplicate phone rejection, login/logout, unauthorized admin access protection.
- `tests/test_bookings.py` (4 tests): Token generation format (`AQ-YYYYMMDD-XXXX`), valid booking creation, past-date rejection, owner cancellation.
- `tests/test_queue.py` (5 tests): Dynamic queue calculation, operator status transitions, skip and requeue workflow, actual weighment recording and payment calculation.
- `tests/test_predictions.py` (5 tests): Synthetic dataset schema, RandomForest vs Baseline evaluation, handling unseen crop categories, zero farmers ahead immediate turnaround, fallback calculation.

### Run All Tests:
```powershell
python -m unittest discover -s tests -p "test_*.py"
```
**Test Result:** `Ran 19 tests in 6.438s — OK (0 failures, 0 errors).`

---

## 11. Viva Voce Technical Explanation

### Q1: What problem does AgriQueue solve in Indian agriculture?
> **Answer:** In traditional agricultural mandis (like Krishi Upaj Mandis in Madhya Pradesh), farmers arrive without schedule during harvest peaks. This creates massive queues of tractor-trolleys waiting 12 to 36 hours in extreme weather, yard traffic gridlock, and uncertainty. AgriQueue digitizes this process: farmers book a time slot in advance, receive a verified queue token (`AQ-YYYYMMDD-0001`), and see AI-estimated waiting times on their phones so they only arrive when their turn is near.

### Q2: Why use RandomForestRegressor for waiting-time prediction?
> **Answer:** Waiting time in a procurement yard is a non-linear regression problem influenced by multiple tabular factors: the number of farmers ahead, how many weighbridge counters are operating, the crop variety (oilseeds require moisture and oil tests taking longer than cereals), declared tonnage, and peak time of day. Random Forest combines an ensemble of decision trees, handles tabular numerical and categorical features effectively without extreme overfitting, and outperforms linear models on operational queue dynamics.

### Q3: Why is evaluation done with MAE and RMSE rather than "accuracy %"?
> **Answer:** In continuous numerical regression tasks, "accuracy percentage" is mathematically undefined or artificially constructed. Proper regression evaluation requires Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE) expressed in actual minutes. In our evaluation on 500 test records, the mean baseline had an MAE of 21.60 minutes, while our Random Forest model achieved an MAE of 3.35 minutes — proving an 18.25-minute improvement.

### Q4: How is race-condition token duplication prevented?
> **Answer:** Tokens follow the format `AQ-YYYYMMDD-XXXX`. In `database.py`, `generate_unique_token()` queries the current count of bookings for that date within a transaction and checks a database `UNIQUE` constraint on `token_number`. If a collision is ever detected, it sequentially increments until a guaranteed unique token is reserved.

### Q5: How is user data privacy maintained?
> **Answer:** In `app.py`, route handlers verify the session user ID and role. Farmers are strictly prevented from viewing or modifying other farmers' tokens (`abort(403)` is returned if a farmer requests another farmer's token URL). Operator access is restricted to their assigned Mandi center, and all critical actions are tracked in the `audit_logs` table.

---

## 12. GitHub Upload Instructions

To upload this clean, self-contained project to your personal GitHub account:

```powershell
cd D:\CrimeVision\AgriQueue

# Initialize git repository
git init

# Add files (respecting .gitignore which excludes local sqlite db and venvs)
git add .

# Create initial commit
git commit -m "Initial commit: AgriQueue AI-Based Farmer Procurement Queue Management System"

# Rename branch to main
git branch -M main

# Add your GitHub remote repository URL
git remote add origin https://github.com/<your-username>/AgriQueue.git

# Push to GitHub
git push -u origin main
```

---

## 13. Production Deployment Guide (Render)

### Method A: Web Service via Render Dashboard
1. Go to **[Render Dashboard](https://dashboard.render.com)** → Click **New +** → Select **Web Service**.
2. Connect your **`AgriQueue`** GitHub repository.
3. Configure the service settings:
   - **Name:** `agriqueue`
   - **Environment:** `Python 3`
   - **Branch:** `main`
   - **Build Command:** `./build.sh` *(or `pip install -r requirements.txt && python train_model.py`)*
   - **Start Command:** `gunicorn app:app`
4. Configure **Environment Variables** under the Environment tab:
   - `SECRET_KEY`: Set a secure random string (e.g. run `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `FLASK_ENV`: `production`
   - `DEMO_MODE`: `true` *(seeds initial demo mandis & farmers on first launch; set to `false` for clean production)*
   - `DATABASE_PATH`: `instance/agriqueue.db` *(or `/var/data/agriqueue.db` if attaching a Render Persistent Disk)*
5. Click **Create Web Service**. Render executes `./build.sh` (installing dependencies & generating the ML model artifact), safely initializes SQLite schema, and boots Gunicorn on `$PORT`.

### Method B: Render Blueprint (Infrastructure as Code)
The repository includes a pre-configured `render.yaml`. On Render, navigate to **Blueprints** → Connect your repository → Render will automatically configure the build command, start command, and generate a secure `SECRET_KEY`.

---

## 14. Limitations & Future Roadmap

- **SMS / WhatsApp Gateway:** In-app notifications are implemented. Integrating Twilio or an Indian DLT-compliant SMS gateway (CDAC / NIC Kisan SMS) for non-smartphone feature phones is the next logical extension.
- **Weighbridge IoT Integration:** Automatic capture of weighbridge gross and tare weights over RS-232 / Modbus serial interface to eliminate manual weight entry by operators.
- **Production Database Migration:** SQLite is lightweight and optimal for local student demonstrations; high-volume multi-mandi statewide concurrency would benefit from PostgreSQL with row-level locking.
- **Vernacular Language Support:** The application architecture is ready for complete Hindi (`hi`) and regional dialect localization via Flask-Babel.

---

*Academic Major Project • B.Tech Final Year • Demonstration Agricultural Queue System*
