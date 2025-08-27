from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import timedelta
import os

# ------------------ Flask Setup ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = "supersecretkey"
app.permanent_session_lifetime = timedelta(days=30)

# ------------------ Firebase Setup ------------------
cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

db = firestore.client()

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("combinePage/Login.html")  # login page

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    remember = request.form.get("remember")

    if not email or not password:
        flash("Please enter both email and password.")
        return redirect(url_for("home"))

    try:
        # ---------- Admin Login ----------
        if email == "admin@admin.edu":
            doc = db.collection("admin").document("admin").get()
            if doc.exists and doc.to_dict().get("password") == password:
                session["user"] = {"uid": "admin", "email": email}  # ✅ store as dict
                session["role"] = "admin"
                session.permanent = True if remember == "on" else False
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Invalid admin credentials.")
                return redirect(url_for("home"))

        # ---------- Student / Teacher ----------
        user = auth.get_user_by_email(email)   # Firebase lookup
        uid = user.uid

        collections = {"student": "students", "teacher": "teachers"}
        role = None
        user_doc = None

        for role_name, collection_name in collections.items():
            docs = db.collection(collection_name).where("uid", "==", uid).stream()
            for doc in docs:
                user_doc = doc.to_dict()
                role = role_name
                break
            if role:
                break

        if not user_doc:
            flash("User not found in Firestore.")
            return redirect(url_for("home"))

        # ✅ FIX: Store both uid + email in session
        session["user"] = {"uid": uid, "email": email}
        session["role"] = role
        session.permanent = True if remember == "on" else False

        if role == "student":
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher_dashboard"))
        else:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

    except auth.UserNotFoundError:
        flash("Invalid email or password")
        return redirect(url_for("home"))

# ------------------ Dashboards ------------------
@app.route("/student_dashboard")
def student_dashboard():
    if session.get("role") == "student":
        return render_template("student/S_Dashboard.html")
    return redirect(url_for("home"))

@app.route("/teacher_dashboard")
def teacher_dashboard():
    if session.get("role") == "teacher":
        return render_template("teacher/T_dashboard.html")
    return redirect(url_for("home"))

@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("role") == "admin":
        return render_template("admin/A_Homepage.html")
    return redirect(url_for("home"))

# ------------------ Student Pages ------------------
@app.route("/student_attendance")
def student_attendance():
    if 'user' not in session:  # check if logged in
        return redirect(url_for('login'))

    user_id = session['user']['uid']  # get student ID from session

    # 🔹 Fetch attendance records from Firestore
    attendance_ref = firestore.client().collection('attendance').where('student_id', '==', user_id)
    docs = attendance_ref.stream()

    records = []
    total = 0
    present = 0
    absent = 0

    for doc in docs:
        data = doc.to_dict()
        records.append(data)

        total += 1
        if data.get('status') == 'Present':
            present += 1
        elif data.get('status') == 'Absent':
            absent += 1

    # 🔹 Calculate percentage
    percentage = (present / total * 100) if total > 0 else 0

    return render_template(
        "student/S_History.html",
        records=records,
        present=present,
        absent=absent,
        total=total,
        percentage=round(percentage, 2)
    )

@app.route('/student/absentapp')
def student_absentapp():
    if session.get("role") == "student":
        return render_template('student/S_AbsentApp.html')
    return redirect(url_for("home"))

@app.route("/student/profile")
def student_profile():
    if session.get("role") == "student":
        return render_template("student/S_Profile.html")
    return redirect(url_for("home"))

@app.route("/student/contact")
def student_contact():
    if session.get("role") == "student":
        return render_template("student/S_ContactUs.html")
    return redirect(url_for("home"))

# ------------------ Teacher Pages ------------------
@app.route("/teacher/profile")
def teacher_profile():
    if session.get("role") == "teacher":
        return render_template("teacher/T_profile.html")
    return redirect(url_for("home"))

@app.route("/teacher/class_list")
def teacher_class_list():
    if session.get("role") == "teacher":
        return render_template("teacher/T_class_list.html")
    return redirect(url_for("home"))

@app.route("/teacher/attendance")
def teacher_attendance():
    if session.get("role") == "teacher":
        return render_template("teacher/T_attendance_report.html")
    return redirect(url_for("home"))

@app.route("/teacher/daily_attend")
def teacher_daily_attend():
    if session.get("role") == "teacher":
        return render_template("teacher/T_DailyAttend.html")
    return redirect(url_for("home"))

@app.route("/teacher/login")
def teacher_login():
    return render_template("teacher/T_login.html")

@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("home"))

# ------------------ Admin Pages ------------------
@app.route("/admin/student_add")
def admin_student_add():
    if session.get("role") == "admin":
        return render_template("admin/A_Student-Add.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_add")
def admin_teacher_add():
    if session.get("role") == "admin":
        return render_template("admin/A_Teacher-Add.html")
    return redirect(url_for("home"))

@app.route("/admin/student_list")
def admin_student_list():
    if session.get("role") == "admin":
        return render_template("admin/A_Student-List.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_list")
def admin_teacher_list():
    if session.get("role") == "admin":
        return render_template("admin/A_Teacher-List.html")
    return redirect(url_for("home"))

# ------------------ Logout / Signup ------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/signup")
def signup():
    return "Signup page coming soon!"

# ------------------ Run Flask ------------------
if __name__ == "__main__":
    app.run(debug=True, port=8000)
