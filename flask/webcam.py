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
from datetime import datetime, timedelta

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
camera_running = False
current_schedule = None
API_URL = "http://127.0.0.1:8000"
attended_today = {}  # Track attendance to avoid duplicates

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

# ===== Load students ONLY when camera starts (for real attendance) =====
def load_students_for_schedule(schedule_id):
    global STUDENTS, encodings, classNames, current_schedule
    print(f"[INFO] Loading students for schedule: {schedule_id}")
    
    try:
        # === 1. Fetch schedule to get group_id ===
        schedule_ref = db.collection("schedules").document(schedule_id)
        schedule_doc = schedule_ref.get()
        if not schedule_doc.exists:
            print("[ERROR] Schedule not found")
            return False

        schedule_data = schedule_doc.to_dict()
        group_id = schedule_data.get("fk_group")  # This is the Firestore group doc ID!
        start_time = schedule_data.get("start_time")
        end_time = schedule_data.get("end_time")

        if not group_id or not start_time or not end_time:
            print("[ERROR] Missing schedule fields")
            return False

        current_schedule = {
            "schedule_id": schedule_id,
            "start_time": start_time,
            "end_time": end_time,
            "group_id": group_id  # ← store group_id (doc ID)
        }

        # === 2. Fetch students from main API ===
        response = requests.get(f"{API_URL}/api/attendance/{schedule_id}")
        if response.status_code != 200:
            print("[ERROR] Failed to fetch students from main API")
            return False

        data = response.json()
        students_list = data.get("students", [])
        
        STUDENTS = {}
        encodings = []
        classNames = []
        
        for student in students_list:
            student_id = student["id"]
            
            # Get student's program (if needed)
            program_id = student.get("program", "")
            
            # IMPORTANT: Use group_id from schedule (not student's group field)
            # Because all students in this schedule belong to the same group
            STUDENTS[student_id] = {
                "name": student.get("name", "Unknown"),
                "group": group_id,        # ← Firestore group doc ID (matches teacher system)
                "program": program_id
            }
            
            # ... [rest of photo loading code unchanged] ...

        print(f"[INFO] Loaded {len(encodings)} encodings for group {group_id}")
        return True

    except Exception as e:
        print(f"[ERROR] Load failed: {e}")
        return False
# ===== Mark attendance (only used in real mode) =====
def mark_attendance(student_id):
    global current_schedule
    if not current_schedule:
        return None

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.time()

    schedule_id = current_schedule["schedule_id"]
    start_time_str = current_schedule["start_time"]
    end_time_str = current_schedule["end_time"]

    try:
        session_start = datetime.strptime(start_time_str, "%H:%M").time()
        session_end = datetime.strptime(end_time_str, "%H:%M").time()
    except:
        return None

    # Skip if outside session
    if not (session_start <= current_time <= session_end):
        return None

    # Determine status
    start_dt = datetime.combine(datetime.today(), session_start)
    cutoff_dt = start_dt + timedelta(minutes=30)
    status = "Present" if current_time <= cutoff_dt.time() else "Late"

    # Avoid duplicates
    key = (student_id, schedule_id, today)
    if attended_today.get(key):
        return None
    attended_today[key] = True

    # Get student data
    s = STUDENTS.get(student_id, {})
    student_name = s.get("name", "Unknown")
    group_id = s.get("group", "")      # ← now it's the Firestore doc ID
    program_id = s.get("program", "")

    # Get program name (optional, but matches teacher system)
    program_name = "Unknown Program"
    if program_id:
        prog_doc = db.collection("programs").document(program_id).get()
        if prog_doc.exists:
            program_name = prog_doc.to_dict().get("programName", "Unknown Program")

    # === Store EXACTLY like teacher system ===
    attendance_data = {
        "student_name": student_name,
        "group": group_id,           # ← Firestore group doc ID
        "program": program_name,
        "status": status,
        "timestamp": firestore.SERVER_TIMESTAMP
    }

    db.collection("attendance").document(schedule_id).collection(today).document(student_id).set(
        attendance_data, merge=True
    )

    print(f"[INFO] Marked {student_name} as {status}")
    return student_name
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
        # Only process 1 out of every FRAME_SKIP frames for recognition
        if frame_count % FRAME_SKIP != 0:
            # Still show live video
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
        boxes = face_recognition.face_locations(rgb_small, model="hog")
        encs = face_recognition.face_encodings(rgb_small, boxes)

        for enc, (top, right, bottom, left) in zip(encs, boxes):
            # If no students loaded (preview mode), treat all as Unknown
            if not encodings:
                name = "Unknown"
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
    """Used by main app for real attendance (with schedule)"""
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
    return "Camera started with schedule", 200


@app.route("/start_camera_preview", methods=["POST"])
def start_camera_preview():
    """Start camera in preview mode: detect faces but mark all as Unknown, no attendance"""
    global camera_running, current_schedule, encodings, classNames, STUDENTS
    if camera_running:
        return "Camera already running", 200

    # Clear all student data → forces "Unknown" for all faces
    current_schedule = None
    STUDENTS = {}
    encodings = []
    classNames = []

    camera_running = True
    threading.Thread(target=camera_loop, daemon=True).start()
    return "Camera started in preview mode", 200


@app.route("/stop_camera")
def stop_camera():
    global camera_running, current_schedule
    camera_running = False
    current_schedule = None
    time.sleep(0.2)  # Allow thread to exit
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
    <head>
        <title>Camera Preview</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                text-align: center; 
                margin-top: 30px; 
                background: #f5f5f5;
            }
            .btn {
                padding: 12px 24px;
                font-size: 18px;
                margin: 10px;
                cursor: pointer;
                border: none;
                border-radius: 5px;
                background: #4CAF50;
                color: white;
            }
            .btn.stop {
                background: #f44336;
            }
            .btn:disabled {
                background: #cccccc;
                cursor: not-allowed;
            }
            #status {
                margin: 15px 0;
                font-weight: bold;
                color: #555;
            }
            #videoFeed {
                border: 2px solid #ddd;
                background: #000;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <h2>Camera Preview Mode</h2>
        <p>All faces appear as <strong>"Unknown"</strong> — no attendance recorded.</p>

        <div id="status">Camera stopped</div>

        <button class="btn" onclick="startCamera()">Start Camera (Preview)</button>
        <button class="btn stop" onclick="stopCamera()" id="stopBtn" disabled>Stop Camera</button>

        <div>
            <img src="/video_feed" id="videoFeed" width="640" height="480">
        </div>

        <script>
            const statusEl = document.getElementById('status');
            const stopBtn = document.getElementById('stopBtn');

            async function startCamera() {
                statusEl.textContent = "Starting camera...";
                statusEl.style.color = "#555";

                try {
                    const res = await fetch('/start_camera_preview', {
                        method: 'POST'
                    });

                    if (res.ok) {
                        statusEl.textContent = "Camera running (preview mode)";
                        statusEl.style.color = "green";
                        stopBtn.disabled = false;
                    } else {
                        const msg = await res.text();
                        statusEl.textContent = "Error: " + msg;
                        statusEl.style.color = "red";
                    }
                } catch (err) {
                    statusEl.textContent = "Failed to connect to server";
                    statusEl.style.color = "red";
                }
            }

            async function stopCamera() {
                try {
                    await fetch('/stop_camera');
                    statusEl.textContent = "Camera stopped";
                    statusEl.style.color = "#555";
                    stopBtn.disabled = true;
                } catch (err) {
                    statusEl.textContent = "Stop failed";
                    statusEl.style.color = "red";
                }
            }
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    if wait_for_api(API_URL):
        app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
    else:
        print("Exiting: main app not available")