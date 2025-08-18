from flask import Flask, render_template, Response, jsonify
import cv2, os, json, threading, time
import numpy as np
from datetime import datetime, time as dt_time
import face_recognition
import firebase_admin
from firebase_admin import credentials, db

# ========== Firebase Admin Setup ==========
cred = credentials.Certificate("serviceAccountKey.json")  # download from Firebase Console
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://aimanzamani-default-rtdb.asia-southeast1.firebasedatabase.app"
})

# ========== Flask ==========
app = Flask(__name__)

# ========== Load Faces ==========
PATH = 'student_pics'
images, classNames = [], []

if not os.path.isdir(PATH):
    os.makedirs(PATH, exist_ok=True)

for cl in os.listdir(PATH):
    img_path = os.path.join(PATH, cl)
    if os.path.isfile(img_path):
        img = cv2.imread(img_path)
        if img is not None:
            images.append(img)
            classNames.append(os.path.splitext(cl)[0])

def findEncodings(imgs):
    encs = []
    for im in imgs:
        rgb = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        face_encs = face_recognition.face_encodings(rgb)
        if face_encs:
            encs.append(face_encs[0])
    return encs

encodeListKnown = findEncodings(images)
print(f"[INFO] Loaded {len(encodeListKnown)} encodings.")

# ========== Load Students ==========
def fetch_students():
    students_snap = db.reference("users").get() or {}
    return students_snap

STUDENTS = fetch_students()

# ========== Attendance ==========
_last_seen_push = {}
COOLDOWN_SECONDS = 30

# Teacher can set class start/end times and late threshold
CLASS_START = dt_time(8, 0)   # 08:00 AM
CLASS_END = dt_time(9, 0)     # 09:00 AM
LATE_AFTER = dt_time(8, 15)   # 08:15 AM = late

def mark_attendance(uid: str, name: str, email: str, late=False):
    date = datetime.now().strftime('%Y-%m-%d')
    now_iso = datetime.now().isoformat(timespec='seconds')

    node = db.reference(f"attendance/{date}/{uid}")
    existing = node.get()

    record = {
        "uid": uid,
        "name": name,
        "email": email,
        "first_seen": now_iso if existing is None else existing.get("first_seen"),
        "last_seen": now_iso,
        "count": 1 if existing is None else int(existing.get("count", 1)) + 1,
        "late": late
    }

    if existing is None:
        node.set(record)
    else:
        node.update(record)

def _should_push(uid: str) -> bool:
    now = time.time()
    last = _last_seen_push.get(uid, 0)
    if now - last >= COOLDOWN_SECONDS:
        _last_seen_push[uid] = now
        return True
    return False

def is_within_class_window():
    now = datetime.now().time()
    return CLASS_START <= now <= CLASS_END

def is_late():
    now = datetime.now().time()
    return now > LATE_AFTER

# ========== Camera Thread ==========
camera = cv2.VideoCapture(0)
latest_frame = None
frame_lock = threading.Lock()

def camera_loop():
    global latest_frame
    frame_count = 0
    while True:
        ok, frame = camera.read()
        if not ok:
            time.sleep(0.05)
            continue

        frame_count += 1
        recognized_faces = []

        if frame_count % 7 == 0 and len(encodeListKnown) > 0:
            small = cv2.resize(frame, (0,0), fx=0.3, fy=0.3)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            boxes = face_recognition.face_locations(rgb_small, model="hog")
            encs  = face_recognition.face_encodings(rgb_small, boxes)

            for enc, (top, right, bottom, left) in zip(encs, boxes):
                matches = face_recognition.compare_faces(encodeListKnown, enc, tolerance=0.6)
                dists = face_recognition.face_distance(encodeListKnown, enc)

                name = "Unknown"
                if len(dists) > 0:
                    best = np.argmin(dists)
                    if matches[best]:
                        key = classNames[best]
                        info = STUDENTS.get(key.lower()) or STUDENTS.get(key)
                        if info:
                            uid = info["uid"]
                            email = info.get("email", "")
                            name = info.get("name", key)

                            # Only mark attendance if class is active
                            if is_within_class_window() and _should_push(uid):
                                mark_attendance(uid, name, email, late=is_late())

                # scale back up
                top, right, bottom, left = int(top/0.3), int(right/0.3), int(bottom/0.3), int(left/0.3)
                recognized_faces.append((name, left, top, right, bottom))

        # Draw names
        for (name, x1, y1, x2, y2) in recognized_faces:
            cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
            cv2.rectangle(frame, (x1, y2-35), (x2, y2), (0,255,0), cv2.FILLED)
            cv2.putText(frame, name, (x1+6, y2-6), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255,255,255), 1)

        ok, buf = cv2.imencode(".jpg", frame)
        if ok:
            with frame_lock:
                latest_frame = buf.tobytes()

        time.sleep(0.01)

def get_latest_frame():
    with frame_lock:
        return latest_frame

# ========== Flask Routes ==========
@app.route('/')
def index():
    return render_template('T_attendance_report.html')

@app.route('/video')
def video():
    def gen_frames():
        while True:
            frame = get_latest_frame()
            if frame:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.05)
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/attendance_data')
def attendance_data():
    today = datetime.now().strftime('%Y-%m-%d')
    snap = db.reference(f"attendance/{today}").get() or {}
    rows = []
    for uid, rec in snap.items():
        rows.append({
            "uid": uid,
            "name": rec.get("name"),
            "email": rec.get("email"),
            "first_seen": rec.get("first_seen"),
            "last_seen": rec.get("last_seen"),
            "count": rec.get("count", 1),
            "late": rec.get("late", False)
        })
    return jsonify(rows)

# ========== Run ==========
if __name__ == '__main__':
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        camera.release()
