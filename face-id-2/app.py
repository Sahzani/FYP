from flask import Flask, render_template, Response, request, jsonify
import face_recognition
import cv2
import numpy as np
import os
from datetime import datetime
import base64

import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# Initialize Firebase Admin SDK
cred = credentials.Certificate('attendence-e0c7a-firebase-adminsdk-fbsvc-8cd402c855.json')  # <-- Change this path
firebase_admin.initialize_app(cred)
db = firestore.client()

# Load known face images
path = 'Pic'
images = []
classNames = []
myList = os.listdir(path)
print("Images found:", myList)

for cl in myList:
    curImg = cv2.imread(f'{path}/{cl}')
    if curImg is not None:
        images.append(curImg)
        classNames.append(os.path.splitext(cl)[0])

print("Class Names:", classNames)

# Encode known faces
def findEncodings(images):
    encodeList = []
    for img in images:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(img)
        if encodings:
            encodeList.append(encodings[0])
    return encodeList

encodeListKnown = findEncodings(images)
print('Encoding Complete')

# Attendance logging to Firestore
def markAttendance(name):
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

    attendance_ref = db.collection('attendance')
    # Query if today's attendance for this name already exists
    query = attendance_ref.where('name', '==', name).where('date', '==', date_str).stream()

    if not any(query):
        attendance_ref.add({
            'name': name,
            'timestamp': timestamp_str,
            'date': date_str
        })
        print(f'Attendance marked for {name} at {timestamp_str}')
    else:
        print(f'Attendance for {name} already marked today.')

# Video feed generator (for laptop webcam)
def gen_frames():
    cap = cv2.VideoCapture(0)

    while True:
        success, img = cap.read()
        if not success:
            break

        imgS = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
        imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

        facesCurFrame = face_recognition.face_locations(imgS)
        encodesCurFrame = face_recognition.face_encodings(imgS, facesCurFrame)

        for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):
            matches = face_recognition.compare_faces(encodeListKnown, encodeFace)
            faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)

            matchIndex = np.argmin(faceDis)
            name = "Unknown"

            if matches[matchIndex]:
                name = classNames[matchIndex].upper()
                markAttendance(name)

            y1, x2, y2, x1 = faceLoc
            y1, x2, y2, x1 = y1*4, x2*4, y2*4, x1*4

            # Draw green box and label
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(img, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
            cv2.putText(img, name, (x1 + 6, y2 - 6),
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 1)

        ret, buffer = cv2.imencode('.jpg', img)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video')
def video():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/attendance_data')
def attendance_data():
    data = []
    attendance_ref = db.collection('attendance')
    docs = attendance_ref.stream()

    for doc in docs:
        record = doc.to_dict()
        data.append({
            'name': record.get('name'),
            'time': record.get('timestamp')
        })
    return jsonify(data)

# API for mobile face recognition (accept base64 image)
@app.route('/recognize', methods=['POST'])
def recognize():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'error': 'No image provided'}), 400

    img_data = data['image'].split(',')[1]  # Remove base64 header
    nparr = np.frombuffer(base64.b64decode(img_data), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    imgS = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
    imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

    facesCurFrame = face_recognition.face_locations(imgS)
    encodesCurFrame = face_recognition.face_encodings(imgS, facesCurFrame)

    for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):
        matches = face_recognition.compare_faces(encodeListKnown, encodeFace)
        faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)
        matchIndex = np.argmin(faceDis)

        if matches[matchIndex]:
            name = classNames[matchIndex].upper()
            time_now = datetime.now().strftime('%H:%M:%S')
            markAttendance(name)
            return jsonify({'name': name, 'time': time_now})

    return jsonify({'name': None})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
