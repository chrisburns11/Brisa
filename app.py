from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    # Dummy data structure expected by the template
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

@app.route("/test")
def test():
    return "Brisa is alive!"
