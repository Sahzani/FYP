from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import timedelta
from werkzeug.utils import secure_filename
from firebase_admin import auth, exceptions
import firebase_admin, random
from flask import send_from_directory
import os


# For webcam page
camera_process = None
WEBCAM_PATH = r"C:\Users\Acer\Desktop\FYP\flask\camera\webcam.py"
app = Flask(__name__, static_folder="student_pics")


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
    profile_data = {}
    schedules_list = []

    if session.get("role") == "teacher":
        user = session.get("user")
        if user:
            uid = user.get("uid")
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if user_data.get("role_type") == 2:  # Ensure it's a teacher
                    profile_data = {
                        "name": user_data.get("name", "Teacher"),
                        "profile_pic": user_data.get(
                            "photo_name",
                            "https://placehold.co/140x140/E9E9E9/333333?text=T"
                        ),
                        "is_gc": user_data.get("is_gc", False)
                    }

                    # Fetch schedules assigned to this teacher
                    schedules_docs = db.collection("schedules").where("fk_teacher", "==", uid).stream()
                    for doc in schedules_docs:
                        s = doc.to_dict()
                        s["docId"] = doc.id

                        # Fetch group/module names for display
                        group_doc = db.collection("groups").document(s.get("fk_group")).get()
                        module_doc = db.collection("modules").document(s.get("fk_module")).get()

                        s["group_name"] = group_doc.to_dict().get("groupName") if group_doc.exists else ""
                        s["module_name"] = module_doc.to_dict().get("moduleName") if module_doc.exists else ""

                        schedules_list.append(s)

    return {"profile": profile_data, "schedules": schedules_list}

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
@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    remember = request.form.get("remember")

    if not email or not password:
        flash("Please enter both email and password.")
        return redirect(url_for("home"))  # "/" route

    try:
        # ---------- Admin Login ----------
        if email == "admin@admin.edu":
            doc = db.collection("admin").document("admin").get()
            if doc.exists and doc.to_dict().get("password") == password:
                session["user"] = {"uid": "admin", "email": email}
                session["user_id"] = "admin"
                session["user_email"] = email
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

            # ---------- Check if GC (only for teacher) ----------
            roles_subcol = db.collection("users").document(uid).collection("roles").stream()
            is_gc = False
            for r in roles_subcol:
                r_data = r.to_dict()
                if r_data.get("isCoordinator") == True:
                    is_gc = True
                    break
            # You can store this info in session if needed
            session["is_gc"] = is_gc

        else:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

        # ✅ Unified session
        session["user"] = {"uid": uid, "email": email}
        session["user_id"] = uid
        session["user_email"] = email
        session["role"] = role
        session.permanent = True if remember == "on" else False

        return redirect(url_for(redirect_url))

    except auth.UserNotFoundError:
        flash("Invalid email or password")
        return redirect(url_for("home"))

    except Exception as e:
        flash(f"Login error: {str(e)}")
        return redirect(url_for("home"))


@app.route("/")
def home():
    return render_template("combinePage/Login.html")  # login page



# ------------------student Dashboards ------------------
from datetime import datetime
from flask import render_template, session, redirect, url_for

@app.route("/student_dashboard")
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("home"))

    uid = session.get("user_id")  # 🔹 now uses user_id instead of user
    if not uid:
        return redirect(url_for("home"))

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
    
# ------------------ Teacher Dashboard ------------------
@app.route("/teacher_dashboard")
def teacher_dashboard():
    # Ensure teacher is logged in
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("home"))
    teacher_uid = user.get("uid")

    # ------------------ Fetch teacher profile ------------------
    profile_doc = db.collection("users").document(teacher_uid).get()
    profile = {}
    if profile_doc.exists:
        user_data = profile_doc.to_dict()
        full_name = user_data.get("name", "Teacher")
        parts = full_name.split(" ", 1)

        # ------------------ Check if GC ------------------
        role_doc = db.collection("users").document(teacher_uid).collection("roles").document("teacher").get()
        is_gc = False
        if role_doc.exists:
            is_gc = role_doc.to_dict().get("isCoordinator", False)

        profile = {
            "role": user_data.get("role", "Teacher"),
            "firstName": parts[0],
            "lastName": parts[1] if len(parts) > 1 else "",
            "profile_pic": user_data.get(
                "photo_name", "https://placehold.co/140x140/E9E9E9/333333?text=T"
            ),
            "is_gc": is_gc
        }
    else:
        profile = {
            "role": "Teacher",
            "firstName": "Teacher",
            "lastName": "",
            "profile_pic": "",
            "is_gc": False
        }

    # ------------------ Fetch schedules ------------------
    schedules = []
    schedules_docs = db.collection("schedules").where("fk_teacher", "==", teacher_uid).stream()
    for doc in schedules_docs:
        s = doc.to_dict()
        s["docId"] = doc.id

        group_code = s.get("fk_groupcode")
        module_code = s.get("fk_module")

        # Skip schedules with missing fields
        if not group_code or not module_code:
            continue

        # Fetch group and module names safely
        group_doc = db.collection("groups").document(group_code).get()
        module_doc = db.collection("modules").document(module_code).get()
        s["group_name"] = group_doc.to_dict().get("groupName") if group_doc.exists else ""
        s["module_name"] = module_doc.to_dict().get("moduleName") if module_doc.exists else ""

        schedules.append(s)

    # ------------------ Stats calculation ------------------
    today_str = datetime.now().strftime("%Y-%m-%d")
    total_present, total_absent = 0, 0

    for schedule in schedules:
        group_code = schedule.get("fk_groupcode")
        module_code = schedule.get("fk_module")

        if not group_code or not module_code:
            continue

        attendance_docs = db.collection("attendance").document(today_str)\
            .collection(group_code).document(module_code)\
            .collection("students").stream()

        for att in attendance_docs:
            att_data = att.to_dict()
            if att_data.get("status") == "Present":
                total_present += 1
            else:
                total_absent += 1

    stats = {
        "classes": len(schedules),
        "present": total_present,
        "absent": total_absent
    }

    # ------------------ Render template ------------------
    return render_template(
        "teacher/T_dashboard.html",
        stats=stats,
        schedules=schedules,
        profile=profile,
        current_schedule=None
    )


#------------------ Admin Pages ------------------
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

# ------------------ Student Schedule Page ------------------
@app.route("/student/schedule")
def student_schedule():
    # Check if user is logged in
    user = session.get("user")
    role = session.get("role")
    if not user or role != "student":
        return redirect(url_for("home"))

    uid = user.get("uid")

    # Fetch student info from users/{uid}/roles/student
    student_doc_ref = db.collection("users").document(uid).collection("roles").document("student")
    student_doc = student_doc_ref.get()
    if not student_doc.exists:
        flash("Student data not found.")
        return redirect(url_for("student_dashboard"))

    student_info = student_doc.to_dict()
    group_code = student_info.get("fk_groupcode", "")
    student_class = student_info.get("studentClass", "")

    # Fetch schedules for this group
    schedules_ref = db.collection("schedules").where("group", "==", group_code).stream()
    schedules = [doc.to_dict() for doc in schedules_ref]

    # Fetch full name from users/{uid} document
    user_doc = db.collection("users").document(uid).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        full_name = user_data.get("name", "Student").strip()
    else:
        full_name = "Student"

    return render_template(
        "student/S_Schedule.html",
        schedules=schedules,
        full_name=full_name,
        student_class=student_class,
        group_code=group_code
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

# ------------------ Teacher modules, groups, and attendance ------------------
@app.route("/teacher_modules")
def teacher_modules():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    teacher_id = user.get("uid")
    if not teacher_id:
        return redirect(url_for("login"))

    # ------------------ Profile for header ------------------
    # Fetch the teacher's full profile from Firestore
    teacher_doc = db.collection("users").document(teacher_id).get()
    if teacher_doc.exists:
        teacher_data = teacher_doc.to_dict()
        profile = {
            "firstName": teacher_data.get("firstName", ""),
            "lastName": teacher_data.get("lastName", "")
        }
    else:
        profile = {"firstName": "", "lastName": ""}

    # ------------------ 1. Fetch schedules for this teacher ------------------
    schedules_ref = db.collection("schedules").where("fk_teacher", "==", teacher_id).stream()
    schedules = [s.to_dict() | {"id": s.id} for s in schedules_ref]

    if not schedules:
        return render_template("teacher/T_modules.html", modules_data=[], groups_data={}, profile=profile)

    # ------------------ 2. Collect module IDs and group IDs ------------------
    module_ids = list({s["fk_module"] for s in schedules})
    group_ids = list({s["fk_group"] for s in schedules})

    # ------------------ 3. Fetch module names ------------------
    modules_ref = db.collection("modules").where("__name__", "in", module_ids).stream()
    modules = {m.id: m.to_dict() for m in modules_ref}

    # ------------------ 4. Fetch groups ------------------
    groups_ref = db.collection("groups").where("__name__", "in", group_ids).stream()
    groups = {g.id: g.to_dict() for g in groups_ref}

    # ------------------ 5. Fetch students ------------------
    students_ref = db.collection("users").where("role_type", "==", 1).stream()
    students_by_group = {}
    for stu_doc in students_ref:
        stu = stu_doc.to_dict()
        g_id = stu.get("group_code")
        if g_id not in students_by_group:
            students_by_group[g_id] = []

        full_name = f"{stu.get('firstName', '')} {stu.get('lastName', '')}".strip()
        students_by_group[g_id].append({
            "id": stu_doc.id,
            "name": full_name if full_name else "Student",
            "status": "Not Marked",
            "date": ""
        })

    # ------------------ 6. Fetch attendance ------------------
    attendance_ref = db.collection("attendance").stream()
    attendance_map = {}
    for att_doc in attendance_ref:
        att = att_doc.to_dict()
        key = (att.get("schedule_id"), att.get("student_id"))
        attendance_map[key] = {"status": att.get("status", "Not Marked"), "date": att.get("date", "")}

    # ------------------ 7. Assemble modules & groups ------------------
    modules_data = []
    groups_data = {}

    for sched in schedules:
        mod_id = sched["fk_module"]
        g_id = sched["fk_group"]

        # Module name from 'modules' collection
        module_name = modules.get(mod_id, {}).get("moduleName", "Unknown Module")

        # Add module entry if not exists
        module_obj = next((m for m in modules_data if m["moduleName"] == module_name), None)
        if not module_obj:
            module_obj = {"moduleName": module_name, "groups": []}
            modules_data.append(module_obj)

        # Add group under module
        if g_id not in module_obj["groups"]:
            module_obj["groups"].append(g_id)

        # Add group details with student attendance
        students_list = []
        for stu in students_by_group.get(g_id, []):
            key = (sched["id"], stu["id"])
            att_info = attendance_map.get(key, {"status": "Not Marked", "date": ""})
            students_list.append({
                "id": stu["id"],
                "name": stu["name"],
                "status": att_info["status"],
                "date": att_info["date"]
            })

        groups_data[g_id] = {
            "groupName": groups.get(g_id, {}).get("groupCode", g_id),
            "students": students_list,
            "day": sched.get("day", ""),
            "time": f"{sched.get('start_time', '')} - {sched.get('end_time', '')}",
            "room": sched.get("room", "")
        }

    # ------------------ 8. Render template ------------------
    return render_template(
        "teacher/T_modules.html",
        modules_data=modules_data,
        groups_data=groups_data,
        profile=profile
    )
# ------------------ Teacher marks attendance ------------------
@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    teacher_id = user.get("uid")
    if not teacher_id:
        return redirect(url_for("login"))

    # Expect data from form / AJAX
    schedule_id = request.form.get("schedule_id")
    student_id = request.form.get("student_id")
    status = request.form.get("status")  # e.g., "Present", "Absent", etc.

    if not (schedule_id and student_id and status):
        flash("Missing attendance information.", "error")
        return redirect(url_for("teacher_modules"))

    # Save or update attendance
    attendance_ref = db.collection("attendance")
    query = attendance_ref.where("schedule_id", "==", schedule_id)\
                          .where("student_id", "==", student_id).stream()

    existing_att = list(query)
    att_data = {
        "schedule_id": schedule_id,
        "student_id": student_id,
        "status": status,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if existing_att:
        # Update existing document
        doc_id = existing_att[0].id
        attendance_ref.document(doc_id).set(att_data)
    else:
        # Add new attendance record
        attendance_ref.add(att_data)

    flash("Attendance updated successfully!", "success")
    return redirect(url_for("teacher_modules"))


@app.route("/teacher/attendance")
def teacher_attendance():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    user_id = session.get("user_id")  # this exists in your session
    if not user_id:
        return redirect(url_for("home"))

    # Fetch teacher profile from Firestore
    user_doc_ref = db.collection("users").document(user_id)
    user_doc = user_doc_ref.get()
    if not user_doc.exists:
        flash("User profile not found.")
        return redirect(url_for("home"))

    profile = user_doc.to_dict()  # profile now has all fields (e.g., name, email)

    return render_template("teacher/T_attendance_report.html", profile=profile)


@app.route("/teacher/manage_absent")
def teacher_manage_absent():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("home"))

    # Fetch teacher profile from Firestore
    user_doc_ref = db.collection("users").document(user_id)
    user_doc = user_doc_ref.get()
    if not user_doc.exists:
        flash("User profile not found.")
        return redirect(url_for("home"))

    profile = user_doc.to_dict()  # contains name, email, etc.

    return render_template("teacher/T_manageAbsent.html", profile=profile)


@app.route("/teacher/login")
def teacher_login():
    return render_template("teacher/T_login.html")

@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("home"))

events = [
    {
        "id": 1,
        "title": "Workshop A",
        "datetime": datetime(2025, 10, 2, 14, 0),
        "group": {"name": "Group Alpha"},
        "attendees": [{"name": "Student 1"}, {"name": "Student 2"}]
    }
]

# ------------------ Teacher Schedule page ------------------
@app.route("/teacher/schedules")
def teacher_schedules():
    if session.get("role") != "teacher":
        return redirect(url_for("home"))

    teacher_id = str(session.get("user_id")).strip()

    # Fetch all schedules
    schedules_docs = db.collection("schedules").stream()

    # Fetch supporting info
    programs = {p.id: p.to_dict() for p in db.collection("programs").stream()}
    modules  = {m.id: m.to_dict() for m in db.collection("modules").stream()}

    # Fetch groups collection once
    groups_collection = {g.id: g.to_dict() for g in db.collection("groups").stream()}

    schedules = []
    for doc in schedules_docs:
        s = doc.to_dict()
        s['docId'] = doc.id

        # Match teacher ID
        if str(s.get('fk_teacher','')).strip() == teacher_id:
            # Module name
            s['moduleName'] = modules.get(s.get('fk_module'), {}).get('moduleName', 'Unknown Module')
            
            # Use groupCode as the displayed group name
            group_doc = groups_collection.get(s.get('fk_group'), {})
            s['groupName'] = group_doc.get('groupCode', s.get('fk_group'))  # fallback to fk_group if missing
            s['groupCode'] = group_doc.get('groupCode', s.get('fk_group'))
            
            # Program name
            s['programName'] = programs.get(s.get('fk_program'), {}).get('programName', 'Unknown Program')
            
            # Start and End time
            s['startTime'] = s.get('start_time', 'Unknown Start')
            s['endTime'] = s.get('end_time', 'Unknown End')
            
            # Day and Room
            s['day'] = s.get('day', 'Unknown Day')
            s['room'] = s.get('room', 'Unknown Room')

            schedules.append(s)

    # Teacher profile
    profile_doc = db.collection("users").document(teacher_id).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {"name": "Teacher"}

    return render_template(
        "teacher/T_Schedule.html",
        schedules=schedules,
        programs=programs,
        groups=groups_collection,
        modules=modules,
        profile=profile
    )

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



    

# Helper to generate a unique studentID
def generate_student_id():
    return "STU" + str(random.randint(1000, 9999))  # simple random ID
# ------------------ Admin Student Add Page ------------------
@app.route("/admin/student_add")
def admin_student_add():
    # Fetch all programs
    programs_docs = db.collection("programs").stream()
    programs = []
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)

    # Fetch all groups
    groups_docs = db.collection("groups").stream()
    groups = []
    for doc in groups_docs:
        g = doc.to_dict()
        g["docId"] = doc.id
        groups.append(g)

    # Fetch all students
    students_docs = db.collection("users").where("role_type", "==", 1).stream()
    students = []

    for doc in students_docs:
        s = doc.to_dict()
        s["uid"] = doc.id

        # Fetch student role info
        role_doc = db.collection("users").document(s["uid"]).collection("roles").document("student").get()
        if role_doc.exists:
            role = role_doc.to_dict()
            s["studentID"] = role.get("studentID", "")
            s["fk_groupcode"] = role.get("fk_groupcode", "")
            s["program"] = role.get("program", "")
        else:
            s["studentID"] = ""
            s["fk_groupcode"] = ""
            s["program"] = ""

        # Group name from document ID
        if s["fk_groupcode"]:
            group_doc = db.collection("groups").document(s["fk_groupcode"]).get()
            s["groupName"] = group_doc.to_dict().get("groupName") if group_doc.exists else ""
        else:
            s["groupName"] = ""

        # Program name
        if s.get("program"):
            program_doc = db.collection("programs").document(s["program"]).get()
            s["programName"] = program_doc.to_dict().get("programName", "") if program_doc.exists else ""
        else:
            s["programName"] = ""

        # Include photo
        s["photo_name"] = s.get("photo_name", "")

        students.append(s)

    return render_template(
        "admin/A_Student-Add.html",
        programs=programs,
        groups=groups,
        students=students
    )


# ------------------ Save (Add/Edit) Student ------------------
UPLOAD_FOLDER = "student_pics"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/admin/student/save', methods=['POST'])
def admin_student_save():
    student_id = request.form.get('userId')
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    email = request.form['email']
    password = request.form.get('password')
    program = request.form['program']

    display_name = f"{first_name} {last_name}"

    # Auto-generate studentID
    import random, string
    studentID = ''.join(random.choices(string.digits, k=6))

    # Auto-assign first group of the program (document ID)
    group_docs = db.collection('groups').where('program', '==', program).limit(1).stream()
    fk_groupcode = ""
    for g in group_docs:
        fk_groupcode = g.id
        break

    # Handle photo upload
    photo_file = request.files.get("photo")
    photo_name = None
    if photo_file and allowed_file(photo_file.filename):
        ext = photo_file.filename.rsplit(".", 1)[1].lower()
        photo_name = f"{student_id}.{ext}"
        photo_file.save(os.path.join(UPLOAD_FOLDER, photo_name))

    if student_id:
        # Update existing student
        try:
            if password:
                auth.update_user(student_id, email=email, display_name=display_name, password=password)
            else:
                auth.update_user(student_id, email=email, display_name=display_name)
        except exceptions.FirebaseError as e:
            flash(f"Error updating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_student_add"))

        student_data = {
            'first_name': first_name,
            'last_name': last_name,
            'name': display_name,
            'email': email,
            'active': True,
            'role_type': 1
        }

        if photo_name:
            student_data['photo_name'] = photo_name

        db.collection('users').document(student_id).update(student_data)
        db.collection('users').document(student_id).collection('roles').document('student').set({
            'studentID': studentID,
            'fk_groupcode': fk_groupcode,  # ⚡ group ID
            'program': program
        })

    else:
        # Add new student
        try:
            user = auth.create_user(email=email, password=password or "password123", display_name=display_name)
            student_id = user.uid
        except exceptions.FirebaseError as e:
            flash(f"Error creating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_student_add"))

        student_data = {
            'user_id': student_id,
            'first_name': first_name,
            'last_name': last_name,
            'name': display_name,
            'email': email,
            'active': True,
            'role_type': 1,
            'photo_name': photo_name if photo_name else f"{student_id}.jpg"
        }

        db.collection('users').document(student_id).set(student_data)
        db.collection('users').document(student_id).collection('roles').document('student').set({
            'studentID': studentID,
            'fk_groupcode': fk_groupcode,  # ⚡ group ID
            'program': program
        })

    return redirect(url_for('admin_student_add'))


# ------------------ Upload Students via CSV ------------------
@app.route("/admin/student_upload", methods=["POST"])
def admin_student_upload():
    if session.get("role") != "admin":
        return redirect(url_for("admin_dashboard"))

    if "csv_file" not in request.files or request.files["csv_file"].filename == "":
        flash("No file selected", "error")
        return redirect(url_for("admin_student_add"))

    file = request.files["csv_file"]

    import csv, io, random, string
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    for row in reader:
        first_name = row.get("first_name")
        last_name = row.get("last_name")
        email = row.get("email")
        password = row.get("password") or "password123"
        program = row.get("program")

        if not first_name or not last_name or not email or not program:
            continue

        studentID = ''.join(random.choices(string.digits, k=6))

        # Auto-assign first group of the program
        group_docs = db.collection('groups').where('program', '==', program).limit(1).stream()
        fk_groupcode = ""
        for g in group_docs:
            fk_groupcode = g.id
            break

        try:
            display_name = f"{first_name} {last_name}"
            user = auth.create_user(email=email, password=password, display_name=display_name)
            student_id = user.uid
        except exceptions.FirebaseError:
            continue

        # Save user to Firestore
        db.collection('users').document(student_id).set({
            'user_id': student_id,
            'first_name': first_name,
            'last_name': last_name,
            'name': display_name,
            'email': email,
            'active': True,
            'role_type': 1,
            'photo_name': f"{student_id}.jpg"
        })

        db.collection('users').document(student_id).collection('roles').document('student').set({
            'studentID': studentID,
            'fk_groupcode': fk_groupcode,  # ⚡ group ID
            'program': program
        })

    flash("CSV uploaded successfully", "success")
    return redirect(url_for("admin_student_add"))


# ------------------ API to get student data for edit ------------------
@app.route("/api/student/<uid>")
def api_student(uid):
    s_doc = db.collection("users").document(uid).get()
    if not s_doc.exists:
        return jsonify({}), 404
    s = s_doc.to_dict()
    role_doc = db.collection("users").document(uid).collection("roles").document("student").get()
    if role_doc.exists:
        role = role_doc.to_dict()
        s["studentID"] = role.get("studentID", "")
        s["program"] = role.get("program", "")
        s["fk_groupcode"] = role.get("fk_groupcode", "")  # ⚡ ID
    return jsonify(s)


# ------------------ Serve student photos ------------------
@app.route('/student_pics/<filename>')
def student_photo(filename):
    return send_from_directory('student_pics', filename)


# ------------------ Delete Student ------------------
@app.route("/admin/student/delete/<uid>", methods=["POST"])
def admin_student_delete(uid):
    try:
        # Delete Firestore documents
        db.collection("users").document(uid).delete()
        # Delete Auth user
        auth.delete_user(uid)
        flash("Student deleted successfully", "success")
    except Exception as e:
        flash(f"Error deleting student: {str(e)}", "error")
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
    program_map = {}  # Map program doc ID -> programName
    for doc in programs_docs:
        p = doc.to_dict()
        p["docId"] = doc.id
        programs.append(p)
        program_map[doc.id] = p.get("programName", "")

    # Fetch all teachers
    teachers_docs = db.collection("users").where("role_type", "==", 2).stream()
    teachers = []
    for doc in teachers_docs:
        t = doc.to_dict()
        t["uid"] = doc.id

        # Fetch roles
        role_doc = db.collection("users").document(t["uid"]).collection("roles").document("teacher").get()
        if role_doc.exists:
            role = role_doc.to_dict()
            t["program"] = role.get("program", "")
            t["teacherID"] = role.get("teacherID", "")
            t["isCoordinator"] = role.get("isCoordinator", False)
            t["programName"] = program_map.get(t["program"], "")  # <-- Add program name
        else:
            t["program"] = ""
            t["teacherID"] = ""
            t["isCoordinator"] = False
            t["programName"] = ""

        t["firstName"] = t.get("firstName", "")
        t["lastName"] = t.get("lastName", "")
        t["photo"] = t.get("photo", "")

        teachers.append(t)

    return render_template(
        "admin/A_Teacher-Add.html",
        programs=programs,
        teachers=teachers
    )


# ------------------ Save (Add/Edit) Teacher ------------------
@app.route('/admin/teacher/save', methods=['POST'])
def admin_teacher_save():
    teacher_id = request.form.get('userId')  # Firestore UID if editing
    firstName = request.form['firstName']
    lastName = request.form['lastName']
    email = request.form['email']
    password = request.form.get('password')
    program = request.form['program']
    teacherID = request.form['teacherID']
    isCoordinator = request.form.get('isCoordinator') == 'on'  # checkbox in form

    display_name = f"{firstName} {lastName}"

    if teacher_id:
        # -------- Update existing user --------
        try:
            if password:
                auth.update_user(teacher_id, email=email, display_name=display_name, password=password)
            else:
                auth.update_user(teacher_id, email=email, display_name=display_name)
        except exceptions.FirebaseError as e:
            flash(f"Error updating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_teacher_add"))

        db.collection('users').document(teacher_id).update({
            'firstName': firstName,
            'lastName': lastName,
            'email': email,
            'active': True,
            'role_type': 2,
            'photo_name': ''
        })

        db.collection('users').document(teacher_id).collection('roles').document('teacher').set({
            'program': program,
            'teacherID': teacherID,
            'isCoordinator': isCoordinator
        })

    else:
        # -------- Add new teacher --------
        try:
            user = auth.create_user(email=email, password=password or "password123", display_name=display_name)
            teacher_id = user.uid
        except exceptions.FirebaseError as e:
            flash(f"Error creating Auth user: {str(e)}", "error")
            return redirect(url_for("admin_teacher_add"))

        db.collection('users').document(teacher_id).set({
            'user_id': teacher_id,
            'firstName': firstName,
            'lastName': lastName,
            'email': email,
            'active': True,
            'role_type': 2,
            'photo_name': ''
        })

        db.collection('users').document(teacher_id).collection('roles').document('teacher').set({
            'program': program,
            'teacherID': teacherID,
            'isCoordinator': isCoordinator
        })

    return redirect(url_for('admin_teacher_add'))

# ------------------ Get Teacher for Edit Modal ------------------
@app.route('/api/teacher/<uid>')
def api_get_teacher(uid):
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        return jsonify({"error": "Teacher not found"}), 404

    teacher = user_doc.to_dict()

    # Fetch roles
    role_doc = db.collection("users").document(uid).collection("roles").document("teacher").get()
    if role_doc.exists:
        role = role_doc.to_dict()
        teacher["program"] = role.get("program", "")
        teacher["teacherID"] = role.get("teacherID", "")
        teacher["isCoordinator"] = role.get("isCoordinator", False)
    else:
        teacher["program"] = ""
        teacher["teacherID"] = ""
        teacher["isCoordinator"] = False

    return jsonify(teacher)


@app.route('/admin/teacher/delete/<uid>', methods=['POST'])
def admin_teacher_delete(uid):
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        # Try deleting user from Firebase Auth
        auth.delete_user(uid)
    except exceptions.NotFoundError:
        # If user doesn't exist in Auth, just skip
        pass
    except exceptions.FirebaseError as e:
        return jsonify({"error": str(e)}), 400

    # Delete Firestore user document anyway
    db.collection("users").document(uid).delete()

    return jsonify({"success": True})


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

# ------------------ Admin Assign Modules to Teachers ------------------
@app.route("/admin/teacher_assign", methods=["GET", "POST"])
def admin_teacher_assign():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    if request.method == "POST":
        # Handle module assignment form submission
        teacher_id = request.form.get("teacher_id")
        module_id = request.form.get("module_id")
        group_id = request.form.get("group_id")

        if teacher_id and module_id and group_id:
            # Fetch module and group info
            module_doc = db.collection("modules").document(module_id).get()
            group_doc = db.collection("groups").document(group_id).get()
            module_data = module_doc.to_dict() if module_doc.exists else {}
            group_data = group_doc.to_dict() if group_doc.exists else {}

            # Save directly to mlmodule (no teacher_assignments)
            db.collection("mlmodule").add({
                "group_code": group_data.get("groupCode", ""),
                "moduleName": module_data.get("moduleName", ""),
                "status": "active",
                "teacherID": teacher_id
            })

            flash("Module assigned to teacher successfully!", "success")
        else:
            flash("Please select all fields before submitting.", "error")

        return redirect(url_for("admin_teacher_assign"))

    # ------------------ GET: fetch data for page ------------------
    # Fetch all teachers
    users_docs = db.collection("users").where("role_type", "==", 2).stream()
    teachers = []
    for doc in users_docs:
        t = doc.to_dict()
        t["docId"] = doc.id
        t["firstName"] = t.get("firstName", "")
        t["lastName"] = t.get("lastName", "")
        t["email"] = t.get("email", "")

        # Fetch roles/teacher subcollection
        role_doc = (
            db.collection("users")
              .document(t["docId"])
              .collection("roles")
              .document("teacher")
              .get()
        )
        if role_doc.exists:
            role = role_doc.to_dict()
            t["program"] = role.get("program", "")
        else:
            t["program"] = ""

        # Fetch current assignments from mlmodule
        assignments_docs = (
            db.collection("mlmodule")
              .where("teacherID", "==", t["docId"])
              .stream()
        )
        t["assignments"] = [a_doc.to_dict() for a_doc in assignments_docs]

        teachers.append(t)

    # Fetch programs
    programs_docs = db.collection("programs").stream()
    programs_map = {doc.id: doc.to_dict().get("programName", "") for doc in programs_docs}

    # Fetch groups
    groups_docs = db.collection("groups").stream()
    groups = [{"docId": doc.id, **doc.to_dict()} for doc in groups_docs]

    # Fetch modules
    modules_docs = db.collection("modules").stream()
    modules = [{"docId": doc.id, **doc.to_dict()} for doc in modules_docs]

    return render_template(
        "admin/A_Teacher-Assign.html",
        teachers=teachers,
        programs_map=programs_map,
        groups=groups,
        modules=modules,
    )

# ------------------ Admin Schedule page ------------------
@app.route("/admin/schedules")
def admin_schedules():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    # Fetch supporting data
    programs = [{**p.to_dict(), "docId": p.id} for p in db.collection("programs").stream()]
    groups = [{**g.to_dict(), "docId": g.id} for g in db.collection("groups").stream()]
    modules = [{**m.to_dict(), "docId": m.id} for m in db.collection("modules").stream()]

    # Fetch teachers from users collection (role_type == 2)
    teachers_docs = db.collection("users").where("role_type", "==", 2).stream()
    teachers = []
    for doc in teachers_docs:
        t = doc.to_dict()
        t["docId"] = doc.id

        # Fetch role info
        role_doc = db.collection("users").document(t["docId"]).collection("roles").document("teacher").get()
        if role_doc.exists:
            role = role_doc.to_dict()
            t["program"] = role.get("program", "")
            t["module"] = role.get("module", "")
            t["teacherID"] = role.get("teacherID", "")
        else:
            t["program"] = ""
            t["module"] = ""
            t["teacherID"] = ""

        # Precompute full name
        t["fullName"] = f"{t.get('firstName','')} {t.get('lastName','')}".strip()
        teachers.append(t)

    # ✅ Sort teachers by full name (case-insensitive)
    teachers.sort(key=lambda t: t.get("fullName", "").lower())

    # Fetch schedules and attach teacher names
    schedules = []
    for doc in db.collection("schedules").stream():
        s = doc.to_dict()
        s["docId"] = doc.id

        # Match teacher and set full name
        teacher = next((t for t in teachers if t["docId"] == s.get("fk_teacher")), None)
        s["teacher_name"] = teacher.get("fullName", "") if teacher else ""

        schedules.append(s)

    # Get selected teacher for timetable view
    selected_teacher_id = request.args.get("teacher_id")
    selected_teacher = next((t for t in teachers if t["docId"] == selected_teacher_id), None)

    return render_template(
        "admin/A_Schedule-Upload.html",
        programs=programs,
        groups=groups,
        modules=modules,
        teachers=teachers,
        schedules=schedules,
        selected_teacher=selected_teacher
    )

# ------------------ Save/Add/Edit Schedule ------------------
@app.route("/admin/schedule/save", methods=["POST"])
def admin_schedule_save():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    schedule_id = request.form.get("scheduleId")
    schedule_data = {
        "fk_program": request.form.get("fk_program"),
        "fk_group": request.form.get("fk_group"),
        "fk_module": request.form.get("fk_module"),
        "fk_teacher": request.form.get("fk_teacher"),
        "day": request.form.get("day"),
        "start_time": request.form.get("start_time"),
        "end_time": request.form.get("end_time"),
        "room": request.form.get("room")
    }

    if schedule_id:
        # Update existing schedule
        db.collection("schedules").document(schedule_id).set(schedule_data, merge=True)
    else:
        # Add new schedule
        db.collection("schedules").add(schedule_data)

    flash("Schedule saved successfully!", "success")
    return redirect(url_for("admin_schedules"))

# ------------------ Delete Schedule ------------------
@app.route("/admin/schedule/delete/<schedule_id>", methods=["POST"])
def admin_schedule_delete(schedule_id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    db.collection("schedules").document(schedule_id).delete()
    flash("Schedule deleted successfully!", "success")
    return redirect(url_for("admin_schedules"))


# ------------------ CSV Upload ------------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"csv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/admin/schedule/upload_csv", methods=["POST"])
def admin_schedule_upload_csv():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    if "file" not in request.files or request.files["file"].filename == "":
        flash("No file selected!", "error")
        return redirect(url_for("admin_schedules"))

    file = request.files["file"]
    if file and allowed_file(file.filename):
        if not os.path.exists(app.config["UPLOAD_FOLDER"]):
            os.makedirs(app.config["UPLOAD_FOLDER"])

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        import csv  # Make sure csv is imported

        with open(filepath, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                db.collection("schedules").add({
                    "fk_program": row["program"],
                    "fk_group": row["group"],
                    "fk_module": row["module"],
                    "fk_teacher": row["teacher"],
                    "day": row["day"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "room": row["room"]
                })

        flash("CSV uploaded successfully!", "success")
    else:
        flash("Invalid file type!", "error")

    return redirect(url_for("admin_schedules"))



# ------------------ Other Admin Pages ------------------

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