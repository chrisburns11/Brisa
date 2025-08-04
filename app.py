
import os
import json
import gspread
from flask import Flask, render_template
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Load credentials from environment variable
google_creds = json.loads(os.environ["GOOGLE_CREDS_JSON"])

# Use creds to create a client to interact with the Google Drive API
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)

def get_players_by_day(sheet_name):
    sheet = client.open("Brisa Tee Times").worksheet(sheet_name)
    data = sheet.get_all_values()[1:]  # Skip header row
    tee_times = {}
    for row in data:
        tee_time, last_name, first_name, country = row
        if tee_time not in tee_times:
            tee_times[tee_time] = []
        tee_times[tee_time].append({
            "name": f"{last_name}, {first_name} ({country})",
            "last": last_name,
            "first": first_name,
            "country": country
        })
    return tee_times

@app.route("/")
def home():
    saturday = get_players_by_day("Saturday")
    sunday = get_players_by_day("Sunday")
    return render_template("home.html", saturday=saturday, sunday=sunday)

if __name__ == "__main__":
    app.run(debug=True)
