from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__, template_folder="../templates")
app.secret_key = "supersecretkey"  # change this later for security

# Temporary users for testing (later replace with Firebase)
users = {
    "student@example.com": {"password": "student123", "role": "student"},
    "teacher@example.com": {"password": "teacher123", "role": "teacher"}
}

@app.route("/")
def home():
    return render_template("combinePage/Login.html")  # your login page

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

    if email in users and users[email]["password"] == password:
        session["user"] = email
        role = users[email]["role"]

        if role == "student":
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher_dashboard"))
    else:
        flash("Invalid email or password")
        return redirect(url_for("home"))

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

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

# Optional placeholder signup route if your Login.html still has the link
@app.route("/signup")
def signup():
    return "Signup page coming soon!"

if __name__ == "__main__":
    app.run(debug=True)
from flask import Flask, render_template, request, redirect, url_for, session, flash
import firebase_admin
from firebase_admin import credentials, auth

app = Flask(__name__, template_folder="../templates")
app.secret_key = "supersecretkey"  # Change this to something strong in production

# ------------------ Initialize Firebase Admin ------------------
cred = credentials.Certificate("../serviceAccountKey.json")  # path to your downloaded key
firebase_admin.initialize_app(cred)

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("combinePage/Login.html")  # your login page

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

    try:
        # Sign in user with Firebase Auth
        user = auth.get_user_by_email(email)  # get UID from email
        uid = user.uid

        # NOTE: Firebase Admin SDK doesn't verify password directly.
        # For testing, you can use pyrebase or Firebase Client SDK in front-end.
        # Here, we just check if the user exists.

        # Get custom claims (role)
        claims = user.custom_claims
        role = claims.get("role") if claims else None

        if role == "student":
            session["user"] = email
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            session["user"] = email
            return redirect(url_for("teacher_dashboard"))
        elif role == "admin":
            session["user"] = email
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

    except auth.UserNotFoundError:
        flash("Invalid email or password")
        return redirect(url_for("home"))

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

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

# Optional placeholder signup route if your Login.html still has the link
@app.route("/signup")
def signup():
    return "Signup page coming soon!"

# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
