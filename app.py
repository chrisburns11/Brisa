import os
import re
import json
import gspread
from datetime import datetime, timezone
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
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

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

def _open_reservations_ws(gc):
    """Open (or create) the 'Reservations' worksheet with headers, including 'slot'."""
    sh = _open_sheet(gc, SHEET_REF)
    want_headers = [
        "timestamp_utc", "day", "tee_time",
        "first_name", "last_name", "country", "email", "status", "slot"
    ]
    try:
        ws = sh.worksheet("Reservations")
        rows = ws.get_all_values()
        if not rows:
            ws.update("A1:I1", [want_headers])
        else:
            have = rows[0]
            # If 'slot' missing, append it to the header row.
            if "slot" not in [h.strip().lower() for h in have]:
                ws.update_cell(1, len(have) + 1, "slot")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Reservations", rows=2000, cols=12)
        ws.update("A1:I1", [want_headers])
    return ws

# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return render_template("home.html")

@app.route("/reserve", methods=["POST"])
def reserve():
    try:
        data = request.json or {}
        day = (data.get("day") or "").strip()
        tee_time = (data.get("tee_time") or "").strip()
        player = data.get("player") or {}
        first_name = (player.get("first_name") or "").strip()
        last_name  = (player.get("last_name") or "").strip()
        country    = (player.get("country") or "").strip()
        email      = (data.get("email") or "").strip()  # optional
        slot       = data.get("slot")                   # 0..3 preferred
        try:
            slot = int(slot) if slot is not None else None
        except Exception:
            slot = None

        if not (day and tee_time and first_name and last_name):
            return jsonify({"error": "Missing day, tee_time, first_name, or last_name"}), 400
        if not SHEET_REF:
            return jsonify({"error": "SHEET_ID not configured"}), 500

        gc = get_gspread_client()
        ws = _open_reservations_ws(gc)

        # Duplicate check: same player already has same day/time
        rows = ws.get_all_values()
        if rows:
            header = rows[0]
            col = {name: i for i, name in enumerate(header)}
            for r in rows[1:]:
                if len(r) < len(header):
                    continue
                if (
                    r[col.get("day", 1)] == day and
                    r[col.get("tee_time", 2)] == tee_time and
                    r[col.get("first_name", 3)].strip().lower() == first_name.lower() and
                    r[col.get("last_name", 4)].strip().lower() == last_name.lower()
                ):
                    return jsonify({"error": "This player already has this tee time"}), 409

        ts = datetime.now(timezone.utc).isoformat()
        ws.append_row(
            [ts, day, tee_time, first_name, last_name, country, email, "reserved", slot],
            value_input_option="RAW"
        )

        # Send confirmation email/SMS (best-effort)
        players_text = f"{last_name}, {first_name} ({country})".strip()
        try:
            if email:
                msg = Message("Brisa Tee Time Confirmation", recipients=[email])
                msg.body = (
                    f"Hi {first_name},\n\n"
                    f"You're confirmed for {tee_time} on {day}.\n\n"
                    f"Player: {players_text}\n"
                )
                mail.send(msg)
        except Exception as e:
            print(f"Email failed: {e}")

        try:
            phone = data.get("phone")
            if phone and twilio_client and TWILIO_NUMBER:
                twilio_client.messages.create(
                    body=f"Hi {first_name}, you're confirmed for {tee_time} on {day} with Brisa.",
                    from_=TWILIO_NUMBER,
                    to=phone,
                )
        except Exception as e:
            print(f"SMS failed: {e}")

        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"/reserve error: {e}")
        return jsonify({"error": "Failed to reserve"}), 500


@app.route("/reserve/cancel", methods=["POST"])
def reserve_cancel():
    try:
        data = request.json or {}
        day = (data.get("day") or "").strip()
        tee_time = (data.get("tee_time") or "").strip()
        first_name = (data.get("first_name") or "").strip()
        last_name  = (data.get("last_name") or "").strip()
        slot       = data.get("slot")
        try:
            slot = int(slot) if slot is not None else None
        except Exception:
            slot = None

        if not (day and tee_time and first_name and last_name):
            return jsonify({"error": "Missing day, tee_time, first_name, or last_name"}), 400
        if not SHEET_REF:
            return jsonify({"error": "SHEET_ID not configured"}), 500

        gc = get_gspread_client()
        ws = _open_reservations_ws(gc)

        rows = ws.get_all_values()
        if not rows:
            return jsonify({"error": "No reservations found"}), 404

        header = rows[0]
        col = {name: i for i, name in enumerate(header)}
        target_row_index = None  # 1-based

        for idx, r in enumerate(rows[1:], start=2):
            if len(r) < len(header):
                continue
            if (
                r[col.get("day", 1)] == day and
                r[col.get("tee_time", 2)] == tee_time and
                r[col.get("first_name", 3)].strip().lower() == first_name.lower() and
                r[col.get("last_name", 4)].strip().lower() == last_name.lower() and
                (slot is None or str(r[col.get("slot", 8)] or "").strip() == str(slot))
            ):
                target_row_index = idx
                break

        if not target_row_index:
            return jsonify({"error": "Reservation not found"}), 404

        ws.delete_rows(target_row_index)
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"/reserve/cancel error: {e}")
        return jsonify({"error": "Failed to cancel reservation"}), 500

@app.route("/load_reservations", methods=["POST"])
def load_reservations():
    try:
        data = request.json or {}
        day = (data.get("day") or "").strip()
        if not day:
            return jsonify({"error": "Missing 'day'"}), 400
        if not SHEET_REF:
            return jsonify({"error": "SHEET_ID not configured"}), 500

        gc = get_gspread_client()
        ws = _open_reservations_ws(gc)
        rows = ws.get_all_values()
        if not rows:
            return jsonify([])

        header = rows[0]
        col = {name: i for i, name in enumerate(header)}
        out = []
        for r in rows[1:]:
            if len(r) < len(header):
                continue
            if r[col.get("day", 1)] != day:
                continue
            status = (r[col.get("status", 7)] or "").strip().lower()
            if status and status != "reserved":
                continue
            out.append({
                "day": r[col.get("day", 1)],
                "tee_time": r[col.get("tee_time", 2)],
                "first_name": r[col.get("first_name", 3)],
                "last_name": r[col.get("last_name", 4)],
                "country": r[col.get("country", 5)],
                "email": r[col.get("email", 6)],
                "slot": (int(r[col.get("slot", 8)]) if (len(r) > col.get("slot", 8) and r[col.get("slot", 8)].strip() != "") else None),
            })
        return jsonify(out)
    except Exception as e:
        print(f"/load_reservations error: {e}")
        return jsonify({"error": "Failed to load reservations"}), 500

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
