from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from db import get_connection, init_db, get_campus_location, get_student_profile
from psycopg2.extras import RealDictCursor
import hashlib
import math
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.jinja_env.globals['enumerate'] = enumerate


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


from datetime import date as date_cls, timedelta
from collections import Counter


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_analytics(user_id):
    """Compute full attendance analytics for a student."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # All attendance records for this student
    cur.execute("""
        SELECT DATE(time) AS att_date,
               EXTRACT(DOW FROM time)::int AS dow
        FROM attendance
        WHERE user_id = %s
        ORDER BY time ASC
    """, (user_id,))
    my_records = cur.fetchall()

    # Total global school days (any student present = school day)
    cur.execute("SELECT COUNT(DISTINCT DATE(time)) AS cnt FROM attendance")
    total_days = int((cur.fetchone() or {}).get('cnt') or 0)

    # Per-subject stats
    cur.execute("""
        SELECT s.name,
               COUNT(DISTINCT DATE(a_all.time))                                         AS subject_total,
               COUNT(DISTINCT CASE WHEN a_me.user_id = %s THEN DATE(a_me.time) END)    AS student_present
        FROM subjects s
        JOIN student_subjects ss ON s.id = ss.subject_id AND ss.user_id = %s
        LEFT JOIN attendance a_all ON s.id = a_all.subject_id
        LEFT JOIN attendance a_me  ON s.id = a_me.subject_id AND a_me.user_id = %s
        GROUP BY s.id, s.name
        ORDER BY s.name
    """, (user_id, user_id, user_id))
    subject_rows = cur.fetchall()
    cur.close()
    conn.close()

    # ── Basic stats ──
    present_dates = sorted(set(str(r['att_date']) for r in my_records))
    total_present = len(present_dates)
    absent = max(0, total_days - total_present)
    pct = round((total_present / total_days * 100) if total_days > 0 else 0, 1)

    # ── Risk level ──
    if pct >= 80:
        risk_level, risk_class = 'SAFE', 'safe'
    elif pct >= 70:
        risk_level, risk_class = 'WARNING', 'warning'
    else:
        risk_level, risk_class = 'DANGER', 'danger'

    # ── Streaks ──
    current_streak = longest_streak = 0
    if present_dates:
        dates = [date_cls.fromisoformat(d) for d in present_dates]
        # Longest streak
        lng = cs = 1
        for i in range(1, len(dates)):
            cs = cs + 1 if (dates[i] - dates[i-1]).days == 1 else 1
            lng = max(lng, cs)
        longest_streak = lng
        # Current streak from the end
        cs = 1
        for i in range(len(dates)-1, 0, -1):
            if (dates[i] - dates[i-1]).days == 1:
                cs += 1
            else:
                break
        # Only active if last attendance is today or yesterday
        current_streak = cs if (date_cls.today() - dates[-1]).days <= 1 else 0

    # ── Trend (density comparison first half vs second half) ──
    trend = 'stable'
    if len(present_dates) >= 6:
        dates_list = [date_cls.fromisoformat(d) for d in present_dates]
        mid = len(dates_list) // 2
        def density(lst):
            if len(lst) < 2: return float(len(lst))
            return len(lst) / max(1, (lst[-1] - lst[0]).days + 1)
        fd, sd = density(dates_list[:mid]), density(dates_list[mid:])
        if sd > fd * 1.05:   trend = 'improving'
        elif sd < fd * 0.95: trend = 'declining'

    # ── Prediction (next 30 days at same rate) ──
    rate = pct / 100
    future_days = 30
    pred_pct = round(
        ((total_present + rate * future_days) / (total_days + future_days) * 100)
        if (total_days + future_days) > 0 else 0, 1
    )
    high_risk_pred = pred_pct < 75

    # ── Classes needed to reach 75% ──
    classes_needed = 0
    if pct < 75 and total_days > 0:
        needed = (0.75 * total_days - total_present) / 0.25
        classes_needed = max(0, math.ceil(needed))

    # ── Day-of-week pattern ──
    day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    dow_count = Counter(r['dow'] for r in my_records)
    present_by_day = {day_names[i]: int(dow_count.get(i, 0)) for i in range(7)}

    # ── Busiest / lightest attendance days ──
    sorted_days = sorted(present_by_day.items(), key=lambda x: x[1], reverse=True)
    best_day = sorted_days[0][0] if sorted_days and sorted_days[0][1] > 0 else '—'
    low_day  = sorted_days[-1][0] if sorted_days and sorted_days[-1][1] >= 0 else '—'

    # ── Subject-wise ──
    subject_stats = []
    for s in subject_rows:
        t = int(s['subject_total'] or 0)
        p = int(s['student_present'] or 0)
        sp = round((p / t * 100) if t > 0 else 0, 1)
        level = 'strong' if sp >= 85 else ('weak' if sp < 75 else 'ok')
        subject_stats.append({'name': s['name'], 'present': p, 'total': t, 'pct': sp, 'level': level})

    # ── Performance score (0–100) ──
    att_pts     = min(pct, 100) * 0.60          # up to 60
    streak_pts  = min(current_streak / 10, 1.0) * 15  # up to 15
    consist_pts = 25 if pct >= 80 else (20 if pct >= 75 else (12 if pct >= 70 else 5))  # up to 25
    performance_score = round(min(100.0, att_pts + streak_pts + consist_pts), 1)

    return {
        'total_present':    total_present,
        'total_days':       total_days,
        'absent':           absent,
        'attendance_pct':   pct,
        'risk_level':       risk_level,
        'risk_class':       risk_class,
        'current_streak':   current_streak,
        'longest_streak':   longest_streak,
        'trend':            trend,
        'predicted_pct':    pred_pct,
        'high_risk_pred':   high_risk_pred,
        'classes_needed':   classes_needed,
        'subject_stats':    subject_stats,
        'present_by_day':   present_by_day,
        'best_day':         best_day,
        'low_day':          low_day,
        'performance_score': performance_score,
    }


# ─────────────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return redirect(url_for("login"))


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and user["password"] == hash_password(password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "student_dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")
        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("register.html")
        if role not in ("admin", "student"):
            role = "student"
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                        (username, hash_password(password), role))
            conn.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception:
            conn.rollback()
            flash("Username already exists.", "error")
        finally:
            cur.close()
            conn.close()
    return render_template("register.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "student_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


# ── Student: Profile Setup (first-login) ─────────────────────────────────────

@app.route("/setup_profile", methods=["GET", "POST"])
def setup_profile():
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))
    # Already complete → skip to dashboard
    profile = get_student_profile(session["user_id"])
    if profile and profile.get("is_complete"):
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        degree = request.form.get("degree", "").strip()
        branch = request.form.get("branch", "").strip()
        specialization = request.form.get("specialization", "").strip()
        year = request.form.get("year", "").strip()
        section = request.form.get("section", "").strip()
        if not all([full_name, degree, branch, year, section]):
            flash("Please fill all required fields.", "error")
            return render_template("student_profile.html", profile=profile or {})
        conn = get_connection()
        cur = conn.cursor()
        if profile:
            cur.execute("""
                UPDATE student_profiles
                SET full_name=%s, degree=%s, branch=%s, specialization=%s,
                    year=%s, section=%s, is_complete=TRUE, updated_at=CURRENT_TIMESTAMP
                WHERE user_id=%s
            """, (full_name, degree, branch, specialization, year, section, session["user_id"]))
        else:
            cur.execute("""
                INSERT INTO student_profiles
                    (user_id, full_name, degree, branch, specialization, year, section, is_complete)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            """, (session["user_id"], full_name, degree, branch, specialization, year, section))
        conn.commit()
        cur.close()
        conn.close()
        flash("Profile saved! Welcome to AttendX.", "success")
        return redirect(url_for("student_dashboard"))

    return render_template("student_profile.html", profile=profile or {})


# ── Student: Profile & Password Settings ──────────────────────────────────────

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("login"))
    conn = get_connection()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        degree = request.form.get("degree", "").strip()
        branch = request.form.get("branch", "").strip()
        specialization = request.form.get("specialization", "").strip()
        year = request.form.get("year", "").strip()
        section = request.form.get("section", "").strip()
        cur = conn.cursor()
        cur.execute("SELECT id FROM student_profiles WHERE user_id = %s", (session["user_id"],))
        if cur.fetchone():
            cur.execute("""
                UPDATE student_profiles
                SET full_name=%s, degree=%s, branch=%s, specialization=%s,
                    year=%s, section=%s, is_complete=TRUE, updated_at=CURRENT_TIMESTAMP
                WHERE user_id=%s
            """, (full_name, degree, branch, specialization, year, section, session["user_id"]))
        else:
            cur.execute("""
                INSERT INTO student_profiles
                    (user_id, full_name, degree, branch, specialization, year, section, is_complete)
                VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)
            """, (session["user_id"], full_name, degree, branch, specialization, year, section))
        conn.commit()
        cur.close()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM student_profiles WHERE user_id = %s", (session["user_id"],))
    student_profile = cur.fetchone() or {}
    cur.close()
    conn.close()
    return render_template("profile.html", profile=student_profile)


@app.route("/change_password", methods=["POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("login"))
    old_password = request.form.get("old_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not old_password or not new_password:
        flash("All password fields are required.", "error")
        return redirect(request.referrer or url_for("profile"))
    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(request.referrer or url_for("profile"))
    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(request.referrer or url_for("profile"))
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT password FROM users WHERE id = %s", (session["user_id"],))
    user = cur.fetchone()
    if user and user["password"] == hash_password(old_password):
        cur.execute("UPDATE users SET password=%s WHERE id=%s",
                    (hash_password(new_password), session["user_id"]))
        conn.commit()
        flash("Password changed successfully!", "success")
    else:
        flash("Incorrect current password.", "error")
    cur.close()
    conn.close()
    return redirect(request.referrer or url_for("profile"))


# ── Admin: Dashboard ──────────────────────────────────────────────────────────

@app.route("/admin_dashboard")
def admin_dashboard():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("login"))
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, username, role FROM users ORDER BY id")
    users = cur.fetchall()
    cur.execute("""
        SELECT u.username, a.time, a.status, a.latitude, a.longitude,
               s.name AS subject_name
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN subjects s ON a.subject_id = s.id
        ORDER BY a.time DESC
        LIMIT 50
    """)
    records = cur.fetchall()
    cur.close()
    conn.close()
    campus = get_campus_location()
    return render_template("admin_dashboard.html", users=users, records=records, campus=campus)


# ── Admin: Set Campus Location ────────────────────────────────────────────────

@app.route("/set_location", methods=["POST"])
def set_location():
    if "user_id" not in session or session.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.get_json()
    name = data.get("name", "College Campus").strip() or "College Campus"
    lat, lon, radius = data.get("latitude"), data.get("longitude"), data.get("radius", 100)
    if lat is None or lon is None:
        return jsonify({"success": False, "message": "Latitude and longitude are required."}), 400
    try:
        lat, lon, radius = float(lat), float(lon), int(radius)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid coordinate values."}), 400
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM campus_location ORDER BY id LIMIT 1")
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE campus_location
            SET name=%s, latitude=%s, longitude=%s, radius=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (name, lat, lon, radius, existing[0]))
    else:
        cur.execute("INSERT INTO campus_location (name, latitude, longitude, radius) VALUES (%s,%s,%s,%s)",
                    (name, lat, lon, radius))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "message": f"Location '{name}' saved successfully!"})


@app.route("/api/campus_location")
def api_campus_location():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    campus = get_campus_location()
    if not campus:
        return jsonify({"error": "No location set"}), 404
    return jsonify({"name": campus["name"], "latitude": campus["latitude"],
                    "longitude": campus["longitude"], "radius": campus["radius"]})


# ── Admin: Subject Management ─────────────────────────────────────────────────

@app.route("/manage_subjects", methods=["GET", "POST"])
def manage_subjects():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_subject":
            name = request.form.get("name", "").strip()
            total_hours = request.form.get("total_hours", "0")
            if not name:
                flash("Subject name is required.", "error")
            else:
                try:
                    total_hours = int(total_hours)
                    cur.execute("INSERT INTO subjects (name, total_hours) VALUES (%s, %s)",
                                (name, total_hours))
                    conn.commit()
                    flash(f"Subject '{name}' added successfully.", "success")
                except Exception:
                    conn.rollback()
                    flash("Subject name already exists.", "error")

    cur.execute("SELECT * FROM subjects ORDER BY name")
    subjects = cur.fetchall()
    cur.execute("SELECT id, username FROM users WHERE role='student' ORDER BY username")
    students = cur.fetchall()

    # For each subject, get assigned student ids
    cur.execute("SELECT subject_id, user_id FROM student_subjects")
    assignments_raw = cur.fetchall()
    assigned_map = {}  # subject_id -> set of user_ids
    for row in assignments_raw:
        sid = row["subject_id"]
        if sid not in assigned_map:
            assigned_map[sid] = set()
        assigned_map[sid].add(row["user_id"])

    cur.close()
    conn.close()
    return render_template("manage_subjects.html", subjects=subjects,
                           students=students, assigned_map=assigned_map)


@app.route("/assign_subject", methods=["POST"])
def assign_subject():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("login"))

    subject_id = request.form.get("subject_id")
    select_all = request.form.get("select_all") == "on"
    student_ids = request.form.getlist("student_ids")

    if not subject_id:
        flash("Please select a subject.", "error")
        return redirect(url_for("manage_subjects"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if select_all:
        cur.execute("SELECT id FROM users WHERE role='student'")
        rows = cur.fetchall()
        student_ids = [str(r["id"]) for r in rows]

    if not student_ids:
        flash("No students selected.", "error")
        cur.close()
        conn.close()
        return redirect(url_for("manage_subjects"))

    inserted = 0
    skipped = 0
    for sid in student_ids:
        try:
            cur.execute("INSERT INTO student_subjects (user_id, subject_id) VALUES (%s, %s)",
                        (int(sid), int(subject_id)))
            conn.commit()
            inserted += 1
        except Exception:
            conn.rollback()
            skipped += 1

    cur.close()
    conn.close()
    flash(f"Assigned to {inserted} student(s). {skipped} already had this subject.", "success")
    return redirect(url_for("manage_subjects"))


@app.route("/unassign_subject", methods=["POST"])
def unassign_subject():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    subject_id = request.form.get("subject_id")
    user_id = request.form.get("user_id")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM student_subjects WHERE subject_id=%s AND user_id=%s",
                (subject_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    flash("Student unassigned from subject.", "success")
    return redirect(url_for("manage_subjects"))


@app.route("/delete_subject/<int:subject_id>", methods=["POST"])
def delete_subject(subject_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM subjects WHERE id=%s", (subject_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Subject deleted.", "success")
    return redirect(url_for("manage_subjects"))


# ── Student: Dashboard ────────────────────────────────────────────────────────

@app.route("/student_dashboard")
def student_dashboard():
    if "user_id" not in session or session.get("role") != "student":
        flash("Access denied.", "error")
        return redirect(url_for("login"))

    # Force profile completion on first login
    profile = get_student_profile(session["user_id"])
    if not profile or not profile.get("is_complete"):
        return redirect(url_for("setup_profile"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT a.time, a.status, a.latitude, a.longitude, s.name AS subject_name
        FROM attendance a
        LEFT JOIN subjects s ON a.subject_id = s.id
        WHERE a.user_id = %s
        ORDER BY a.time DESC
        LIMIT 20
    """, (session["user_id"],))
    records = cur.fetchall()

    # Subjects assigned to this student
    cur.execute("""
        SELECT s.id, s.name, s.total_hours
        FROM subjects s
        JOIN student_subjects ss ON s.id = ss.subject_id
        WHERE ss.user_id = %s
        ORDER BY s.name
    """, (session["user_id"],))
    assigned_subjects = cur.fetchall()

    cur.close()
    conn.close()
    campus = get_campus_location()
    return render_template("student_dashboard.html", records=records, campus=campus,
                           profile=profile, assigned_subjects=assigned_subjects)


@app.route("/analytics")
def analytics():
    if "user_id" not in session or session.get("role") != "student":
        flash("Access denied.", "error")
        return redirect(url_for("login"))

    profile = get_student_profile(session["user_id"])
    if not profile or not profile.get("is_complete"):
        return redirect(url_for("setup_profile"))

    data = compute_analytics(session["user_id"])
    return render_template("student_analytics.html", data=data)


# ── Student: Mark Attendance ──────────────────────────────────────────────────

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.get_json()
    lat = data.get("latitude")
    lon = data.get("longitude")
    subject_id = data.get("subject_id")

    if lat is None or lon is None:
        return jsonify({"success": False, "message": "Location data missing."}), 400
    if not subject_id:
        return jsonify({"success": False, "message": "Please select a subject before marking attendance."}), 400

    campus = get_campus_location()
    if not campus:
        return jsonify({"success": False, "message": "Campus location not configured by admin."}), 500

    distance = haversine_distance(lat, lon, campus["latitude"], campus["longitude"])
    if distance > campus["radius"]:
        return jsonify({
            "success": False,
            "message": f"You are {round(distance, 1)}m away. Must be within {campus['radius']}m of {campus['name']}.",
            "distance": round(distance, 2)
        }), 400

    conn = get_connection()
    cur = conn.cursor()

    # One attendance per subject per day
    cur.execute("""
        SELECT id FROM attendance
        WHERE user_id=%s AND subject_id=%s AND DATE(time)=CURRENT_DATE
    """, (session["user_id"], subject_id))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"success": False, "message": "Attendance already marked for this subject today."}), 409

    cur.execute("""
        INSERT INTO attendance (user_id, status, latitude, longitude, subject_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (session["user_id"], "Present", lat, lon, subject_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "message": "Attendance marked successfully!", "distance": round(distance, 2)})


# ── Admin: View All Attendance ────────────────────────────────────────────────

@app.route("/view_attendance")
def view_attendance():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("login"))
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT u.username, a.time, a.status, a.latitude, a.longitude, s.name AS subject_name
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN subjects s ON a.subject_id = s.id
        ORDER BY a.time DESC
    """)
    records = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("view_attendance.html", records=records)


# ── Admin: User Management ────────────────────────────────────────────────────

@app.route("/add_student", methods=["POST"])
def add_student():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "student")
    if not username or not password:
        flash("Username and password required.", "error")
        return redirect(url_for("admin_dashboard"))
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                    (username, hash_password(password), role))
        conn.commit()
        flash(f"User '{username}' added successfully.", "success")
    except Exception:
        conn.rollback()
        flash("Username already exists.", "error")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("User deleted.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
