import os
import json
import pandas as pd
import gspread
import codecs
from google.oauth2.service_account import Credentials
from flask import Flask, request, jsonify, render_template
from flask_mail import Mail, Message
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

app = Flask(__name__)

# Mail config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)

# Twilio config
twilio_client = Client(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH"))
twilio_number = os.getenv("TWILIO_NUMBER")

# Google Sheets setup
scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
google_creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_CREDS_PATH"),
    scopes=scopes
)
gc = gspread.authorize(google_creds)

@app.route('/')
def index():
    return render_template("home.html")

@app.route('/load_players', methods=['POST'])
def load_players():
    day = request.json.get("day")
    sheet = gc.open_by_key(os.getenv("SHEET_ID")).worksheet(day)
    data = sheet.get_all_records()
    return jsonify(data)

@app.route('/send_confirmation', methods=['POST'])
def send_confirmation():
    data = request.json
    tee_time = data.get("tee_time")
    players = data.get("players", [])
    recipient_email = data.get("email")
    recipient_name = data.get("name")
    phone = data.get("phone")

    # Email
    try:
        msg = Message("Brisa Tee Time Confirmation",
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[recipient_email])
        msg.body = f"Hi {recipient_name},\n\nYou're confirmed for {tee_time}.\n\nPlayers:\n" + \
                   "\n".join([f"{p['Last Name']}, {p['First Name']} ({p['Country']})" for p in players])
        mail.send(msg)
    except Exception as e:
        print(f"Email failed: {e}")

    # SMS
    try:
        if phone:
            twilio_client.messages.create(
                body=f"Hi {recipient_name}, you're confirmed for {tee_time} with Brisa. Good luck!",
                from_=twilio_number,
                to=phone
            )
    except Exception as e:
        print(f"SMS failed: {e}")

    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True)

