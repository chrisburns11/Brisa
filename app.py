import os
import re
import json
import gspread
from urllib.parse import urlparse, parse_qs
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
# Google Sheets setup
# -------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Accept either a full Sheets URL or the bare spreadsheet ID
SHEET_REF = os.getenv("SHEET_URL") or os.getenv("SHEET_ID")

def build_google_creds():
    """Build Credentials from env JSON, else optional file path (local dev)."""
    raw = os.getenv("GOOGLE_CREDS_JSON") or os.getenv("GOOGLE_CREDENTIALS")
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError("GOOGLE_CREDS_JSON/GOOGLE_CREDENTIALS is not valid JSON") from e
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    path = os.getenv("GOOGLE_CREDS_PATH")
    if path:
        return Credentials.from_service_account_file(path, scopes=SCOPES)

    raise RuntimeError(
        "No Google credentials found. Set GOOGLE_CREDS_JSON (preferred), "
        "GOOGLE_CREDENTIALS, or GOOGLE_CREDS_PATH."
    )

def get_gspread_client():
    """Lazy-init and cache the gspread client so import-time failures don’t kill Gunicorn."""
    if not hasattr(get_gspread_client, "_client"):
        creds = build_google_creds()
        get_gspread_client._client = gspread.authorize(creds)
    return get_gspread_client._client

# ---- Robust ID extraction ----
_SPREADSHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")

def _extract_sheet_id(ref: str) -> str | None:
    """
    Return the spreadsheet ID from:
      - https://docs.google.com/spreadsheets/d/<ID>/edit...
      - https://drive.google.com/open?id=<ID>
      - drive.google.com/file/d/<ID>/view
      - or return ref if it already looks like a bare ID
    """
    if not ref:
        return None
    s = ref.strip().strip('"').strip("'")

    # Bare ID (heuristic)
    if "/" not in s and "google.com" not in s and len(s) >= 30:
        return s

    # Parse URLs
    if "google.com" in s:
        if not s.startswith(("http://", "https://")):
            s = "https://" + s
        u = urlparse(s)

        # docs.google.com/spreadsheets/d/<ID>
        m = _SPREADSHEET_ID_RE.search(u.path)
        if m:
            return m.group(1)

        # drive.google.com/open?id=<ID>
        qs = parse_qs(u.query or "")
        if "id" in qs and qs["id"]:
            return qs["id"][0]

        # drive.google.com/file/d/<ID>/view
        m2 = re.search(r"/file/d/([a-zA-Z0-9-_]+)", u.path)
        if m2:
            return m2.group(1)

    return None

def _open_sheet(gc, ref: str):
    """Always resolve to a spreadsheet ID and open by key (works for URL or ID)."""
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("SHEET_URL/SHEET_ID not configured")

    sid = _extract_sheet_id(ref)
    if not sid:
        raise ValueError("Could not extract a spreadsheet ID from SHEET_URL/SHEET_ID")
    return gc.open_by_key(sid)

# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return render_template("home.html")

@app.route("/load_players", methods=["POST"])
def load_players():
    try:
        data = request.json or {}
        day = data.get("day")
        if not day:
            return jsonify({"error": "Missing 'day'"}), 400
        if not SHEET_REF:
            return jsonify({"error": "SHEET_ID not configured"}), 500

        gc = get_gspread_client()
        sh = _open_sheet(gc, SHEET_REF)
        sheet = sh.worksheet(day)
        raw_data = sheet.get_all_records()

        cleaned_data = [
            {
                "first_name": (row.get("First Name") or "").strip(),
                "last_name": (row.get("Last Name") or "").strip(),
                "country": (row.get("Country") or "").strip(),
            }
            for row in raw_data
            if (row.get("First Name") and row.get("Last Name"))
        ]
        return jsonify(cleaned_data)
    except Exception as e:
        print(f"/load_players error: {e}")
        if os.getenv("SHOW_ERRORS") == "1":
            return jsonify({"error": str(e)}), 500
        return jsonify({"error": "Failed to load players"}), 500

@app.route("/send_confirmation", methods=["POST"])
def send_confirmation():
    data = request.json or {}
    tee_time = data.get("tee_time")
    players = data.get("players", [])
    recipient_email = data.get("email")
    recipient_name = data.get("name") or "there"
    phone = data.get("phone")

    if not tee_time or not recipient_email:
        return jsonify({"error": "Missing tee_time or email"}), 400

    players_text = "\n".join(
        f"{(p.get('last_name') or '').strip()}, {(p.get('first_name') or '').strip()} ({(p.get('country') or '').strip()})"
        for p in players
        if p.get("first_name") and p.get("last_name")
    )

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

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/debug-google")
def debug_google():
    try:
        gc = get_gspread_client()
        sid = _extract_sheet_id(SHEET_REF or "")
        sh = _open_sheet(gc, SHEET_REF)
        tabs = [ws.title for ws in sh.worksheets()]
        preview = (sid[-6:] if sid and len(sid) >= 6 else sid)  # avoid leaking full ID
        kind = "url" if ("google.com" in (SHEET_REF or "")) else "id"
        return {"sheet_ref_set": bool(SHEET_REF), "ref_kind": kind, "id_preview": preview, "tabs": tabs}, 200
    except Exception as e:
        return {
            "sheet_ref_set": bool(SHEET_REF),
            "error_type": type(e).__name__,
            "error": str(e),
        }, 500

if __name__ == "__main__":
    app.run(debug=True)
