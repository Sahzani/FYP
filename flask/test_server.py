from flask import Flask, Response
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# --- Using local SSL files ---
# These files were copied from /etc/letsencrypt/live/...
CERT_PATH = "flask_cert.pem"
KEY_PATH = "flask_key.pem"
# -----------------------------

@app.route("/test")
def test_route():
    # Return a simple text response to confirm the server is reachable
    return "Server is CONNECTED and responsive on port 5001!", 200

if __name__ == "__main__":
    print("[INFO] Starting simple test server on port 5001...")
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False,
        threaded=True,
        ssl_context=(CERT_PATH, KEY_PATH)
    )