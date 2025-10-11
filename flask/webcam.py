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
API_URL = "http://128.199.107.48:8000"


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

# ===== Load Students and Encodings for Specific Schedule =====
def load_students_for_schedule(schedule_id):
    global STUDENTS, encodings, classNames
    print(f"[INFO] Fetching students for schedule: {schedule_id}")
    
    try:
        response = requests.get(f"{API_URL}/api/attendance/{schedule_id}")
        if response.status_code != 200:
            print("[ERROR] Failed to fetch schedule data")
            return False
            
        data = response.json()
        students_list = data.get("students", [])
        
        STUDENTS = {}
        encodings = []
        classNames = []
        
        for student in students_list:
            student_id = student["id"]
            STUDENTS[student_id] = student
            
            # Extract photo path from photo_url (remove leading /student_pics/)
            photo_url = student.get("photo_url", "")
            if not photo_url or not photo_url.startswith("/student_pics/"):
                print(f"[WARN] No valid photo for student {student_id}")
                continue
                
            photo_filename = photo_url.replace("/student_pics/", "", 1)
            
            # Build correct path including 'static' folder
            photo_path = os.path.join("static", "student_pics", *photo_filename.split('/'))
            
            if not os.path.exists(photo_path):
                print(f"[WARN] File not found: {photo_path}")
                continue

            img = cv2.imread(photo_path)
            if img is None:
                print(f"[WARN] Could not read image: {photo_path}")
                continue

            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face_enc = face_recognition.face_encodings(rgb_img)
            if face_enc:
                encodings.append(face_enc[0])
                classNames.append(student_id)
                print(f"[INFO] Loaded encoding for {student.get('name')} ({student_id})")

        print(f"[INFO] Total encodings loaded: {len(encodings)}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to load students: {e}")
        return False

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
    group_code = s.get("group", "")
    program_id = s.get("program", "")

    db.collection("attendance").document(schedule_id).collection(today).document(student_id).set({
        "name": s.get("name", "Unknown"),
        "group": group_code,
        "program": program_id,
        "status": "Present",
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    print(f"[INFO] Marked {s.get('name', 'Unknown')} as Present")
    return s.get("name", "Unknown")

# ===== Camera Loop =====
def camera_loop():
    global latest_frame, camera_running
    cam = cv2.VideoCapture(2)
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

        # Resize the frame before sending to browser
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

    # Store selected schedule
    current_schedule = {"schedule_id": schedule_id}
    
    # Load ONLY students for this specific schedule
    if not load_students_for_schedule(schedule_id):
        return "Failed to load student data", 500

    if not camera_running:
        camera_running = True
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()
    return "Camera started", 200

@app.route("/stop_camera")
def stop_camera():
    global camera_running
    camera_running = False
    return "Camera stopped", 200

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
    # Don't load students at startup - load per schedule instead
    app.run(host="0.0.0.0", port=5001, debug=True)