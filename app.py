from flask import Flask, render_template, request, jsonify
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- Home Page ---
@app.route("/")
def home():
    return render_template("index.html")

# --- Example HTMX endpoint ---
@app.route("/api/ask", methods=["POST"])
def ask_gemini():
    user_text = request.form.get("text")

    # TODO: replace with real Gemini API call
    response_text = f"You said: {user_text}"

    return jsonify({"reply": response_text})

if __name__ == "__main__":
    app.run(debug=True)
