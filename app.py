import os
import json
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, render_template

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SERVICE_ACCOUNT_FILE = 'swift-catfish-468017-n0-2a6e16d0098f.json'

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

gc = gspread.authorize(creds)

def get_players_by_day(sheet_name):
    sheet = gc.open("Brisa Tee Times").worksheet(sheet_name)
    data = sheet.get_all_values()
    tee_times = {}
    for row in data[1:]:
        if len(row) < 4:
            continue
        time, last, first, country = row
        key = f"{last}, {first} ({country})"
        tee_times.setdefault(time, []).append(key)
    return tee_times

@app.route('/')
def index():
    saturday_players = get_players_by_day("Saturday")
    sunday_players = get_players_by_day("Sunday")
    return render_template('home.html', saturday_players=saturday_players, sunday_players=sunday_players)

if __name__ == '__main__':
    app.run(debug=True)