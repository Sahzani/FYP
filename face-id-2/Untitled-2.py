# Backend (/upload in app.py) – Face Recognition + DB
# You already have this working in your uploaded app.py:

# @app.route('/upload', methods=['POST'])
# def upload():
#     data = request.json
#     if 'image' not in data:
#         return jsonify({'success': False, 'error': 'No image provided'})

#     # Decode image
#     img_data = data['image'].split(',')[1]
#     img_bytes = base64.b64decode(img_data)
#     np_arr = np.frombuffer(img_bytes, np.uint8)
#     img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
#     img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

#     # Detect face
#     facesCurFrame = face_recognition.face_locations(img)
#     encodesCurFrame = face_recognition.face_encodings(img, facesCurFrame)

#     for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):
#         matches = face_recognition.compare_faces(encodeListKnown, encodeFace)
#         faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)
#         matchIndex = np.argmin(faceDis)

#         if matches[matchIndex]:
#             name = classNames[matchIndex].upper()
#             markAttendance(name)  # ← sends to DB
#             return jsonify({'success': True, 'name': name})

#     return jsonify({'success': False, 'error': 'No Match'})
