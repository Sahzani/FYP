from flask import Flask, render_template, Response, jsonify
import face_recognition
import cv2
import numpy as np
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# === Paths Setup ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # iAttendy folder
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
STUDENT_PICS_FOLDER = os.path.join(BASE_DIR, 'student_pics')
FIREBASE_JSON = os.path.join(BASE_DIR, 'attend-efe1b-firebase-adminsdk-fbsvc-64dd242eec.json')

# === Initialize Flask App ===
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)

# === Initialize Firebase ===
try:
    cred = credentials.Certificate(FIREBASE_JSON)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase initialized successfully")
except Exception as e:
    print("❌ Firebase initialization failed:", e)
    db = None

# === Load Known Faces ===
images = []
class_names = []

if not os.path.exists(STUDENT_PICS_FOLDER):
    raise FileNotFoundError(f"Folder '{STUDENT_PICS_FOLDER}' not found. Create it and add student images.")

for filename in os.listdir(STUDENT_PICS_FOLDER):
    filepath = os.path.join(STUDENT_PICS_FOLDER, filename)
    img = cv2.imread(filepath)
    if img is not None:
        images.append(img)
        class_names.append(os.path.splitext(filename)[0])
    else:
        print(f"⚠️ Skipped invalid image: {filename}")

if not images:
    raise ValueError("No valid student images found in 'student_pics' folder.")

print("Loaded student images:", class_names)

def encode_faces(images_list):
    encodings = []
    for img in images_list:
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_encodings = face_recognition.face_encodings(rgb_img)
        if img_encodings:
            encodings.append(img_encodings[0])
        else:
            print("⚠️ No face found in one of the images, skipping.")
    return encodings

known_encodings = encode_faces(images)
print("✅ Face encoding complete!")

# === Attendance Function ===
def mark_attendance(name):
    if db is None:
        return
    now = datetime.now()
    time_str = now.strftime('%H:%M:%S')
    date_str = now.strftime('%Y-%m-%d')

    try:
        doc_ref = db.collection('attendance').document(f"{name}_{date_str}")
        doc = doc_ref.get()
        if not doc.exists:
            doc_ref.set({
                'name': name,
                'date': date_str,
                'time': time_str
            })
            print(f"✅ Attendance marked for {name} at {time_str}")
    except Exception as e:
        print(f"❌ Failed to mark attendance for {name}: {e}")

# === Initialize Webcam ===
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    raise RuntimeError("Cannot access webcam. Make sure it's connected and not used by another app.")

# === Frame Generator ===
def generate_frames():
    frame_count = 0
    process_every_n_frames = 7
    face_data = []

    while True:
        success, frame = camera.read()
        if not success or frame is None:
            continue

        frame_count += 1

        if frame_count % process_every_n_frames == 0:
            small_frame = cv2.resize(frame, (0, 0), fx=0.3, fy=0.3)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame, model='hog')
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            face_data = []
            for encoding, loc in zip(face_encodings, face_locations):
                matches = face_recognition.compare_faces(known_encodings, encoding, tolerance=0.6)
                face_distances = face_recognition.face_distance(known_encodings, encoding)
                match_index = np.argmin(face_distances)

                name = "Unknown"
                if matches[match_index]:
                    name = class_names[match_index].upper()
                    mark_attendance(name)

                y1, x2, y2, x1 = loc
                y1, x2, y2, x1 = int(y1 / 0.3), int(x2 / 0.3), int(y2 / 0.3), int(x1 / 0.3)
                face_data.append((name, (x1, y1, x2, y2)))

        for name, (x1, y1, x2, y2) in face_data:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(frame, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
            cv2.putText(frame, name, (x1 + 6, y2 - 6),
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 1)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# === Flask Routes ===
@app.route('/')
def index():
    return render_template('T_attendance_report.html')

@app.route('/attendance_data')
def attendance_data():
    data = []
    if db is None:
        return jsonify(data)
    try:
        docs = db.collection('attendance').stream()
        for doc in docs:
            entry = doc.to_dict()
            data.append({
                'name': entry.get('name'),
                'date': entry.get('date'),
                'time': entry.get('time')
            })
    except Exception as e:
        print("❌ Error fetching attendance data:", e)
    return jsonify(data)

@app.route('/video')
def video():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# === Run Flask App ===
if __name__ == '__main__':
    try:
        print("Templates folder:", app.template_folder)
        print("Static folder:", app.static_folder)
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        camera.release()
        print("Webcam released.")
