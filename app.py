import os
import json
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, request, jsonify, render_template
from flask_mail import Mail, Message
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

app = Flask(__name__)

# -------------------------
# Mail config
# -------------------------
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
# Optional: set default sender to avoid needing 'sender=' each time
if os.getenv("MAIL_USERNAME"):
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")

mail = Mail(app)

# -------------------------
# Twilio config
# -------------------------
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
twilio_client = Client(TWILIO_SID, TWILIO_AUTH) if (TWILIO_SID and TWILIO_AUTH) else None

# -------------------------
# Google Sheets setup (env JSON first; path fallback for local)
# -------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEET_ID = os.getenv("SHEET_ID")

def build_google_creds():
    """Build Credentials from env JSON, else optional file path (local dev)."""
    raw = os.getenv("GOOGLE_CREDS_JSON")
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError("GOOGLE_CREDS_JSON is not valid JSON") from e
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    path = os.getenv("GOOGLE_CREDS_PATH")
    if path:
        return Credentials.from_service_account_file(path, scopes=SCOPES)

    raise RuntimeError(
        "No Google credentials found. Set GOOGLE_CREDS_JSON (preferred) "
        "or GOOGLE_CREDS_PATH."
    )

def get_gspread_client():
    """Lazy-init and cache the gspread client so import-time failures don’t kill Gunicorn."""
    if not hasattr(get_gspread_client, "_client"):
        creds = build_google_creds()
        get_gspread_client._client = gspread.authorize(creds)
    return get_gspread_client._client

# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return render_template("home.html")

@app.route("/load_players", methods=["POST"])
def load_players():
    try:
        day = request.json.get("day")
        if not day:
            return jsonify({"error": "Missing 'day'"}), 400
        if not SHEET_ID:
            return jsonify({"error": "SHEET_ID not configured"}), 500

        gc = get_gspread_client()
        sheet = gc.open_by_key(SHEET_ID).worksheet(day)
        raw_data = sheet.get_all_records()

        cleaned_data = [
            {
                "first_name": row.get("First Name", "").strip(),
                "last_name": row.get("Last Name", "").strip(),
                "country": row.get("Country", "").strip(),
            }
            for row in raw_data
            if row.get("First Name") and row.get("Last Name")
        ]
        return jsonify(cleaned_data)
    except Exception as e:
        # Don’t leak secrets; give a helpful message for logs and a generic error to client
        print(f"/load_players error: {e}")
        return jsonify({"error": "Failed to load players"}), 500

@app.route("/send_confirmation", methods=["POST"])
def send_confirmation():
    data = request.json or {}
    tee_time = data.get("tee_time")
    players = data.get("players", [])
    recipient_email = data.get("email")
    recipient_name = data.get("name") or "there"
    phone = data.get("phone")

    # Basic validation
    if not tee_time or not recipient_email:
        return jsonify({"error": "Missing tee_time or email"}), 400

    # Build player list text
    players_text = "\n".join(
        f"{p.get('last_name','').strip()}, {p.get('first_name','').strip()} ({p.get('country','').strip()})"
        for p in players
        if p.get("first_name") and p.get("last_name")
    )

    # Email
    try:
        msg = Message("Brisa Tee Time Confirmation", recipients=[recipient_email])
        msg.body = (
            f"Hi {recipient_name},\n\n"
            f"You're confirmed for {tee_time}.\n\n"
            f"Players:\n{players_text if players_text else 'TBD'}"
        )
        mail.send(msg)
    except Exception as e:
        print(f"Email failed: {e}")

    # SMS
    try:
        if phone and twilio_client and TWILIO_NUMBER:
            twilio_client.messages.create(
                body=f"Hi {recipient_name}, you're confirmed for {tee_time} with Brisa. Good luck!",
                from_=TWILIO_NUMBER,
                to=phone,
            )
    except Exception as e:
        print(f"SMS failed: {e}")

    return jsonify({"status": "success"})

# Optional: simple health check endpoint for Render
@app.route("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(debug=True)
