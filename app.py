
from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("swift-catfish-468017-n0-2a6e16d0098f.json", scope)
client = gspread.authorize(creds)

sheet_url = "https://docs.google.com/spreadsheets/d/1KM8zpgGfAl5T3V39Ix0mWLOeGQX2YDEf4arkbph3Ua8"

@app.route("/")
def index():
    return render_template("home.html")

@app.route("/get_players")
def get_players():
    day = request.args.get("day", "Saturday")
    sheet = client.open_by_url(sheet_url).worksheet(day)
    data = sheet.get_all_values()[1:]  # Skip header row

    players = [f"{row[1]}, {row[2]} ({row[3]})" for row in data if len(row) >= 4]
    tee_times = sorted(list(set([row[0] for row in data if row[0]])))

    return jsonify({"players": players, "tee_times": tee_times})

if __name__ == "__main__":
    app.run(debug=True)
