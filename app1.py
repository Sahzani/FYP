from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import timedelta
import os
# hani buats ada changes sikit if this works
# ------------------ Flask Setup ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.secret_key = "supersecretkey"  # CHANGE THIS IN PRODUCTION
app.permanent_session_lifetime = timedelta(days=30)

# ------------------ Firebase Admin Setup ------------------
# IMPORTANT: Replace 'serviceAccountKey.json' with your actual Firebase service account key file path.
cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
try:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")

# ------------------ Routes ------------------
@app.route("/")
def home():
    """
    Handles the main login page. If a user is already authenticated,
    it redirects them to their respective dashboard.
    """
    if "user" in session and session.get("role"):
        return redirect(url_for(f"{session.get('role')}_dashboard"))
    # Assumes the HTML file is located at templates/Login.html
    return render_template("Login.html")

@app.route("/login", methods=["POST"])
def login():
    """
    The secure login endpoint that receives and verifies a Firebase ID Token.
    It does NOT receive a password. Password validation is handled on the client-side
    with Firebase's SDK.
    """
    # Get the ID Token and 'remember me' status from the POST request
    id_token = request.form.get("id_token")
    remember = request.form.get("remember")

    # Ensure a token was provided
    if not id_token:
        flash("Authentication failed. Please try again.")
        return redirect(url_for("home"))

    try:
        # Step 1: Verify the ID Token with the Firebase Admin SDK.
        # This is the most crucial security step. It proves the user has
        # successfully authenticated with Firebase.
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        user_email = decoded_token['email']

        # Step 2: Find the user's role in Firestore using the verified UID.
        collections = {
            "student": "students",
            "teacher": "teachers",
            "admin": "admins"
        }

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
            flash("User not found in Firestore. Contact an admin to get a role.")
            return redirect(url_for("home"))

        # Step 3: Set session variables for the authenticated user
        session["user"] = user_email
        session["role"] = role
        session.permanent = True if remember == "on" else False

        # Step 4: Redirect to the appropriate dashboard based on their role
        if role == "student":
            return redirect(url_for("student_dashboard"))
        elif role == "teacher":
            return redirect(url_for("teacher_dashboard"))
        elif role == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Role not assigned. Contact admin.")
            return redirect(url_for("home"))

    except auth.InvalidIdTokenError:
        # Catch if the token is invalid (e.g., expired, tampered with)
        flash("Invalid token. Please sign in again.")
        return redirect(url_for("home"))
    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"Login error: {e}")
        flash("An unexpected error occurred. Please try again.")
        return redirect(url_for("home"))

# ------------------ Dashboards ------------------
@app.route("/student_dashboard")
def student_dashboard():
    # Protects the route by ensuring the user is in the session and has the correct role.
    if "user" in session and session.get("role") == "student":
        # Assumes the template is at templates/student/S_Dashboard.html
        return render_template("student/S_Dashboard.html")
    return redirect(url_for("home"))

@app.route("/teacher_dashboard")
def teacher_dashboard():
    # Protects the route
    if "user" in session and session.get("role") == "teacher":
        # Assumes the template is at templates/teacher/T_dashboard.html
        return render_template("teacher/T_dashboard.html")
    return redirect(url_for("home"))

@app.route("/admin_dashboard")
def admin_dashboard():
    # Protects the route
    if "user" in session and session.get("role") == "admin":
        # Assumes the template is at templates/admin/A_Homepage.html
        return render_template("admin/A_Homepage.html")
    return redirect(url_for("home"))

# ------------------ Logout ------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    return redirect(url_for("home"))

# ------------------ Signup placeholder ------------------
# You would need to add a similar secure process for user signup.
@app.route("/signup")
def signup():
    return "Signup page coming soon!"

# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
