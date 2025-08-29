from flask import Flask, Response
import cv2, threading, time, os, numpy as np
from datetime import datetime, timezone, timedelta
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
STUDENTS = {}  # docID -> student data
encodings = []
classNames = []

students_ref = db.collection("students")
for doc in students_ref.stream():
    data = doc.to_dict()
    student_id = doc.id
    STUDENTS[student_id] = data

    photo_filename = data.get("photo")
    if not photo_filename:
        continue
    photo_path = os.path.join("student_pics", photo_filename)
    if not os.path.exists(photo_path):
        continue

    img = cv2.imread(photo_path)
    if img is None:
        continue
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    import numpy as np

    print("rgb_img type:", type(rgb_img))
    print("rgb_img shape:", getattr(rgb_img, "shape", None))
    print("rgb_img dtype:", getattr(rgb_img, "dtype", None))

    rgb_img = np.ascontiguousarray(rgb_img)   # 🔑 force proper memory layout


    encode = face_recognition.face_encodings(rgb_img)
    if encode:
        encodings.append(encode[0])
        classNames.append(student_id)

print(f"[INFO] Loaded {len(encodings)} student face encodings.")

# ===== Attendance Tracking =====
attended_today = {}  # student_id -> date string

# ===== Camera Setup =====
camera = cv2.VideoCapture(1, cv2.CAP_DSHOW)
latest_frame = None
frame_lock = threading.Lock()

# ===== Helper: Load Attendance Times =====
def get_attendance_times():
    doc_snap = db.collection("settings").document("attendanceTimes").get()
    data = doc_snap.to_dict() or {}
    start_time_str = data.get("startTime", "08:30")
    cutoff_time_str = data.get("cutoffTime", "09:00")
    active = data.get("active", False)
    start_time = datetime.strptime(start_time_str, "%H:%M").time()
    cutoff_time = datetime.strptime(cutoff_time_str, "%H:%M").time()
    return start_time, cutoff_time, active

# ===== Camera Loop =====
def camera_loop():
    global latest_frame, attended_today
    frame_count = 0
    last_times = None  # Keep track of last start/cutoff to reset attendance

    while True:
        ok, frame = camera.read()
        if not ok:
            time.sleep(0.1)
            continue

        # Poll latest attendance times
        start_time, cutoff_time, active = get_attendance_times()
        if not active:
            time.sleep(1)
            continue

        # Reset attended_today if times changed
        current_times = (start_time, cutoff_time)
        if last_times != current_times:
            attended_today = {}
            last_times = current_times

        frame_count += 1
        recognized_faces = []

        # Run face detection every 5 frames
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

                        today_str = datetime.now().strftime("%Y-%m-%d")
                        if attended_today.get(student_id) != today_str:
                            # Determine status
                            now_time = datetime.now().time()
                            if now_time <= start_time:
                                status = "Present"
                            elif now_time <= cutoff_time:
                                status = "Late"
                            else:
                                status = "Absent"

                            attended_today[student_id] = today_str

                            student_data = STUDENTS.get(student_id, {})
                            name = f"{student_data.get('firstName','')} {student_data.get('lastName','')}".strip()
                            email = student_data.get("email","")
                            student_class = student_data.get("studentClass","")

                            # Save to Firestore with server timestamp
                            db.collection("attendance").add({
                                "student_id": student_id,
                                "name": name,
                                "email": email,
                                "class": student_class,
                                "status": status,
                                "timestamp": firestore.SERVER_TIMESTAMP
                            })

                            print(f"[INFO] {name} marked {status} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                recognized_faces.append((student_id, left, top, right, bottom))

        # Draw boxes
        for student_id, x1, y1, x2, y2 in recognized_faces:
            x1, y1, x2, y2 = [v*4 for v in (x1, y1, x2, y2)]
            if student_id:
                name = f"{STUDENTS[student_id].get('firstName','')} {STUDENTS[student_id].get('lastName','')}".strip()
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)
                cv2.putText(frame, name, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
            else:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,0,255), 2)
                cv2.putText(frame, "Unknown", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

        # Update latest frame for Flask feed
        ok, buf = cv2.imencode(".jpg", frame)
        if ok:
            with frame_lock:
                latest_frame = buf.tobytes()

        time.sleep(0.01)

    camera.release()
    cv2.destroyAllWindows()

# ===== Flask Video Feed =====
def get_latest_frame():
    with frame_lock:
        return latest_frame

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
