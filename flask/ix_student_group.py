import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
if not firebase_admin._apps:   # only initialize if not already
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Fetch all students
students_ref = db.collection("users").where("role_type", "==", 1).stream()

for student_doc in students_ref:
    student = student_doc.to_dict()
    uid = student_doc.id

    # Fetch role document
    role_ref = db.collection("users").document(uid).collection("roles").document("student")
    role_doc = role_ref.get()

    if not role_doc.exists:
        print(f"[WARN] Student {uid} has no role document, skipping")
        continue

    role_data = role_doc.to_dict()
    fk_groupcode = role_data.get("fk_groupcode")
    program_id = role_data.get("program")

    # Skip if already has group assigned
    if fk_groupcode:
        continue

    if not program_id:
        print(f"[WARN] Student {uid} has no program assigned, skipping")
        continue

    # Find first group for this program
    group_docs = db.collection('groups').where('fk_program', '==', program_id).limit(1).stream()

    first_group_id = None
    for g in group_docs:
        first_group_id = g.id
        break

    if not first_group_id:
        print(f"[WARN] No group found for program {program_id}, skipping student {uid}")
        continue

    # Update student role with fk_groupcode
    role_ref.update({"fk_groupcode": first_group_id})
    print(f"[INFO] Updated student {uid} with group {first_group_id}")
