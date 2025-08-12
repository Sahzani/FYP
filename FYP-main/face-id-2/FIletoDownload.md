Absolutely! Here’s a **step-by-step guide** to set up a simple **Face Recognition** project using **Flask + OpenCV** (and the popular `face_recognition` library) including environment setup and all dependencies.

---

# Step-by-step: Flask + OpenCV + face\_recognition Face Recognition Setup

---

## 1. Install Python (if not installed)

* Make sure you have **Python 3.7+** installed.
* Download from [python.org](https://www.python.org/downloads/).

Check by running:

```bash
python --version
```

---

## 2. Create a virtual environment

In your project folder, run:

```bash
python -m venv venv
```

This creates a virtual environment folder named `venv`.

---

## 3. Activate the virtual environment

* On **Windows** (PowerShell):

```powershell
.\venv\Scripts\Activate.ps1
```

If you get a policy error, run PowerShell as Admin and allow script execution:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

* On **Mac/Linux**:

```bash
source venv/bin/activate
```

You should see your prompt change to `(venv)`.

---

## 4. Install required Python packages

Inside the activated environment, run:

```bash
pip install flask opencv-python face_recognition numpy
```

* `flask`: web framework
* `opencv-python`: OpenCV bindings
* `face_recognition`: face detection and recognition library
* `numpy`: array handling (used by OpenCV and face\_recognition)

---

## 5. Prepare your project structure

Example:

```
your-project/
│
├── app.py
├── requirements.txt
├── static/
│   └── (optional: css/js files)
└── templates/
    └── index.html
```

---

## 6. Sample minimal `app.py` for face recognition

```python
from flask import Flask, render_template, Response
import cv2
import face_recognition

app = Flask(__name__)

# Initialize webcam
video_capture = cv2.VideoCapture(0)

def gen_frames():
    while True:
        success, frame = video_capture.read()
        if not success:
            break

        # Convert frame from BGR (OpenCV) to RGB (face_recognition)
        rgb_frame = frame[:, :, ::-1]

        # Find all faces in the frame
        face_locations = face_recognition.face_locations(rgb_frame)

        # Draw boxes around faces
        for (top, right, bottom, left) in face_locations:
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        # Yield frame in a byte format for streaming
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(debug=True)
```

---

## 7. Simple `templates/index.html`

```html
<!DOCTYPE html>
<html>
<head>
    <title>Face Recognition Webcam</title>
</head>
<body>
    <h1>Live Face Recognition</h1>
    <img src="{{ url_for('video_feed') }}" width="720" />
</body>
</html>
```

---

## 8. Run your Flask app

Make sure virtual environment is activated, then:

```bash
python app.py
```

Open browser at `http://127.0.0.1:5000` and you should see live webcam feed with faces detected and boxed.

---

## Extras:

* If you want to **recognize known faces**, you’ll need to load images, encode them, and compare in the loop.
* For that, load known images via `face_recognition.load_image_file()` and get encodings via `face_recognition.face_encodings()`.
* Then compare detected faces with known ones using `face_recognition.compare_faces()`.

---

If you want, I can help you build the full code with known face recognition, attendance logging, or saving snapshots — just ask!
