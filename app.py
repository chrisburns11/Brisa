import os
from flask import Flask, render_template, request
from flask_mail import Mail, Message
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("EMAIL_USER")
app.config['MAIL_PASSWORD'] = os.getenv("EMAIL_PASS")

mail = Mail(app)

twilio_sid = os.getenv("TWILIO_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE")

client = Client(twilio_sid, twilio_token)

@app.route("/")
def index():
    tournaments = {
        "Spring Classic": {
            "Friday": ["8:00 AM", "9:00 AM", "10:00 AM"],
            "Saturday": ["8:30 AM", "9:30 AM"]
        },
        "Summer Open": {
            "Sunday": ["10:00 AM", "11:00 AM"]
        }
    }
    return render_template("index.html", tournaments=tournaments)

@app.route("/submit", methods=["POST"])
def submit():
    name = request.form["name"]
    email = request.form["email"]
    phone = request.form.get("phone")
    tournament = request.form["tournament"]
    day = request.form["day"]
    time = request.form["time"]

    tee_time = f"{tournament} - {day} at {time}"

    msg = Message("Tee Time Confirmation",
                  sender=os.getenv("EMAIL_USER"),
                  recipients=[email])
    msg.body = f"Hi {name},\n\nYour tee time for {tournament_name} on {day} at {tee_time} has been confirmed.\n\nThank you for using Brisa!"

You are confirmed for: {tee_time}

– Brisa"
    mail.send(msg)

    if phone:
        client.messages.create(
            to=phone,
            from_=twilio_number,
            body=f"Hi {name},\n\nYour tee time for {tournament_name} on {day} at {tee_time} has been confirmed.\n\n- Brisa"
        )

    return f"Thanks {name}, your tee time is confirmed for {tee_time}!"

if __name__ == "__main__":
    app.run(debug=True)
