// --- FIREBASE AUTH LOGIN PAGE ---
// IMPORTANT: Add your domain to Firebase Console → Authentication → Settings → Authorized Domains
// Examples: "localhost", "127.0.0.1", "yourprojectname.web.app", "yourdomain.com"

// Import Firebase SDK (v9+ modular)
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js";
import { getAuth, signInWithEmailAndPassword } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";

// Your Firebase configuration (replace with your own from Firebase Console)
const firebaseConfig = {
  apiKey: "AIzaSyC_pq3Gnzwkdvc9CPeRa3Yre_vkcijzVpk",
  authDomain: "aimanzamani.firebaseapp.com",
  projectId: "aimanzamani",
  storageBucket: "aimanzamani.firebasestorage.app",
  messagingSenderId: "63348630728",
  appId: "1:63348630728:web:5d1537bd1c6e14535171fd"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// Handle Login
document.getElementById("loginBtn").addEventListener("click", () => {
  const email = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  if (!email || !password) {
    alert("Please fill in all fields.");
    return;
  }

  signInWithEmailAndPassword(auth, email, password)
    .then(userCredential => {
      const user = userCredential.user;
      alert("✅ Login successful! Welcome " + user.email);
      window.location.href = "dashboard.html"; // Redirect after login
    })
    .catch(error => {
      alert("❌ Error: " + error.message);
    });
});

// --- PASSWORD MODAL FUNCTIONALITY ---
const changePasswordButton = document.getElementById('changePasswordButton');
const passwordModal = document.getElementById('passwordModal');
const closeModalButton = document.getElementById('closeModal');
const cancelButton = document.getElementById('cancelButton');

if (changePasswordButton && passwordModal && closeModalButton && cancelButton) {
  changePasswordButton.addEventListener('click', () => passwordModal.classList.add('open'));
  closeModalButton.addEventListener('click', () => passwordModal.classList.remove('open'));
  cancelButton.addEventListener('click', () => passwordModal.classList.remove('open'));
}