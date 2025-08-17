from flask import Flask, render_template, request, redirect, url_for, flash, session
import pyrebase

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change to something stronger

# ------------------ Firebase Config ------------------
firebaseConfig = {
    "apiKey": "AIzaSyC_pq3Gnzwkdvc9CPeRa3Yre_vkcijzVpk",
    "authDomain": "aimanzamani.firebaseapp.com",
    "databaseURL": "https://aimanzamani-default-rtdb.asia-southeast1.firebasedatabase.app/",
    "projectId": "aimanzamani",
    "storageBucket": "aimanzamani.appspot.com",
    "messagingSenderId": "63348630728",
    "appId": "1:63348630728:web:5d1537bd1c6e14535171fd"
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()

# ------------------ Auth Pages ------------------
@app.route('/')
def login():
    return render_template('combinePage/Login.html')

@app.route('/signup')
def signup():
    return render_template('combinePage/Sign-up.html')

@app.route('/forget-password')
def forget_password():
    return render_template('combinePage/Forget Password.html')

# ------------------ Signup POST ------------------
@app.route('/signup', methods=['POST'])
def signup_post():
    email = request.form['email']
    password = request.form['password']
    role = request.form.get('role')  # Admin, Teacher, Student

    try:
        user = auth.create_user_with_email_and_password(email, password)
        uid = user['localId']

        # Save role to Firebase database
        db.child("users").child(uid).set({
            "email": email,
            "role": role
        })

        flash("Sign up successful! Please login.", "success")
        return redirect(url_for("login"))

    except Exception as e:
        flash("Signup failed: " + str(e), "danger")
        return redirect(url_for("signup"))

# ------------------ Login POST ------------------
@app.route('/login', methods=['POST'])
def login_post():
    email = request.form['email']
    password = request.form['password']

    try:
        # Sign in with Firebase Authentication
        user = auth.sign_in_with_email_and_password(email, password)
        uid = user['localId']
        session['user'] = uid

        # Directly get the role from UID
        role = db.child("users").child(uid).child("role").get().val()
        role_clean = role.strip().lower() if role else ""

        # Redirect based on role
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

# ------------------ Logout ------------------
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
