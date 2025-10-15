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
from flask_cors import CORS

# ===== Firebase Setup (only once) =====
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ===== Flask Setup =====
app = Flask(__name__)
CORS(app)

# ===== Global Variables =====
STUDENTS = {}
encodings = []
classNames = []
latest_frame = None
frame_lock = threading.Lock()
camera_thread = None
camera_running = False
current_schedule = None
API_URL = "https://iattend.duckdns.org"

# Skip frames to reduce CPU usage (process 1 out of every 5 frames)
FRAME_SKIP = 5
frame_count = 0

# ===== Wait for main API =====
def wait_for_api(url, timeout=30):
    for _ in range(timeout):
        try:
            r = requests.get(url)
            if r.status_code == 200:
                print("[INFO] Main API is ready!")
                return True
        except:
            pass
        time.sleep(1)
    print("[ERROR] Could not reach main API.")
    return False

# ===== Load students ONLY when camera starts =====
def load_students_for_schedule(schedule_id):
    global STUDENTS, encodings, classNames
    print(f"[INFO] Loading students for schedule: {schedule_id}")
    
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
            
            photo_url = student.get("photo_url", "")
            if not photo_url or not photo_url.startswith("/student_pics/"):
                continue
                
            photo_path = os.path.join("static", "student_pics", photo_url.replace("/student_pics/", "", 1))
            if not os.path.exists(photo_path):
                continue

            img = cv2.imread(photo_path)
            if img is None:
                continue

            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face_enc = face_recognition.face_encodings(rgb_img)
            if face_enc:
                encodings.append(face_enc[0])
                classNames.append(student_id)

        print(f"[INFO] Loaded {len(encodings)} student encodings")
        return True
        
    except Exception as e:
        print(f"[ERROR] Load failed: {e}")
        return False

# ===== Mark attendance (same as before) =====
attended_today = {}

def mark_attendance(student_id):
    global current_schedule
    today = datetime.now().strftime("%Y-%m-%d")
    if not current_schedule:
        return None

    schedule_id = current_schedule["schedule_id"]
    key = (student_id, schedule_id, today)
    if attended_today.get(key):
        return None  # already marked

    attended_today[key] = True
    s = STUDENTS.get(student_id, {})
    group_code = s.get("group", "")
    program_id = s.get("program", "")

    now = datetime.now()
    class_start = datetime.strptime("08:00", "%H:%M")  # <-- replace with schedule start time
    status = "Present" if now <= class_start else "Late"

    db.collection("attendance").document(schedule_id).collection(today).document(student_id).set({
        "name": s.get("name", "Unknown"),
        "group": group_code,
        "program": program_id,
        "status": status,
        "timestamp": firestore.SERVER_TIMESTAMP
    }, merge=True)

    print(f"[INFO] Marked {s.get('name', 'Unknown')} as {status}")
    return s.get("name", "Unknown")


# ===== Camera Loop (Optimized) =====
def camera_loop():
    global latest_frame, camera_running, frame_count
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("[ERROR] Cannot open camera")
        camera_running = False
        return

    while camera_running:
        ret, frame = cam.read()
        if not ret:
            time.sleep(0.1)
            continue

        frame_count += 1
        # Only process 1 out of every FRAME_SKIP frames
        if frame_count % FRAME_SKIP != 0:
            # Still show live video, but skip face recognition
            display_frame = cv2.resize(frame, (640, 480))
            ret, buffer = cv2.imencode(".jpg", display_frame)
            if ret:
                with frame_lock:
                    latest_frame = buffer.tobytes()
            time.sleep(0.03)
            continue

        # Resize for faster processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        boxes = face_recognition.face_locations(rgb_small, model="hog")  # faster than "cnn"
        encs = face_recognition.face_encodings(rgb_small, boxes)

        for enc, (top, right, bottom, left) in zip(encs, boxes):
            if not encodings:
                name = "No Students Loaded"
                student_id = None
            else:
                face_distances = face_recognition.face_distance(encodings, enc)
                best_match_index = np.argmin(face_distances)
                best_distance = face_distances[best_match_index]

                if best_distance < 0.45:
                    student_id = classNames[best_match_index]
                    name = mark_attendance(student_id)
                else:
                    student_id = None
                    name = "Unknown"

            # Draw box on original frame
            top, right, bottom, left = [v * 4 for v in (top, right, bottom, left)]
            color = (0, 255, 0) if student_id else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            label = f"{name} ({best_distance:.2f})" if student_id else name
            cv2.putText(frame, label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        display_frame = cv2.resize(frame, (640, 480))
        ret, buffer = cv2.imencode(".jpg", display_frame)
        if ret:
            with frame_lock:
                latest_frame = buffer.tobytes()

        time.sleep(0.03)  # ~30 FPS max

    cam.release()
    print("[INFO] Camera stopped")

# ===== Routes =====
@app.route("/start_camera", methods=["POST"])
def start_camera():
    global camera_running, current_schedule
    if camera_running:
        return "Camera already running", 200

    schedule_id = request.form.get("schedule")
    if not schedule_id:
        return "No schedule selected", 400

    current_schedule = {"schedule_id": schedule_id}
    if not load_students_for_schedule(schedule_id):
        return "Failed to load students", 500

    camera_running = True
    threading.Thread(target=camera_loop, daemon=True).start()
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
                time.sleep(0.1)
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/")
def student_view():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Student View</title></head>
    <body style="text-align:center; margin-top:50px;">
        <h2>Student Camera View</h2>
        <img src="/video_feed" width="640" height="480">
        <p><button onclick="fetch('/stop_camera')">Stop Camera</button></p>
    </body>
    </html>
    """

CERT_PATH = "/etc/letsencrypt/live/iattend.duckdns.org/fullchain.pem"
KEY_PATH = "/etc/letsencrypt/live/iattend.duckdns.org/privkey.pem"

if __name__ == "__main__":
    if wait_for_api(API_URL):
        app.run(
            host="0.0.0.0", 
            port=5001, 
            debug=False, 
            threaded=True,
            ssl_context=(CERT_PATH, KEY_PATH)  # <-- The new SSL part
        )
    else:
        print("Exiting: main app not available")