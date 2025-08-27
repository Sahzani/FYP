from flask import Flask, Response
import cv2, os, threading, time
import numpy as np
from datetime import datetime
import face_recognition
import firebase_admin
from firebase_admin import credentials, firestore

# ===== Firebase Setup =====
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ===== Flask App =====
app = Flask(__name__)

# ===== Load Students from Firestore =====
STUDENTS = {}       # Firestore docID -> student info
encodings = []      # face encodings
classNames = []     # corresponding Firestore IDs

students_ref = db.collection("students")
docs = students_ref.stream()

print("[INFO] Loading students from Firestore...")

for doc in docs:
    data = doc.to_dict()
    student_id = doc.id
    STUDENTS[student_id] = data

    photo_filename = data.get("photo")
    if not photo_filename:
        print(f"[WARN] Student {student_id} has no photo, skipping")
        continue

    photo_path = os.path.join("student_pics", photo_filename)
    if not os.path.exists(photo_path):
        print(f"[WARN] Photo {photo_filename} not found locally, skipping")
        continue

    img = cv2.imread(photo_path)
    if img is None:
        print(f"[WARN] Cannot read {photo_filename}, skipping")
        continue

    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    encode = face_recognition.face_encodings(rgb_img)
    if encode:
        encodings.append(encode[0])
        classNames.append(student_id)
        print(f"[OK] Loaded encoding for {student_id} ({photo_filename})")
    else:
        print(f"[WARN] No face found in {photo_filename}")

print(f"[INFO] Total students with encodings: {len(encodings)}")

# ===== Attendance Tracking =====
attended_students = {}  # Firestore ID -> status written

# ===== Camera Thread =====
camera = cv2.VideoCapture(1, cv2.CAP_DSHOW)
latest_frame = None
frame_lock = threading.Lock()

def camera_loop():
    global latest_frame
    frame_count = 0
    while True:
        ok, frame = camera.read()
        if not ok:
            time.sleep(0.1)
            continue

        # Fetch class times
        settings_doc = db.collection("settings").document("attendanceTimes").get()
        settings = settings_doc.to_dict() or {}
        if not settings.get("active", False):
            time.sleep(1)
            continue

        start_time_str = settings.get("startTime", "08:30")
        cutoff_time_str = settings.get("cutoffTime", "09:00")
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        cutoff_time = datetime.strptime(cutoff_time_str, "%H:%M").time()

        frame_count += 1
        recognized_faces = []

        if frame_count % 5 == 0:
            small = cv2.resize(frame, (0,0), fx=0.25, fy=0.25)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            boxes = face_recognition.face_locations(rgb_small, model="hog")
            face_encs = face_recognition.face_encodings(rgb_small, boxes)

            for enc, (top, right, bottom, left) in zip(face_encs, boxes):
                student_id = None
                if encodings:
                    matches = face_recognition.compare_faces(encodings, enc, tolerance=0.6)
                    if True in matches:
                        best_idx = np.argmax(matches)
                        student_id = classNames[best_idx]

                        if student_id not in attended_students:
                            # Determine Present / Late / Absent
                            now_time = datetime.now().time()
                            if now_time <= start_time:
                                status = "Present"
                            elif now_time <= cutoff_time:
                                status = "Late"
                            else:
                                status = "Absent"

                            attended_students[student_id] = status

                            student_data = STUDENTS.get(student_id, {})
                            name = f"{student_data.get('firstName','')} {student_data.get('lastName','')}".strip()
                            email = student_data.get("email","")
                            student_class = student_data.get("studentClass","")

                            # Save to Firestore
                            db.collection("attendance").add({
                                "student_id": student_id,
                                "name": name,
                                "email": email,
                                "class": student_class,
                                "status": status,
                                "time": firestore.SERVER_TIMESTAMP
                            })

                            print(f"[INFO] {name} detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} as {status}")

                recognized_faces.append((student_id, left, top, right, bottom))

        # Draw rectangles and labels
        for student_id, x1, y1, x2, y2 in recognized_faces:
            x1, y1, x2, y2 = [v*4 for v in (x1, y1, x2, y2)]
            if student_id:
                name = f"{STUDENTS[student_id].get('firstName','')} {STUDENTS[student_id].get('lastName','')}".strip()
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)
                cv2.putText(frame, name, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
            else:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,0,255), 2)
                cv2.putText(frame, "Unknown", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

        ok, buf = cv2.imencode(".jpg", frame)
        if ok:
            with frame_lock:
                latest_frame = buf.tobytes()
        time.sleep(0.01)

def get_latest_frame():
    with frame_lock:
        return latest_frame

# ===== Flask Routes =====
@app.route('/video_feed')
def video_feed():
    def gen_frames():
        while True:
            frame = get_latest_frame()
            if frame:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+frame+b'\r\n')
            else:
                time.sleep(0.05)
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ===== Run Flask =====
if __name__ == "__main__":
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5001, debug=False)
    camera.release()
