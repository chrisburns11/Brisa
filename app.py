import os
from flask import Flask, render_template, request, redirect, url_for
from flask_mail import Mail, Message
from twilio.rest import Client
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Flask-Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
mail = Mail(app)

# Dummy data for tournaments and tee times
tournaments = {
    "U.S. Women's Amateur": {
        "Monday": ["8:00 AM", "8:10 AM", "8:20 AM"],
        "Tuesday": ["9:00 AM", "9:10 AM", "9:20 AM"]
    }
}

selected_times = []

# Helper function to send SMS
def send_sms(to, message):
    try:
        client = Client(os.environ.get('TWILIO_SID'), os.environ.get('TWILIO_AUTH_TOKEN'))
        client.messages.create(
            body=message,
            from_=os.environ.get('TWILIO_PHONE_NUMBER'),
            to=to
        )
        print(f"✅ SMS sent to {to}")
    except Exception as e:
        print(f"❌ SMS failed to {to}: {e}")

@app.route("/")
def index():
    return render_template("index.html", tournaments=tournaments)

@app.route("/submit", methods=["POST"])
def submit():
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    email = request.form['email']
    phone = request.form['phone']
    tournament = request.form['tournament']
    day = request.form['day']
    time = request.form['time']

    player = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "tournament": tournament,
        "day": day,
        "time": time,
        "timestamp": datetime.utcnow().isoformat()
    }
    selected_times.append(player)

    # Send confirmation email
    try:
        msg = Message('Brisa Tee Time Confirmation', recipients=[player['email']])
        msg.body = f"Hello {player['first_name']}, your tee time for {tournament} on {day} at {time} has been confirmed."
        mail.send(msg)
        print(f"✅ Email sent to {email}")
    except Exception as e:
        print(f"❌ Email failed to {email}: {e}")

    # Send SMS if opted in
    if 'sms_opt_in' in request.form:
        sms_message = f"Hi {first_name}! Your Brisa tee time for {tournament} on {day} at {time} is confirmed."
        send_sms(phone, sms_message)

    return redirect(url_for('index', success=1))

if __name__ == "__main__":
    app.run(debug=True)
