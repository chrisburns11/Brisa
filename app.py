
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tee_times.db'
app.config['MAIL_SERVER'] = 'smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@example.com'
app.config['MAIL_PASSWORD'] = 'your_password'

mail = Mail(app)
db = SQLAlchemy(app)

class TeeTime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament = db.Column(db.String(100))
    day = db.Column(db.String(20))
    time = db.Column(db.String(20))
    players = db.relationship('Player', backref='tee_time', lazy=True)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    sms_opt_in = db.Column(db.Boolean)
    tee_time_id = db.Column(db.Integer, db.ForeignKey('tee_time.id'))

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/<tournament>')
def tournament_page(tournament):
    tee_times = TeeTime.query.filter_by(tournament=tournament).all()
    return render_template('tournament.html', tournament=tournament, tee_times=tee_times)

@app.route('/register/<int:tee_time_id>', methods=['GET', 'POST'])
def register(tee_time_id):
    tee_time = TeeTime.query.get_or_404(tee_time_id)

    if request.method == 'POST':
        if len(tee_time.players) >= 4:
            flash('This tee time is already full.')
            return redirect(url_for('tournament_page', tournament=tee_time.tournament))

        player = Player(
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            phone=request.form['phone'],
            email=request.form['email'],
            sms_opt_in=('sms_opt_in' in request.form),
            tee_time=tee_time
        )

        db.session.add(player)
        db.session.commit()

        send_confirmation_email(player)
        if player.sms_opt_in:
            send_confirmation_sms(player)

        flash('Your tee time has been successfully reserved!')
        return redirect(url_for('tournament_page', tournament=tee_time.tournament))

    return render_template('register.html', tee_time=tee_time)

def send_confirmation_email(player):
    msg = Message('Tee Time Confirmation', sender='noreply@example.com', recipients=[player.email])
    msg.body = f"Hello {player.first_name},\n\nYour tee time has been confirmed for {player.tee_time.day} at {player.tee_time.time}.\n\nThank you!"
    mail.send(msg)

def send_confirmation_sms(player):
    pass

@app.cli.command('create_tee_times')
def create_tee_times():
    db.create_all()
    tournaments = ['U.S. Open', "U.S. Women's Amateur", 'U.S. Amateur']
    days = ['Day 1', 'Day 2']

    for tournament in tournaments:
        for day in days:
            for hour in range(7, 14):
                for minute in [0, 20, 40]:
                    period = 'am' if hour < 12 else 'pm'
                    display_hour = hour if hour <= 12 else hour - 12
                    time_str = f"{display_hour}:{minute:02}{period}"
                    tee_time = TeeTime(tournament=tournament, day=day, time=time_str)
                    db.session.add(tee_time)
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
