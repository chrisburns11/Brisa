
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

app = Flask(__name__)
CORS(app)

# Load environment variables
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

# Sample tournament and tee time data
tournaments = {
    "U.S. Open": {
        "2025-06-12": ["8:00 AM", "9:00 AM", "10:00 AM"],
        "2025-06-13": ["8:30 AM", "9:30 AM", "10:30 AM"]
    },
    "U.S. Women's Amateur": {
        "2025-08-05": ["7:00 AM", "8:00 AM", "9:00 AM"],
        "2025-08-06": ["7:30 AM", "8:30 AM", "9:30 AM"]
    }
}

@app.route("/")
def home():
    return render_template("home.html", tournaments=tournaments)

@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    tournament = data.get("tournament")
    date = data.get("date")
    time = data.get("time")

    if not all([name, email, tournament, date, time]):
        return jsonify({"success": False, "message": "All fields are required."})

    try:
        # Send email
        subject = f"Tee Time Confirmation for {tournament}"
        body = f"Hi {name},\n\nYou're confirmed for the {tournament} on {date} at {time}.\n\nThanks for using Brisa!"

        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, email, msg.as_string())
        server.quit()

        return jsonify({"success": True, "message": "Confirmation sent successfully."})
    except Exception as e:
        print("Error sending email:", e)
        return jsonify({"success": False, "message": "There was an error sending the confirmation."})

if __name__ == "__main__":
    app.run(debug=True)
