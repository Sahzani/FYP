import os
import cv2
import threading
import time
import numpy as np
from datetime import datetime
from flask import Flask, Response, render_template, redirect, url_for
import face_recognition
import firebase_admin
from firebase_admin import credentials, firestore

# ===== Firebase Setup =====
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ===== Flask App =====
app = Flask(__name__)
# ===== Load Students =====
STUDENTS = {}          # student_id -> student data
encodings, classNames = [], []

print("[INFO] Loading student images and encodings...")

students_ref = db.collection("users").where("role_type", "==", 1).stream()
for doc in students_ref:
    data = doc.to_dict()
    student_id = doc.id
    STUDENTS[student_id] = data

    # Try Firestore photo_name first
    photo_filename = data.get("photo_name")
    if photo_filename:
        photo_path = os.path.join("student_pics", photo_filename)
    else:
        # Fallback: use student's name as filename
        name_safe = data.get("name", "").replace(" ", "_")
        photo_path = os.path.join("student_pics", f"{name_safe}.jpg")
        print(f"[WARN] Student {student_id} ({data.get('name')}) has no photo_name field. Trying {photo_path}")

    if not os.path.exists(photo_path):
        print(f"[WARN] File not found: {photo_path}")
        continue

    img = cv2.imread(photo_path)
    if img is None:
        print(f"[WARN] Unable to read image: {photo_path}")
        continue

    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_enc = face_recognition.face_encodings(rgb_img)
    if face_enc:
        encodings.append(face_enc[0])
        classNames.append(student_id)
        print(f"[INFO] Loaded encoding for {data.get('name')} ({student_id})")

print(f"[INFO] Finished loading students. Total encodings loaded: {len(encodings)}")


# ===== Attendance Tracking =====
attended_today = {}  # (student_id, date) -> True

# ===== Camera Setup =====
camera = None
latest_frame = None
frame_lock = threading.Lock()
camera_thread = None
camera_running = False

# ===== Helper: Mark Attendance =====
def mark_attendance(student_id):
    today_str = datetime.now().strftime("%Y-%m-%d")
    key = (student_id, today_str)

    if attended_today.get(key):
        return None  # Already marked

    attended_today[key] = True

    student_data = STUDENTS.get(student_id, {})
    name = student_data.get("name", "")
    group = student_data.get("fk_groupcode", "")
    program = student_data.get("program", "")

    db.collection("attendance").document(today_str).collection("students").document(student_id).set({
        "name": name,
        "group": group,
        "program": program,
        "status": "Present",
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    print(f"[INFO] Marked {name} ({student_id}) as Present.")
    return name

# ===== Camera Loop =====

def camera_loop():
    global latest_frame, camera_running, camera
    camera = cv2.VideoCapture(0)  # Change 0 to your camera index if needed

    while camera_running:
        ret, frame = camera.read()
        if not ret:
            time.sleep(0.1)
            continue

        small_frame = cv2.resize(frame, (0,0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        boxes = face_recognition.face_locations(rgb_small, model="hog")
        face_encs = face_recognition.face_encodings(rgb_small, boxes)

        for enc, (top, right, bottom, left) in zip(face_encs, boxes):
            matches = face_recognition.compare_faces(encodings, enc, tolerance=0.6)
            student_id = None
            if True in matches:
                best_idx = np.argmax(matches)
                student_id = classNames[best_idx]
                name = mark_attendance(student_id)
            else:
                name = "Unknown"

            # Draw box and label
            top, right, bottom, left = [v*4 for v in (top, right, bottom, left)]
            color = (0, 255, 0) if student_id else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(frame, name, (left, top-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Encode frame
        ret, buffer = cv2.imencode(".jpg", frame)
        if ret:
            with frame_lock:
                latest_frame = buffer.tobytes()

        time.sleep(0.01)

    camera.release()
    cv2.destroyAllWindows()
    

# ===== Flask Routes =====
@app.route("/")
def index():
    return render_template("index.html")  # This should include <img src="/video_feed">

@app.route("/start_camera")
def start_camera():
    global camera_thread, camera_running
    if not camera_running:
        camera_running = True
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()
    return redirect(url_for("index"))

@app.route("/stop_camera")
def stop_camera():
    global camera_running
    camera_running = False
    return redirect(url_for("index"))

@app.route("/video_feed")
def video_feed():
    def generate_frames():
        while True:
            with frame_lock:
                frame = latest_frame
            if frame:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.05)
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

# ===== Run App =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

