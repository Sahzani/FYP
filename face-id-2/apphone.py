from flask import Flask, render_template, Response, jsonify
import face_recognition
import cv2
import numpy as np
import os
from datetime import datetime
import threading

app = Flask(__name__)

# === Load known face images from 'Pic' folder ===
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

def markAttendance(name):
    if not os.path.exists('Attendance.csv'):
        with open('Attendance.csv', 'w') as f:
            f.write("Name,Time\n")

    with open('Attendance.csv', 'r+') as f:
        myDataList = f.readlines()
        nameList = [line.split(',')[0] for line in myDataList[1:]]
        if name not in nameList:
            now = datetime.now()
            dt_string = now.strftime('%H:%M:%S')
            f.writelines(f'{name},{dt_string}\n')

# Threaded video capture class
class VideoCaptureAsync:
    def __init__(self, src=1):
        self.src = src
        self.cap = cv2.VideoCapture(self.src)
        self.ret, self.frame = self.cap.read()
        self.lock = threading.Lock()
        self.running = True
        threading.Thread(target=self.update, daemon=True).start()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            with self.lock:
                self.ret = ret
                self.frame = frame

    def read(self):
        with self.lock:
            return self.ret, self.frame

    def release(self):
        self.running = False
        self.cap.release()

camera = VideoCaptureAsync(1)  # Change 1 to 0 if device 1 is not your Iriun webcam

def gen_frames():
    frame_count = 0
    process_every_n_frames = 7
    face_data = []

    while True:
        success, img = camera.read()
        if not success or img is None:
            continue

        frame_count += 1

        if frame_count % process_every_n_frames == 0:
            imgS = cv2.resize(img, (0, 0), fx=0.3, fy=0.3)
            imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

            facesCurFrame = face_recognition.face_locations(imgS, model='hog')  # faster than cnn
            encodesCurFrame = face_recognition.face_encodings(imgS, facesCurFrame)

            face_data = []
            for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):
                matches = face_recognition.compare_faces(encodeListKnown, encodeFace, tolerance=0.6)
                faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)
                matchIndex = np.argmin(faceDis)
                name = "Unknown"
                if matches[matchIndex]:
                    name = classNames[matchIndex].upper()
                    markAttendance(name)

                y1, x2, y2, x1 = faceLoc
                y1, x2, y2, x1 = int(y1 / 0.3), int(x2 / 0.3), int(y2 / 0.3), int(x1 / 0.3)
                face_data.append((name, (x1, y1, x2, y2)))

        for name, (x1, y1, x2, y2) in face_data:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(img, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
            cv2.putText(img, name, (x1 + 6, y2 - 6),
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 1)

        ret, buffer = cv2.imencode('.jpg', img)
        frame = buffer.tobytes()

        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/attendance_data')
def attendance_data():
    data = []
    if os.path.exists('Attendance.csv'):
        with open('Attendance.csv', 'r') as f:
            lines = f.readlines()[1:]
            for line in lines:
                parts = line.strip().split(',')
                if len(parts) == 2:
                    data.append({'name': parts[0], 'time': parts[1]})
    return jsonify(data)

@app.route('/video')
def video():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
