import firebase_admin
from firebase_admin import credentials, firestore
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin import firestore

cred = credentials.Certificate("serviceAccountKey.json")
if not firebase_admin._apps:   # only initialize if not already
    firebase_admin.initialize_app(cred)

db = firestore.client()
