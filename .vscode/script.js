// --- FIREBASE AUTH LOGIN PAGE ---
// IMPORTANT: Add your domain to Firebase Console → Authentication → Settings → Authorized Domains
// Examples: "localhost", "127.0.0.1", "yourprojectname.web.app", "yourdomain.com"

// Import Firebase SDK (v9+ modular)
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js";
import { getAuth, signInWithEmailAndPassword } from "https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js";

// Your Firebase configuration (replace with your own from Firebase Console)
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID"
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
