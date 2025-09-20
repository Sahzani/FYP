from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import timedelta
from werkzeug.utils import secure_filename
from firebase_admin import auth, exceptions

import os
import subprocess

# For webcam page
camera_process = None
WEBCAM_PATH = r"C:\Users\Acer\Desktop\FYP\flask\camera\webcam.py"

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
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if user_data.get("role_type") == 2:  # Ensure it's a teacher
                    return {
                        "profile": {
                            "name": user_data.get("name", "Teacher"),
                            "profile_pic": user_data.get(
                                "photo_name",
                                "https://placehold.co/140x140/E9E9E9/333333?text=T"
                            )
                        }
                    }
    return {}


# ------------------ Context Processor for Student Full Name ------------------
@app.context_processor
def inject_student_name():
    if session.get("role") == "student":
        user = session.get("user")
        if user:
            uid = user.get("uid")
            
            # Fetch user document
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                
                # Make sure the user is a student
                if user_data.get("role_type") == 1:
                    full_name = user_data.get("name", "").strip()
                    
                    # Fetch student-specific info from roles/student subcollection
                    student_doc_ref = db.collection("users").document(uid).collection("roles").document("student")
                    student_doc = student_doc_ref.get()
                    student_info = student_doc.to_dict() if student_doc.exists else {}
                    
                    student_class = student_info.get("studentClass", "")
                    group_code = student_info.get("fk_groupcode", "")
                    
                    return {
                        "full_name": full_name or "Student",
                        "student_class": student_class,
                        "group_code": group_code
                    }
    # Default fallback
    return {"full_name": "Student", "student_class": "", "group_code": ""}

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

       # ---------- Student / Teacher Login ----------
        user = auth.get_user_by_email(email)  # Firebase Auth lookup
        uid = user.uid

        # Fetch user document from users collection
        user_doc_ref = db.collection("users").document(uid)
        user_doc = user_doc_ref.get()

        if not user_doc.exists:
            flash("User not found in Firestore.")
            return redirect(url_for("home"))

        user_data = user_doc.to_dict()
        role_type = user_data.get("role_type")

        if role_type == 1:
            role = "student"
            redirect_url = "student_dashboard"
        elif role_type == 2:
            role = "teacher"
            redirect_url = "teacher_dashboard"
        else:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

        # Store session
        session["user"] = {"uid": uid, "email": email}
        session["role"] = role
        session.permanent = True if remember == "on" else False

        return redirect(url_for(redirect_url))

    except auth.UserNotFoundError:
        flash("Invalid email or password")
        return redirect(url_for("home"))

    except Exception as e:
        flash(f"Login error: {str(e)}")
        return redirect(url_for("home"))

# ------------------ Dashboards ------------------
from datetime import datetime
from flask import render_template, session, redirect, url_for

@app.route("/student_dashboard")
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user["uid"]

    # Get student data
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

    # Attendance stats
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

    # Notifications
    if late >= 3:
        notification = "You have been late more than 3 times!"
    elif unexcused_absences >= 3:
        notification = "Your attendance rate is dropped due to 3 unexcused absences this month."
    else:
        notification = "No new notifications."

    # Today's attendance
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_status = "Not Marked Yet"
    today_note = ""

    today_attendance_doc = db.collection("attendance") \
                             .where("student_id", "==", uid) \
                             .where("date", "==", today_str) \
                             .limit(1) \
                             .stream()

    for doc in today_attendance_doc:
        data = doc.to_dict()
        today_status = data.get("status", "Not Marked Yet")
        today_note = data.get("note", "")
        break

    # Determine color and icon for today's attendance
    if today_status == "Present":
        status_color = "#28a745"       # green
        status_icon = "fas fa-check-circle"
    elif today_status == "Late":
        status_color = "#ffc107"       # yellow
        status_icon = "fas fa-exclamation-triangle"
    elif today_status == "Absent":
        status_color = "#dc3545"       # red
        status_icon = "fas fa-times-circle"
    else:
        status_color = "#6c757d"       # grey
        status_icon = "fas fa-circle"

    return render_template(
        "student/S_Dashboard.html",
        full_name=full_name,
        stats_present=present,
        stats_absent=absent,
        stats_late=late,
        attendance_streak=streak,
        notification_message=notification,
        today_status=today_status,
        today_note=today_note,
        status_color=status_color,
        status_icon=status_icon
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

# ------------------ Camera Page ------------------
@app.route("/camera")
def camera_page():
    return render_template("camera.html")  # This will be a new template

@app.route("/start-camera")
def start_camera():
    global camera_process
    if camera_process is None:
        camera_process = subprocess.Popen(
            ["python", WEBCAM_PATH], shell=True
        )
    return redirect(url_for("camera_page"))

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

# ------------------ Student Schedule Page ------------------
@app.route("/student/schedule")
def student_schedule():
    # Get the logged-in user from session
    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    user_id = user.get("uid")

    # Fetch student document from Firestore
    student_ref = db.collection("roles").document(user_id).collection("student")
    student_docs = student_ref.stream()
    student_data = None
    for doc in student_docs:
        student_data = doc.to_dict()
        break

    if not student_data:
        flash("Student data not found.")
        return redirect(url_for("student_dashboard"))

    group_code = student_data.get("fk_groupcode")   

    # Query schedules filtered by group
    schedules_ref = db.collection("schedules").where("group", "==", group_code).stream()
    schedules = [doc.to_dict() for doc in schedules_ref]

    return render_template(
        "student/S_Schedule.html",  # updated template name
        schedules=schedules,
        full_name=student_data.get("fullName")
    )

# ------------------ Student Absent Pages ------------------
@app.route("/student/absentapp", methods=["GET", "POST"])
def student_absentapp():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        records = []
        return render_template(
            "student/S_AbsentApp.html",
            records=records,
            student=None,
            full_name=None,
            uid=None,
            student_ID=None
        )

    uid = user.get("uid")

    # Fetch full student data
    student_doc = db.collection("students").where("uid", "==", uid).limit(1).stream()
    student_data = None
    for doc in student_doc:
        student_data = doc.to_dict()
        break

    # Combine firstName + lastName
    first_name = student_data.get("firstName") if student_data else ""
    last_name = student_data.get("lastName") if student_data else ""
    full_name = f"{first_name} {last_name}".strip()
    student_ID = student_data.get("studentID") if student_data else ""

    if request.method == "POST":
        reason = request.form.get("reason")
        duration = request.form.get("duration")
        if not reason or not duration:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("student_absentapp"))

        db.collection("absenceRecords").add({
            "student_id": uid,
            "studentID": student_ID,
            "full_name": full_name,  # Send combined name
            "reason": reason,
            "duration": duration,
            "status": "In Progress",
            "submitted_at": firestore.SERVER_TIMESTAMP
        })
        flash("Absence application submitted successfully!", "success")
        return redirect(url_for("student_absentapp"))

    # GET: fetch absence records
    records = []
    try:
        records_ref = db.collection("absenceRecords").where("student_id", "==", uid)
        for doc in records_ref.stream():
            rec = doc.to_dict()
            rec["id"] = doc.id
            records.append(rec)
    except Exception as e:
        print("Error fetching records:", e)

    return render_template(
        "student/S_AbsentApp.html",
        records=records,
        student=student_data,
        full_name=full_name,
        uid=uid,
        student_ID=student_ID
    )



# ------------------ Student Profile ------------------
@app.route("/student/profile")
def student_profile():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")

    # Fetch student data from Firestore
    student_doc = db.collection("students").where("uid", "==", uid).limit(1).stream()
    student_data = None
    for doc in student_doc:
        student_data = doc.to_dict()
        break

    if not student_data:
        flash("Student data not found.")
        return redirect(url_for("student_dashboard"))

    # Handle profile picture path
    profile_pic_path = student_data.get("profilePic", None)
    if profile_pic_path and not profile_pic_path.startswith("http"):
        # Convert backslashes to forward slashes
        profile_pic_path = profile_pic_path.replace("\\", "/")
    else:
        profile_pic_path = "https://placehold.co/140x140/E9E9E9/333333?text=User"

    # Build profile dictionary
    profile = {
        "full_name": f"{student_data.get('firstName','')} {student_data.get('lastName','')}".strip() or "Student",
        "student_id": student_data.get("studentID", "-"),
        "nickname": student_data.get("nickname", "-"),
        "studentClass": student_data.get("studentClass", "-"),  
        "phone": student_data.get("phone", "-"),
        "email": user.get("email", "-"),
        "profile_pic": profile_pic_path,
        "course": student_data.get("course", "-"),
        "intake": student_data.get("intake", "-")
    }

    return render_template("student/S_Profile.html", profile=profile)



# ------------------ Student Edit Profile ------------------
@app.route("/student/editprofile", methods=["GET", "POST"])
def student_editprofile():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")
    student_doc = db.collection("students").where("uid", "==", uid).limit(1).stream()
    student_data = None
    student_ref = None
    for doc in student_doc:
        student_data = doc.to_dict()
        student_ref = doc.reference
        break

    if not student_data:
        flash("Student data not found.")
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        nickname = request.form.get("nickname")
        phone = request.form.get("phone")
        profile_pic_file = request.files.get("profilePic")

        update_data = {
            "nickname": nickname,
            "phone": phone
        }

        if profile_pic_file and profile_pic_file.filename != "":
            filename = secure_filename(profile_pic_file.filename)
            # Automatically create folder
            upload_dir = os.path.join(BASE_DIR, "static", "uploads", "student_profiles", uid)
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            profile_pic_file.save(file_path)
            update_data["profilePic"] = f"uploads/student_profiles/{uid}/{filename}"

        student_ref.update(update_data)
        flash("Profile updated successfully!")
        return redirect(url_for("student_editprofile"))

    profile = {
        "full_name": f"{student_data.get('firstName','')} {student_data.get('lastName','')}".strip() or "Student",
        "first_name": student_data.get("firstName", ""),
        "last_name": student_data.get("lastName", ""),
        "nickname": student_data.get("nickname", ""),
        "student_id": student_data.get("studentID", "-"),
        "studentClass": student_data.get("studentClass", "-"),
        "phone": student_data.get("phone", "-"),
        "email": user.get("email", "-"),
        "profile_pic": student_data.get("profilePic", "uploads/default/user.png"),
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
        return redirect(url_for("student_EditProfile"))

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

@app.route("/teacher_modules")
def teacher_modules():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    return render_template("teacher/T_modules.html")

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

# ------------------ Teacher Class Schedule ------------------
@app.route("/teacher/schedule")
def teacher_schedule():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    user = session.get("user")
    if not user:
        return redirect(url_for("home"))

    uid = user.get("uid")

    # Fetch teacher profile from Firestore
    profile_doc = db.collection("users").document(uid).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {}

    # Fetch teacher's schedule from Firestore
    schedule_docs = db.collection("schedules").where("teacher_id", "==", uid).stream()
    schedule = []
    for doc in schedule_docs:
        data = doc.to_dict()
        schedule.append({
            "group": data.get("group", ""),
            "module": data.get("module", ""),
            "day": data.get("day", ""),
            "start_time": data.get("start_time", ""),
            "end_time": data.get("end_time", ""),
            "room": data.get("room", "")
        })

    return render_template("teacher/T_schedule.html", schedule=schedule, profile=profile)

# ------------------ Teacher Manage Groups ------------------
@app.route("/teacher/manage_groups", methods=["GET", "POST"])
def teacher_manage_groups():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    # Fetch teacher profile
    profile = db.collection("users").document(session.get("uid")).get().to_dict()

    if request.method == "POST":
        # Create a new group
        group_name = request.form.get("group_name")
        student_ids = request.form.getlist("students")  # multiple select
        if group_name and student_ids:
            new_group_ref = db.collection("groups").document()  # auto ID
            new_group_ref.set({
                "name": group_name,
                "members": student_ids
            })
            return redirect(url_for("teacher_manage_groups"))

    # GET request
    # Fetch existing groups
    groups_docs = db.collection("groups").stream()
    groups = []
    for doc in groups_docs:
        data = doc.to_dict()
        members = []
        for sid in data.get("members", []):
            student_doc = db.collection("users").document(sid).get()
            if student_doc.exists:
                members.append({"id": sid, "name": student_doc.to_dict().get("name")})
        groups.append({"id": doc.id, "name": data.get("name"), "members": members})

    # Fetch unassigned students (students not in any group)
    all_students_docs = db.collection("users").where("role", "==", "student").stream()
    unassigned_students = []
    assigned_ids = [m["id"] for g in groups for m in g["members"]]
    for student_doc in all_students_docs:
        student_data = student_doc.to_dict()
        if student_doc.id not in assigned_ids:
            unassigned_students.append({"id": student_doc.id, "name": student_data.get("name")})

    return render_template(
        "teacher/T_GC_ManageGroup.html",
        profile=profile,
        groups=groups,
        unassigned_students=unassigned_students
    )


# ------------------ Delete a Group ------------------
@app.route("/teacher/delete_group/<group_id>", methods=["POST"])
def teacher_delete_group(group_id):
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    # Delete group document
    db.collection("groups").document(group_id).delete()
    return redirect(url_for("teacher_manage_groups"))


# ------------------ Teacher Group Reports ------------------
@app.route("/teacher/group_reports")
def teacher_group_reports():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    profile = db.collection("users").document(session.get("uid")).get().to_dict()
    
    # Fetch all groups with members
    groups_docs = db.collection("groups").stream()
    groups = []
    for doc in groups_docs:
        data = doc.to_dict()
        members = []
        for sid in data.get("members", []):
            student_doc = db.collection("users").document(sid).get()
            if student_doc.exists:
                members.append({"id": sid, "name": student_doc.to_dict().get("name")})
        groups.append({"id": doc.id, "name": data.get("name"), "members": members})

    return render_template(
        "teacher/T_GC_GroupReports.html",
        profile=profile,
        groups=groups
    )

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


# ------------------ Admin student Pages ------------------
@app.route("/admin/student_add")
def admin_student_add():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    # Fetch all groups
    groups_docs = db.collection("groups").stream()
    groups = []
    for doc in groups_docs:
        g = doc.to_dict()
        g["docId"] = doc.id
        groups.append(g)

    # Fetch all programs (optional, for a program dropdown if needed)
    programs_docs = db.collection("programs").stream()
    programs = []
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)

    # Pass to template
    return render_template("admin/A_Student-Add.html", groups=groups, programs=programs)


# ------------------ Save (Add/Edit) Student ------------------
@app.route('/admin/student/save', methods=['POST'])
def admin_student_save():
    student_id = request.form.get('userId')  # Firestore UID if editing
    name = request.form['name']
    email = request.form['email']
    password = request.form.get('password')
    studentID = request.form['studentID']
    studentClass = request.form['studentClass']
    groupCode = request.form.get('fk_groupcode', '')

    if student_id:
        # -------- Update existing user --------
        try:
            if password:
                auth.update_user(student_id, email=email, display_name=name, password=password)
            else:
                auth.update_user(student_id, email=email, display_name=name)
        except exceptions.FirebaseError as e:
            flash(f"Error updating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_student_add"))

        # Update main Firestore doc
        db.collection('users').document(student_id).update({
            'name': name,
            'email': email,
            'active': True,
            'role_type': 1,
            'photo_name': ''
        })

        # Update roles subcollection
        db.collection('users').document(student_id).collection('roles').document('student').set({
            'studentID': studentID,
            'studentClass': studentClass,
            'fk_groupcode': groupCode
        })

    else:
        # -------- Add new student --------
        try:
            user = auth.create_user(email=email, password=password or "password123", display_name=name)
            user_id = user.uid
        except exceptions.FirebaseError as e:
            flash(f"Error creating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_student_add"))

        # Create main Firestore doc
        db.collection('users').document(user_id).set({
            'user_id': user_id,
            'name': name,
            'email': email,
            'active': True,
            'role_type': 1,
            'photo_name': ''
        })

        # Create roles subcollection
        db.collection('users').document(user_id).collection('roles').document('student').set({
            'studentID': studentID,
            'studentClass': studentClass,
            'fk_groupcode': groupCode
        })

    return redirect(url_for('admin_student_add'))


# ------------------ Upload Students via CSV ------------------
@app.route("/admin/student_upload", methods=["POST"])
def admin_student_upload():
    if session.get("role") != "admin":
        return redirect(url_for("admin_dashboard"))

    if "csv_file" not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("admin_student_add"))

    file = request.files["csv_file"]
    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("admin_student_add"))

    import csv, io
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    for row in reader:
        name = row.get("name")
        email = row.get("email")
        password = row.get("password") or "password123"
        studentID = row.get("studentID")
        studentClass = row.get("studentClass")
        groupCode = row.get("groupCode", "")

        if not name or not email or not studentID:
            continue

        # Create Auth user
        try:
            user = auth.create_user(email=email, password=password, display_name=name)
            user_id = user.uid
        except exceptions.FirebaseError:
            continue  # skip duplicates

        # Create main Firestore doc
        db.collection('users').document(user_id).set({
            'user_id': user_id,
            'name': name,
            'email': email,
            'active': True,
            'role_type': 1,
            'photo_name': ''
        })

        # Create roles subcollection
        db.collection('users').document(user_id).collection('roles').document('student').set({
            'studentID': studentID,
            'studentClass': studentClass,
            'fk_groupcode': groupCode
        })

    flash("CSV uploaded successfully", "success")
    return redirect(url_for("admin_student_add"))


#--------------------student list -----------------------
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

# ------------------ Admin teacher add ------------------
@app.route("/admin/teacher_add")
def admin_teacher_add():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    # Fetch all programs
    programs_docs = db.collection("programs").stream()
    programs = []
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)

    # Fetch all modules
    modules_docs = db.collection("modules").stream()
    modules = []
    for doc in modules_docs:
        m = doc.to_dict()
        m["docId"] = doc.id
        modules.append(m)

    # Fetch all teachers (optional, for table)
    teachers_docs = db.collection("users").where("role_type", "==", 2).stream()
    teachers = []
    for doc in teachers_docs:
        t = doc.to_dict()
        t["uid"] = doc.id

        # Fetch module & program info from roles subcollection
        role_doc = db.collection("users").document(t["uid"]).collection("roles").document("teacher").get()
        if role_doc.exists:
            role = role_doc.to_dict()
            t["program"] = role.get("program", "")
            t["module"] = role.get("module", "")
            t["teacherID"] = role.get("teacherID", "")
        else:
            t["program"] = ""
            t["module"] = ""
            t["teacherID"] = ""

        # Optional: Fetch module info for display
        if t["module"]:
            mod_doc = db.collection("modules").document(t["module"]).get()
            t["modules"] = [mod_doc.to_dict()] if mod_doc.exists else []
        else:
            t["modules"] = []

        teachers.append(t)

    return render_template(
        "admin/A_Teacher-Add.html",
        programs=programs,
        modules=modules,
        teachers=teachers
    )


    return render_template("admin/A_Teacher-Add.html", modules=modules, programs=programs)  


# ------------------ Save (Add/Edit) Teacher ------------------
@app.route('/admin/teacher/save', methods=['POST'])
def admin_teacher_save():
    teacher_id = request.form.get('userId')  # Firestore UID if editing
    name = request.form['name']
    email = request.form['email']
    password = request.form.get('password')
    program = request.form['program']   # ✅ use program instead of course
    module = request.form['module']
    teacherID = request.form['teacherID']

    if teacher_id:
        # -------- Update existing user --------
        try:
            if password:
                auth.update_user(teacher_id, email=email, display_name=name, password=password)
            else:
                auth.update_user(teacher_id, email=email, display_name=name)
        except exceptions.FirebaseError as e:
            flash(f"Error updating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_teacher_add"))

        db.collection('users').document(teacher_id).update({
            'name': name,
            'email': email,
            'active': True,
            'role_type': 2,
            'photo_name': ''
        })

        db.collection('users').document(teacher_id).collection('roles').document('teacher').set({
            'program': program,   # ✅ changed key
            'module': module,
            'teacherID': teacherID
        })

    else:
        # -------- Add new teacher --------
        try:
            user = auth.create_user(email=email, password=password or "password123", display_name=name)
            teacher_id = user.uid
        except exceptions.FirebaseError as e:
            flash(f"Error creating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_teacher_add"))

        db.collection('users').document(teacher_id).set({
            'user_id': teacher_id,
            'name': name,
            'email': email,
            'active': True,
            'role_type': 2,
            'photo_name': ''
        })

        db.collection('users').document(teacher_id).collection('roles').document('teacher').set({
            'program': program,   # ✅ changed key
            'module': module,
            'teacherID': teacherID
        })

    return redirect(url_for('admin_teacher_add'))

# ------------------ Upload Teachers via CSV ------------------
@app.route("/admin/teacher_upload", methods=["POST"])
def admin_teacher_upload():
    if session.get("role") != "admin":
        return redirect(url_for("admin_dashboard"))

    if "csv_file" not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("admin_teacher_add"))

    file = request.files["csv_file"]
    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("admin_teacher_add"))

    import csv, io
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    for row in reader:
        name = row.get("name")
        email = row.get("email")
        password = row.get("password") or "password123"
        program = row.get("program")     # ✅ changed from course → program
        module = row.get("module")
        teacherID = row.get("teacherID")

        if not name or not email or not teacherID:
            continue

        # Create Auth user
        try:
            user = auth.create_user(email=email, password=password, display_name=name)
            teacher_id = user.uid
        except exceptions.FirebaseError:
            continue  # skip duplicates

        # Create main Firestore doc
        db.collection('users').document(teacher_id).set({
            'user_id': teacher_id,
            'name': name,
            'email': email,
            'active': True,
            'role_type': 2,  # teacher role
            'photo_name': ''
        })

        # Create roles subcollection
        db.collection('users').document(teacher_id).collection('roles').document('teacher').set({
            'program': program,   # ✅ store program, not course
            'module': module,
            'teacherID': teacherID
        })

    flash("CSV uploaded successfully", "success")
    return redirect(url_for("admin_teacher_add"))
#--------------------teacher list -----------------------

@app.route("/admin/teacher_list")
def admin_teacher_list():
    if session.get("role") == "admin":
        return render_template("admin/A_Teacher-List.html")
    return redirect(url_for("home"))

@app.route("/admin/module/assign", methods=["POST"])
def assign_module():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    teacher_id = request.form.get("teacher_id")
    module_id = request.form.get("module_id")

    # Store the assignment in `ml_module`
    db.collection("ml_module").add({
        "teacher": teacher_id,
        "module": module_id
    })

    return redirect(url_for("admin_modules"))
# ------------------ Admin page ------------------
@app.route("/admin/rooms")
def admin_rooms():
    if session.get("role") == "admin":
        return render_template("admin/A_Rooms.html")
    return redirect(url_for("home"))


@app.route("/admin/teacher_assign")
def admin_teacher_assign():
    if session.get("role") == "admin":
        return render_template("admin/A_TeacherAssign.html")
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

# ------------------ Admin Modules page ------------------

# Admin Modules Page
@app.route("/admin/modules")
def admin_modules():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    # Fetch modules
    modules_ref = db.collection("modules")
    modules_docs = modules_ref.stream()
    modules = []
    for doc in modules_docs:
        m = doc.to_dict()
        m["docId"] = doc.id
        modules.append(m)
    
    # Fetch programs
    programs_ref = db.collection("programs")  # adjust collection name if different
    programs_docs = programs_ref.stream()
    programs = []
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)
    
    return render_template("admin/modules.html", modules=modules, programs=programs)


# Add / Edit Module
@app.route("/admin/module/save", methods=["POST"])
def admin_module_save():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    module_id = request.form.get("moduleId")
    module_name = request.form.get("moduleName")
    module_code = request.form.get("moduleCode")
    fk_program = request.form.get("fk_program")   # <-- ADD THIS
    status = int(request.form.get("status"))

    module_data = {
        "moduleName": module_name,
        "moduleCode": module_code,
        "fk_program": fk_program,   # <-- SAVE PROGRAM REFERENCE
        "status": status
    }

    if module_id:  # Edit existing module
        db.collection("modules").document(module_id).set(module_data, merge=True)
    else:  # Add new module
        db.collection("modules").add(module_data)

    return redirect(url_for("admin_modules"))


# Delete Module
@app.route("/delete_module/<module_id>", methods=["POST"])
def delete_module(module_id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    db.collection("modules").document(module_id).delete()
    return redirect(url_for("admin_modules"))


# ------------------ Admin Groups Page ------------------
@app.route("/admin/groups")
def admin_groups():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    # Fetch all groups
    groups_docs = db.collection("groups").stream()
    groups = []
    for doc in groups_docs:
        g = doc.to_dict()
        g["docId"] = doc.id
        groups.append(g)

    # Fetch all programs
    programs_docs = db.collection("programs").stream()
    programs = []
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)

    return render_template("admin/A_Group.html", groups=groups, programs=programs)


# ------------------ Save (Add/Edit) Group ------------------
@app.route("/admin/group/save", methods=["POST"])
def admin_group_save():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    group_id = request.form.get("groupId")
    group_code = request.form.get("groupCode")
    program_id = request.form.get("fk_program")
    intake = request.form.get("intake")

    # Validate program exists
    program_doc = db.collection("programs").document(program_id).get()
    if not program_doc.exists:
        flash("Selected program does not exist!", "danger")
        return redirect(url_for("admin_groups"))

    # Data to save
    group_data = {
        "groupCode": group_code,
        "fk_program": program_id,  # store the program's Firestore ID
        "intake": intake
    }

    if group_id:  # Edit existing group
        db.collection("groups").document(group_id).set(group_data, merge=True)
    else:  # Add new group
        write_time, group_ref = db.collection("groups").add(group_data)  # correct unpacking
        group_id = group_ref.id  # now safe to access

    flash("Group saved successfully!", "success")
    return redirect(url_for("admin_groups"))


# ------------------ Delete Group ------------------
@app.route("/admin/group/delete/<group_id>", methods=["POST"])
def admin_group_delete(group_id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    db.collection("groups").document(group_id).delete()
    flash("Group deleted successfully!", "success")
    return redirect(url_for("admin_groups"))


# ------------------ Upload Groups via CSV ------------------
@app.route("/admin/group/upload", methods=["POST"])
def admin_group_upload_route():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    csv_file = request.files.get("csv_file")
    if not csv_file:
        flash("No CSV file selected!", "danger")
        return redirect(url_for("admin_groups"))

    import csv, io
    stream = io.StringIO(csv_file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    for row in reader:
        # Lookup program by name
        program_name = row.get("program_name")
        program_query = db.collection("programs").where("programName", "==", program_name).limit(1).get()
        if not program_query:
            flash(f"Program '{program_name}' not found. Skipping row.", "warning")
            continue

        program_id = program_query[0].id

        group_data = {
            "groupName": row.get("groupName"),
            "groupCode": row.get("groupCode"),
            "fk_program": program_id,
            "intake": row.get("intake")
        }
        db.collection("groups").add(group_data)

    flash("CSV uploaded successfully!", "success")
    return redirect(url_for("admin_groups"))

# ------------------ Admin Programs Page ------------------
@app.route("/admin/programs")
def admin_programs():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    programs_docs = db.collection("programs").stream()
    programs = []
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)

    return render_template("admin/A_Program.html", programs=programs)


# ------------------ Save (Add/Edit) Program ------------------
@app.route("/admin/program/save", methods=["POST"])
def admin_program_save():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    program_id = request.form.get("programId")
    program_name = request.form.get("programName")

    if not program_name:
        flash("Program name cannot be empty!", "danger")
        return redirect(url_for("admin_programs"))

    program_data = {
        "programName": program_name
    }

    if program_id:  # Edit
        db.collection("programs").document(program_id).set(program_data, merge=True)
    else:  # Add new
        db.collection("programs").add(program_data)

    flash("Program saved successfully!", "success")
    return redirect(url_for("admin_programs"))


# ------------------ Delete Program ------------------
@app.route("/admin/program/delete/<program_id>", methods=["POST"])
def admin_program_delete(program_id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    db.collection("programs").document(program_id).delete()
    flash("Program deleted successfully!", "success")
    return redirect(url_for("admin_programs"))


# ------------------ Upload Programs via CSV ------------------
@app.route("/admin/program/upload", methods=["POST"])
def admin_program_upload():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    csv_file = request.files.get("csv_file")
    if not csv_file:
        flash("No CSV file selected!", "danger")
        return redirect(url_for("admin_programs"))

    import csv, io
    stream = io.StringIO(csv_file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    for row in reader:
        program_name = row.get("program_name")
        if not program_name:
            continue
        db.collection("programs").add({"programName": program_name})

    flash("CSV uploaded successfully!", "success")
    return redirect(url_for("admin_programs"))

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