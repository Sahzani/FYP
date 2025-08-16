from flask import Flask, render_template

app = Flask(__name__)

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
