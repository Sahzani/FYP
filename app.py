from flask import Flask, render_template, request, redirect, url_for, session, flash
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import timedelta
import os

# ------------------ Flask Setup ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)  # Flask will look for templates in ./templates by default
app.secret_key = "supersecretkey"  # change this in production
app.permanent_session_lifetime = timedelta(days=30)

# ------------------ Firebase Setup ------------------
cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

db = firestore.client()

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("combinePage/Login.html")  # your login page

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")
    remember = request.form.get("remember")

    if not email or not password:
        flash("Please enter both email and password.")
        return redirect(url_for("home"))

    try:
        # Step 1: Verify user exists in Firebase Auth
        user = auth.get_user_by_email(email)
        uid = user.uid

        # Step 2: Look through collections
        collections = {
            "student": "students",
            "teacher": "teachers",
            "admin": "admins"
        }

        role = None
        user_doc = None

        # Try each collection until match
        for role_name, collection_name in collections.items():
            docs = db.collection(collection_name).where("uid", "==", uid).stream()
            for doc in docs:
                user_doc = doc.to_dict()
                role = role_name
                break
            if role:  # found user
                break

        if not user_doc:
            flash("User not found in Firestore.")
            return redirect(url_for("home"))

        # Step 3: Set session
        session["user"] = email
        session["role"] = role
        session.permanent = True if remember == "on" else False

        # Step 4: Redirect by role
        if role == "student":
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher_dashboard"))
        elif role == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

    except auth.UserNotFoundError:
        flash("Invalid email or password")
        return redirect(url_for("home"))

# ------------------ Student Dashboard ------------------
@app.route("/student_dashboard")
def student_dashboard():
    if "user" in session and session.get("role") == "student":
        return render_template("student/S_Dashboard.html")
    return redirect(url_for("home"))

# ------------------ Teacher Dashboard ------------------
@app.route("/teacher_dashboard")
def teacher_dashboard():
    if "user" in session and session.get("role") == "teacher":
        return render_template("teacher/T_dashboard.html")
    return redirect(url_for("home"))

# ------------------ Admin Dashboard & Pages ------------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if "user" in session and session.get("role") == "admin":
        return render_template("admin/A_Homepage.html")
    return redirect(url_for("home"))

@app.route("/admin/student_add")
def admin_student_add():
    if "user" in session and session.get("role") == "admin":
        return render_template("admin/A_Student-Add.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_add")
def admin_teacher_add():
    if "user" in session and session.get("role") == "admin":
        return render_template("admin/A_Teacher-Add.html")
    return redirect(url_for("home"))

@app.route("/admin/student_list")
def admin_student_list():
    if "user" in session and session.get("role") == "admin":
        return render_template("admin/A_Student-List.html")
    return redirect(url_for("home"))

@app.route("/admin/teacher_list")
def admin_teacher_list():
    if "user" in session and session.get("role") == "admin":
        return render_template("admin/A_Teacher-List.html")
    return redirect(url_for("home"))

# ------------------ Logout ------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    return redirect(url_for("home"))

# ------------------ Signup placeholder ------------------
@app.route("/signup")
def signup():
    return "Signup page coming soon!"

# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
