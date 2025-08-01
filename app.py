from flask import Flask, render_template, request, jsonify
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name")
    email = request.form.get("email")
    tournament = request.form.get("tournament")
    tee_time = request.form.get("tee_time")

    if not name or not email or not tournament or not tee_time:
        return jsonify(success=False), 400

    try:
        msg = EmailMessage()
        msg["Subject"] = "Tee Time Confirmation"
        msg["From"] = os.getenv("EMAIL_USER")
        msg["To"] = email
        msg.set_content(f"Hi {name},\n\nYour tee time for the {tournament} has been confirmed:\n{tee_time}\n\nSee you there!\n– Brisa")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
            smtp.send_message(msg)
        return jsonify(success=True)
    except Exception as e:
        print("Error sending email:", e)
        return jsonify(success=False), 500

if __name__ == "__main__":
    app.run(debug=True)