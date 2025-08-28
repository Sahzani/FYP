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

# ------------------ Context Processor for Teacher Profile ------------------
@app.context_processor
def inject_teacher_profile():
    if session.get("role") == "teacher":
        user = session.get("user")
        if user:
            uid = user.get("uid")
            teacher_doc = db.collection("teachers").where("uid", "==", uid).limit(1).stream()
            teacher_data = None
            for doc in teacher_doc:
                teacher_data = doc.to_dict()
                break
            if teacher_data:
                return {
                    "profile": {
                        "name": teacher_data.get("name", "Teacher"),
                        "profile_pic": teacher_data.get("profilePic", "https://placehold.co/140x140/E9E9E9/333333?text=T")
                    }
                }
    return {}

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
                session["user"] = {"uid": "admin", "email": email}
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
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user["uid"]

    student_doc = db.collection("students").where("uid", "==", uid).limit(1).stream()
    student_data = None
    for doc in student_doc:
        student_data = doc.to_dict()
        break

    full_name = "Student"
    if student_data:
        first = student_data.get("firstName", "")
        last = student_data.get("lastName", "")
        full_name = f"{first} {last}".strip() or "Student"

    attendance_docs = db.collection("attendance").where("student_id", "==", uid).stream()
    present = absent = late = streak = 0
    unexcused_absences = 0
    temp_streak = 0

    for doc in attendance_docs:
        data = doc.to_dict()
        status = data.get("status")
        if status == "Present":
            present += 1
            temp_streak += 1
        elif status == "Late":
            late += 1
            temp_streak = 0
        elif status == "Absent":
            absent += 1
            if not data.get("letter"):
                unexcused_absences += 1
            temp_streak = 0
        streak = max(streak, temp_streak)

    if late >= 3:
        notification = "You have been late more than 3 times!"
    elif unexcused_absences >= 3:
        notification = "Your attendance rate is dropped due to 3 unexcused absences this month."
    else:
        notification = "No new notifications."

    return render_template(
        "student/S_Dashboard.html",
        full_name=full_name,
        stats_present=present,
        stats_absent=absent,
        stats_late=late,
        attendance_streak=streak,
        notification_message=notification
    )

@app.route("/teacher_dashboard")
def teacher_dashboard():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    return render_template("teacher/T_dashboard.html")

@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("role") == "admin":
        return render_template("admin/A_Homepage.html")
    return redirect(url_for("home"))

# ------------------ Student Pages ------------------
@app.route("/student_attendance")
def student_attendance():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['uid']

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

# ------------------ Student Profile ------------------
@app.route("/student/profile")
def student_profile():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")

    student_doc = db.collection("students").where("uid", "==", uid).limit(1).stream()
    student_data = None
    for doc in student_doc:
        student_data = doc.to_dict()
        break

    if not student_data:
        flash("Student data not found.")
        return redirect(url_for("student_dashboard"))

    profile = {
        "full_name": f"{student_data.get('firstName','')} {student_data.get('lastName','')}".strip() or "Student",
        "student_id": student_data.get("studentID", "-"),
        "nickname": student_data.get("nickname", "-"),
        "studentClass": student_data.get("studentClass", "-"),  
        "phone": student_data.get("phone", "-"),
        "email": user.get("email", "-"),
        "profile_pic": student_data.get("profilePic", "https://placehold.co/140x140/E9E9E9/333333?text=User"),
        "course": student_data.get("course", "-"),
        "intake": student_data.get("intake", "-")
    }

    return render_template("student/S_Profile.html", profile=profile)

# ------------------ Student Edit Profile ------------------
@app.route("/student/editprofile", methods=["GET", "POST"])
def student_editprofile():
    # Check user role
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")

    # Fetch student info from Firestore
    student_doc = db.collection("students").where("uid", "==", uid).limit(1).stream()
    student_data = None
    for doc in student_doc:
        student_data = doc.to_dict()
        break

    if not student_data:
        flash("Student data not found.")
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        # Handle profile update
        nickname = request.form.get("nickname")
        phone = request.form.get("phone")
        profile_pic = request.form.get("profile_pic")  # Optional: base64 or URL from front-end

        # Update Firestore
        student_ref = db.collection("students").document(student_data["uid"])
        student_ref.update({
            "nickname": nickname,
            "phone": phone,
            "profilePic": profile_pic
        })

        flash("Profile updated successfully!")
        return redirect(url_for("student_EditProfile"))

    # Prepare profile fields for GET
    profile = {
        "full_name": f"{student_data.get('firstName','')} {student_data.get('lastName','')}".strip() or "Student",
        "first_name": student_data.get("firstName", ""),
        "last_name": student_data.get("lastName", ""),
        "nickname": student_data.get("nickname", ""),
        "student_id": student_data.get("studentID", "-"),
        "studentClass": student_data.get("studentClass", "-"),
        "phone": student_data.get("phone", "-"),
        "email": user.get("email", "-"),
        "profile_pic": student_data.get("profilePic", "https://placehold.co/140x140/E9E9E9/333333?text=User"),
        "course": student_data.get("course", "-"),
        "intake": student_data.get("intake", "-")
    }

    return render_template("student/S_EditProfile.html", profile=profile)


# ------------------ Change Password for student ------------------
@app.route("/student/change_password", methods=["POST"])
def student_change_password():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")
    current_password = request.form.get("currentPassword")
    new_password = request.form.get("newPassword")
    confirm_password = request.form.get("confirmPassword")

    if not current_password or not new_password or not confirm_password:
        flash("Please fill all password fields.", "error")
        return redirect(url_for("student_editprofile"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "error")
        return redirect(url_for("student_editprofile"))

    # TODO: Implement password verification and update using Firebase Auth
    # For example:
    # auth.update_user(uid, password=new_password)

    flash("Password changed successfully!", "success")
    return redirect(url_for("student_editprofile"))

@app.route("/student/contact")
def student_contact():
    if session.get("role") == "student":
        return render_template("student/S_ContactUs.html")
    return redirect(url_for("home"))

# ------------------ Teacher Pages ------------------
@app.route("/teacher/class_list")
def teacher_class_list():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    return render_template("teacher/T_class_list.html")

@app.route("/teacher/attendance")
def teacher_attendance():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    return render_template("teacher/T_attendance_report.html")

@app.route("/teacher/daily_attend")
def teacher_daily_attend():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    return render_template("teacher/T_DailyAttend.html")

@app.route("/teacher/login")
def teacher_login():
    return render_template("teacher/T_login.html")

@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("home"))

# ------------------ Teacher Profile ------------------
@app.route("/teacher/profile")
def teacher_profile():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")

    teacher_doc = db.collection("teachers").where("uid", "==", uid).limit(1).stream()
    teacher_data = None
    for doc in teacher_doc:
        teacher_data = doc.to_dict()
        break

    if not teacher_data:
        flash("Teacher data not found.")
        return redirect(url_for("teacher_dashboard"))

    profile = {
        "name": teacher_data.get("name", "Teacher"),
        "teacher_id": teacher_data.get("teacherID", "-"),
        "department": teacher_data.get("department", "-"),
        "email": user.get("email", "-"),
        "profile_pic": teacher_data.get("profilePic", "https://placehold.co/140x140/E9E9E9/333333?text=T")
    }

    return render_template("teacher/T_Profile.html", profile=profile)

# ------------------ Admin Pages ------------------
@app.route("/admin/student_add")
def admin_student_add():
    if session.get("role") == "admin":
        return render_template("admin/A_Student-Add.html")
    return redirect(url_for("home"))

@app.route("/admin/student_list")
def admin_student_list():
    if session.get("role") == "admin":
        return render_template("admin/A_Student-List.html")
    return redirect(url_for("home"))

@app.route("/admin/student_assign")
def admin_student_assign():
    if session.get("role") == "admin":
        return render_template("admin/A_Student-Assign.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_add")
def admin_teacher_add():
    if session.get("role") == "admin":
        return render_template("admin/A_Teacher-Add.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_list")
def admin_teacher_list():
    if session.get("role") == "admin":
        return render_template("admin/A_Teacher-List.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_assign")
def admin_teacher_assign():
    if session.get("role") == "admin":
        return render_template("admin/A_Teacher-Assign.html")
    return redirect(url_for("home"))

@app.route("/admin/rooms")
def admin_rooms():
    if session.get("role") == "admin":
        return render_template("admin/A_Rooms.html")
    return redirect(url_for("home"))

@app.route("/admin/schedule_upload")
def admin_schedule_upload():
    if session.get("role") == "admin":
        return render_template("admin/A_Schedule-Upload.html")
    return redirect(url_for("home"))

@app.route("/admin/attendance_logs")
def admin_attendance_logs():
    if session.get("role") == "admin":
        return render_template("admin/A_Attendance-Logs.html")
    return redirect(url_for("home"))

@app.route("/admin/change_logs")
def admin_change_logs():
    if session.get("role") == "admin":
        return render_template("admin/A_Change-Logs.html")
    return redirect(url_for("home"))

@app.route("/admin/roles")
def admin_roles():
    if session.get("role") == "admin":
        return render_template("admin/A_Roles.html")
    return redirect(url_for("home"))

@app.route("/admin/email_setup")
def admin_email_setup():
    if session.get("role") == "admin":
        return render_template("admin/A_Email-Setup.html")
    return redirect(url_for("home"))

@app.route("/admin/summary")
def admin_summary():
    if session.get("role") == "admin":
        return render_template("admin/A_Summary.html")
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
