import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mail import Mail, Message
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # You should replace this with a secure key

# Email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("EMAIL_USER")
app.config['MAIL_PASSWORD'] = os.getenv("EMAIL_PASS")

mail = Mail(app)

# Twilio config (corrected key)
twilio_sid = os.getenv("TWILIO_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE")  # Matches .env key

client = Client(twilio_sid, twilio_token)

# Helper function to create tee times list with unique IDs
def create_tee_times(start_id):
    times = []
    for idx, time_str in enumerate(['07:00 AM', '07:20 AM', '07:40 AM', '08:00 AM', '08:20 AM', '08:40 AM', '09:00 AM', '09:20 AM', '09:40 AM', '10:00 AM', '10:20 AM', '10:40 AM', '11:00 AM', '11:20 AM', '11:40 AM', '12:00 PM', '12:20 PM', '12:40 PM', '01:00 PM']):
        times.append({"id": start_id + idx, "time": time_str, "players": []})
    return times

# Tee times structure
tee_times = {
    "U.S. Open": {"Tuesday": create_tee_times(1), "Wednesday": create_tee_times(100)},
    "U.S. Women's Amateur": {"Tuesday": create_tee_times(200), "Wednesday": create_tee_times(300)},
    "U.S. Amateur": {"Tuesday": create_tee_times(400), "Wednesday": create_tee_times(500)},
}

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/<tournament>')
def show_tee_times(tournament):
    if tournament not in tee_times:
        return "Tournament not found", 404
    return render_template('tournament.html', tournament=tournament, days=tee_times[tournament])

@app.route('/register/<tournament>/<day>/<int:tee_time_id>', methods=['GET', 'POST'])
def register(tournament, day, tee_time_id):
    if tournament not in tee_times or day not in tee_times[tournament]:
        return "Invalid tournament or day", 404

    selected_time = next((t for t in tee_times[tournament][day] if t['id'] == tee_time_id), None)
    if not selected_time:
        return "Tee time not found", 404

    if request.method == 'POST':
        if len(selected_time['players']) >= 4:
            flash('Tee time is full.')
            return redirect(url_for('show_tee_times', tournament=tournament))

        player = {
            "first_name": request.form['first_name'],
            "last_name": request.form['last_name'],
            "phone": request.form['phone'],
            "email": request.form['email']
        }
        selected_time['players'].append(player)

        # Send confirmation email
        msg = Message('Brisa Tee Time Confirmation', recipients=[player['email']])
        msg.body = f"Hello {player['first_name']},\n\nYou are registered for {tournament} on {day} at {selected_time['time']}.\n\nThank you for using Brisa!"
        mail.send(msg)

        # Send SMS confirmation if opted in
        if 'sms_opt_in' in request.form:
            try:
                client.messages.create(
                    to=player["phone"],
                    from_=twilio_number,
                    body=f"Hi {player['first_name']}, you're confirmed for {tournament} on {day} at {selected_time['time']}. - Brisa"
                )
            except Exception as e:
                print(f"SMS failed to send: {e}")

        flash('Registration successful. Confirmation sent.')
        return redirect(url_for('show_tee_times', tournament=tournament))

    return render_template('register.html', tee_time=selected_time, tournament=tournament, day=day)

if __name__ == "__main__":
    app.run(debug=True)