from flask import Flask, render_template, request, redirect, url_for, session, flash
import firebase_admin
from firebase_admin import credentials, auth
from datetime import timedelta
import os

# Get the folder of this app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask app with correct templates folder
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "../templates"))
app.secret_key = "supersecretkey"  # change this to something strong in production

# Make sessions last longer if "Remember me" is checked
app.permanent_session_lifetime = timedelta(days=30)

# ------------------ Initialize Firebase Admin ------------------
cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")  # file is in the same folder as app.py
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("combinePage/Login.html")  # your login page

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")
    remember = request.form.get("remember")  # will be 'on' if checked

    if not email or not password:
        flash("Please enter both email and password.")
        return redirect(url_for("home"))

    try:
        # Firebase Admin SDK cannot verify password directly
        # Here we just check if the user exists
        user = auth.get_user_by_email(email)

        # Get custom claims (role)
        claims = user.custom_claims
        role = claims.get("role") if claims else None

        if role not in ["student", "teacher", "admin"]:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

        # Set session
        session["user"] = email
        session.permanent = True if remember == "on" else False

        if role == "student":
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher_dashboard"))
        else:  # admin
            return redirect(url_for("admin_dashboard"))

    except auth.UserNotFoundError:
        flash("Invalid email or password")
        return redirect(url_for("home"))

# ------------------ Dashboards ------------------
@app.route("/student_dashboard")
def student_dashboard():
    if "user" in session:
        return "Welcome to the Student Dashboard!"
    return redirect(url_for("home"))

@app.route("/teacher_dashboard")
def teacher_dashboard():
    if "user" in session:
        return "Welcome to the Teacher Dashboard!"
    return redirect(url_for("home"))

@app.route("/admin_dashboard")
def admin_dashboard():
    if "user" in session:
        return "Welcome to the Admin Dashboard!"
    return redirect(url_for("home"))

# ------------------ Logout ------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

# ------------------ Signup placeholder ------------------
@app.route("/signup")
def signup():
    return "Signup page coming soon!"

# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
