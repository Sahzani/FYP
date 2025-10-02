import os
import cv2
import threading
import time
import numpy as np
from datetime import datetime
from flask import Flask, Response, request
import face_recognition
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from flask_cors import CORS  # Enable CORS for cross-origin requests

# ===== Firebase Setup =====
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ===== Flask Setup =====
app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from app.py

# ===== Global Variables =====
STUDENTS = {}
encodings, classNames = [], []
latest_frame = None
frame_lock = threading.Lock()
camera_thread = None
camera_running = False
current_schedule = None  # Stores selected schedule

API_URL = "http://127.0.0.1:8000"  # URL of app.py

# ===== Wait for API =====
def wait_for_api(url, timeout=30):
    for _ in range(timeout):
        try:
            r = requests.get(url)
            if r.status_code == 200:
                print("[INFO] API is ready!")
                return True
        except:
            pass
        time.sleep(1)
    print("[ERROR] Could not reach API.")
    return False
# ===== Load Students and Encodings =====
def load_students():
    global STUDENTS, encodings, classNames
    response = requests.get(f"{API_URL}/api/students")
    data_list = response.json()
    
    encodings, classNames = [], []

    for data in data_list:
        student_id = data["id"]
        STUDENTS[student_id] = data

        # Fetch student role for group
        role_doc = db.collection("users").document(student_id).collection("roles").document("student").get()
        group_code = role_doc.to_dict().get("fk_groupcode", "") if role_doc.exists else ""
        STUDENTS[student_id]["fk_groupcode"] = group_code
        STUDENTS[student_id]["program"] = role_doc.to_dict().get("program", "") if role_doc.exists else ""

        photo_name = data.get("photo_name", "")
        photo_path = os.path.join(app.static_folder, "student_pics", group_code, photo_name)
        if not os.path.exists(photo_path):
            print(f"[WARN] File not found: {photo_path}")
            continue

        img = cv2.imread(photo_path)
        if img is None:
            continue

        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_enc = face_recognition.face_encodings(rgb_img)
        if face_enc:
            encodings.append(face_enc[0])
            classNames.append(student_id)
            print(f"[INFO] Loaded encoding for {data.get('name')} ({student_id})")

    print(f"[INFO] Total encodings loaded: {len(encodings)}")


# ===== Attendance =====
attended_today = {}

def mark_attendance(student_id):
    global current_schedule
    today = datetime.now().strftime("%Y-%m-%d")
    
    if not current_schedule:
        print("[WARN] No schedule selected")
        return None

    schedule_id = current_schedule.get("schedule_id")
    key = (student_id, schedule_id, today)
    if attended_today.get(key):
        return None  # Already marked today

    attended_today[key] = True
    s = STUDENTS.get(student_id, {})

    # Use fk_groupcode and program from student data
    group_code = s.get("fk_groupcode", "")
    program_id = s.get("program", "")

    db.collection("attendance").document(schedule_id).collection(today).document(student_id).set({
        "name": s.get("name", "Unknown"),
        "group": group_code,      # ✅ directly from student
        "program": program_id,    # ✅ directly from student
        "status": "Present",
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    print(f"[INFO] Marked {s.get('name', 'Unknown')} as Present")
    return s.get("name", "Unknown")

# ===== Camera Loop =====
def camera_loop():
    global latest_frame, camera_running
    cam = cv2.VideoCapture(0)
    while camera_running:
        ret, frame = cam.read()
        if not ret:
            time.sleep(0.1)
            continue

        # Resize frame for faster processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        boxes = face_recognition.face_locations(rgb_small)
        encs = face_recognition.face_encodings(rgb_small, boxes)

        for enc, (top, right, bottom, left) in zip(encs, boxes):
            matches = face_recognition.compare_faces(encodings, enc)
            student_id = None
            if True in matches:
                student_id = classNames[np.argmax(matches)]
                name = mark_attendance(student_id)
            else:
                name = "Unknown"

            top, right, bottom, left = [v * 4 for v in (top, right, bottom, left)]
            color = (0, 255, 0) if student_id else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # ✅ Resize the frame before sending to browser (make video smaller)
        display_frame = cv2.resize(frame, (640, 480))

        ret, buffer = cv2.imencode(".jpg", display_frame)
        if ret:
            with frame_lock:
                latest_frame = buffer.tobytes()
        time.sleep(0.01)

    cam.release()
    cv2.destroyAllWindows()

# ===== Flask Routes =====
@app.route("/start_camera", methods=["POST"])
def start_camera():
    global camera_running, camera_thread, current_schedule
    data = request.form
    schedule_id = data.get("schedule")
    if not schedule_id:
        return "No schedule selected", 400

    # Get the group code for this schedule
    schedule_doc = db.collection("schedules").document(schedule_id).get()
    if not schedule_doc.exists:
        return "Schedule not found", 404

    group_code = schedule_doc.to_dict().get("fk_groupcode")

    # Store selected schedule
    current_schedule = {"schedule_id": schedule_id, "fk_groupcode": group_code}

    # ✅ Only load encodings for this group
    load_students(current_group=group_code)

    if not camera_running:
        camera_running = True
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()
    return "Camera started", 200



@app.route("/video_feed")
def video_feed():
    def generate_frames():
        while True:
            with frame_lock:
                f = latest_frame
            if f:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n')
            else:
                time.sleep(0.05)
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ===== Student View =====
@app.route("/")
def student_view():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Student Camera View</title>
        <style>
            body {
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: #f4f4f4;
                font-family: Arial, sans-serif;
            }
            .container {
                text-align: center;
            }
            h2 {
                margin-bottom: 20px;
            }
            img {
                border: 3px solid #333;
                border-radius: 10px;
                box-shadow: 0px 4px 15px rgba(0,0,0,0.3);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Student View - Confirm Your Presence</h2>
            <img src="/video_feed" width="640" height="480">
        </div>
    </body>
    </html>
    """



# ===== Run App =====
if __name__ == "__main__":
    load_students()
    app.run(host="0.0.0.0", port=5001, debug=True)
