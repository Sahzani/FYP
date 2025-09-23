import os
import cv2
import threading
import time
import numpy as np
from datetime import datetime
from firebase import db
from firebase_admin import firestore
import face_recognition
import time
import cv2

camera = None

# ===== Load Students =====
STUDENTS = {}          # student_id -> student data
encodings, classNames = [], []

print("[INFO] Loading student images and encodings...")

students_ref = db.collection("users").where("role_type", "==", 1).stream()
for doc in students_ref:
    data = doc.to_dict()
    student_id = doc.id
    STUDENTS[student_id] = data

    photo_filename = data.get("photo_name")
    if photo_filename:
        photo_path = os.path.join("student_pics", photo_filename)
    else:
        name_safe = data.get("name", "").replace(" ", "_")
        photo_path = os.path.join("student_pics", f"{name_safe}.jpg")

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

print(f"[INFO] Finished loading students. Total encodings loaded: {len(encodings)}")

# ===== Attendance Tracking =====
attended_today = set()  # (student_id, date)

# ===== Camera Setup =====
camera = None
latest_frame = None
frame_lock = threading.Lock()
camera_thread = None
camera_running = False

# ===== Current schedule =====
current_schedule = {"group": None, "module": None}

def set_schedule(group, module):
    global current_schedule
    current_schedule["group"] = group
    current_schedule["module"] = module

# ===== Mark attendance =====
def mark_attendance(student_id):
    today_str = datetime.now().strftime("%Y-%m-%d")
    student_data = STUDENTS.get(student_id, {})
    name = student_data.get("name", "")

    # Only mark if belongs to current schedule
    if student_data.get("fk_groupcode") != current_schedule["group"] or \
       student_data.get("module_name") != current_schedule["module"]:
        return None

    key = (student_id, today_str)
    if key in attended_today:
        return name

    group_ref = db.collection("attendance").document(today_str)\
                  .collection("Students").document(current_schedule["group"])
    group_doc = group_ref.get()
    module_data = group_doc.to_dict() if group_doc.exists else {}

    if current_schedule["module"] not in module_data:
        module_data[current_schedule["module"]] = {}

    module_data[current_schedule["module"]][student_id] = {
        "name": name,
        "status": "Present",
        "timestamp": firestore.SERVER_TIMESTAMP
    }

    group_ref.set(module_data, merge=True)
    attended_today.add(key)
    print(f"[INFO] Marked {name} ({student_id}) as Present")
    return name

# ===== Camera Loop =====
def camera_loop():
    global latest_frame, camera_running, camera
    camera = cv2.VideoCapture(0)

    while camera_running:
        ret, frame = camera.read()
        if not ret:
            time.sleep(0.1)
            continue

        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
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

            top, right, bottom, left = [v*4 for v in (top, right, bottom, left)]
            color = (0, 255, 0) if student_id else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(frame, name, (left, top-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        ret, buffer = cv2.imencode(".jpg", frame)
        if ret:
            with frame_lock:
                latest_frame = buffer.tobytes()
        time.sleep(0.01)

    camera.release()
    cv2.destroyAllWindows()

# ===== Camera Controls =====
def start_camera():
    global camera_thread, camera_running
    if not camera_running:
        camera_running = True
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()

def stop_camera():
    global camera_running
    camera_running = False

def get_latest_frame():
    with frame_lock:
        return latest_frame

def get_schedule():
    return current_schedule
