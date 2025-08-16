from flask import Flask, render_template, request, redirect, url_for, flash, session
import pyrebase

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change to something stronger

# ------------------ Firebase Config ------------------
firebaseConfig = {
    "apiKey": "your_api_key",
    "authDomain": "your_project_id.firebaseapp.com",
    "databaseURL": "https://your_project_id.firebaseio.com",
    "projectId": "your_project_id",
    "storageBucket": "your_project_id.appspot.com",
    "messagingSenderId": "your_sender_id",
    "appId": "your_app_id"
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()


# ------------------ Combine Pages ------------------
@app.route('/')
def login():
    return render_template('combinePage/Login.html')

@app.route('/signup')
def signup():
    return render_template('combinePage/Sign-up.html')

@app.route('/forget-password')
def forget_password():
    return render_template('combinePage/Forget Password.html')

@app.route('/background')
def background():
    return render_template('combinePage/background.html')

@app.route('/combine-admin')
def combine_admin():
    return render_template('combinePage/admin.html')


# ------------------ Auth Routes ------------------
@app.route('/signup', methods=['POST'])
def signup_post():
    """Handles signup with Firebase and assigns a role"""
    email = request.form['email']
    password = request.form['password']
    role = request.form.get('role')  # e.g., Admin, Teacher, Student

    try:
        user = auth.create_user_with_email_and_password(email, password)
        uid = user['localId']

        # Save role to database
        db.child("users").child(uid).set({
            "email": email,
            "role": role
        })

        flash("Sign up successful! Please login.", "success")
        return redirect(url_for("login"))

    except Exception as e:
        flash("Signup failed: " + str(e), "danger")
        return redirect(url_for("signup"))


@app.route('/login', methods=['POST'])
def login_post():
    """Handles login and redirects based on role"""
    email = request.form['email']
    password = request.form['password']

    try:
        user = auth.sign_in_with_email_and_password(email, password)
        uid = user['localId']
        session['user'] = uid

        # Get role from Firebase and normalize it
        role = db.child("users").child(uid).child("role").get().val()
        if role:
            role_clean = role.strip().lower()
        else:
            role_clean = ""

        print(f"DEBUG: UID={uid}, role='{role}', normalized='{role_clean}'")  # debug print

        if role_clean == "admin":
            return redirect(url_for("admin_home"))
        elif role_clean == "teacher":
            return redirect(url_for("teacher_dashboard"))
        elif role_clean == "student":
            return redirect(url_for("student_dashboard"))
        else:
            flash("Role not assigned or invalid. Contact admin.", "danger")
            return redirect(url_for("login"))

    except Exception as e:
        flash("Login failed: " + str(e), "danger")
        return redirect(url_for("login"))


@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ------------------ Admin Pages ------------------
@app.route('/admin/home')
def admin_home():
    return render_template('admin/A_Homepage.html')

@app.route('/admin/user-list')
def admin_user_list():
    return render_template('admin/A_All_User_List.html')

@app.route('/admin/add-delete-user')
def admin_add_delete():
    return render_template('admin/A_Add_Delete_User.html')

@app.route('/admin/approve-student')
def admin_approve_student():
    return render_template('admin/A_ApproveStuApplication.html')

@app.route('/admin/attend-record')
def admin_attend_record():
    return render_template('admin/A_attend_record_page.html')

@app.route('/admin/class-management')
def admin_class_management():
    return render_template('admin/A_Class-management.html')

@app.route('/admin/face-recognition')
def admin_face_recognition():
    return render_template('admin/A_FaceRecognition.html')

@app.route('/admin/system-log')
def admin_system_log():
    return render_template('admin/A_SystemSettingLog.html')

@app.route('/admin/teacher-add')
def admin_teacher_add():
    return render_template('admin/A_Teacher-Add.html')

@app.route('/admin/teacher-list')
def admin_teacher_list():
    return render_template('admin/A_Teacher-List.html')


# ------------------ Student Pages ------------------
@app.route('/student/dashboard')
def student_dashboard():
    return render_template('student/S_Dashboard.html')

@app.route('/student/absentapp')
def student_absentapp():
    return render_template('student/S_AbsentApp.html')

@app.route('/student/history')
def student_history():
    return render_template('student/S_History.html')

@app.route('/student/profile')
def student_profile():
    return render_template('student/S_Profile.html')


# ------------------ Teacher Pages ------------------
@app.route('/teacher/dashboard')
def teacher_dashboard():
    return render_template('teacher/T_dashboard.html')

@app.route('/teacher/login')
def teacher_login():
    return render_template('teacher/T_login.html')

@app.route('/teacher/class-list')
def teacher_class_list():
    return render_template('teacher/T_class_list.html')

@app.route('/teacher/attendance-report')
def teacher_attendance_report():
    return render_template('teacher/T_attendance_report.html')

@app.route('/teacher/start-attendance')
def teacher_start_attendance():
    return render_template('teacher/T_StartAttendance.html')


if __name__ == '__main__':
    app.run(debug=True)
