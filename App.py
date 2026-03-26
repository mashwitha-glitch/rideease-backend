"""
RideEase — Python Flask Backend
================================
Endpoints:
  POST /api/book          → Submit a booking (SMS + Email + MongoDB)
  GET  /api/admin/bookings → View all bookings (password protected)
  GET  /api/health         → Health check

Run:
  python App.py
"""

# ── MUST be first, before any other imports ──────────────────
from dotenv import load_dotenv
load_dotenv()
# ─────────────────────────────────────────────────────────────

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from routes.booking import (
    generate_booking_id,
    save_booking,
    send_booking_sms,
    send_booking_emails,
    get_all_bookings,
)

app = Flask(__name__)
CORS(app)  # Allows your HTML frontend to call this backend


# ─────────────────────────────────────────────────────────────
#  VALIDATION HELPER
# ─────────────────────────────────────────────────────────────
def validate_booking(data: dict) -> str | None:
    """Return an error message string if validation fails, else None."""
    required = ["trip_type", "pickup", "drop", "date", "time", "cab_type", "name", "mobile"]
    for field in required:
        if not data.get(field, "").strip():
            return f"Missing required field: {field}"

    mobile = data["mobile"].strip()
    if not mobile.isdigit() or len(mobile) != 10 or mobile[0] not in "6789":
        return "Invalid Indian mobile number. Must be 10 digits starting with 6-9."

    return None


# ─────────────────────────────────────────────────────────────
#  ROUTE 1 — Health Check
# ─────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "RideEase Backend"}), 200


# ─────────────────────────────────────────────────────────────
#  ROUTE 2 — Submit Booking
# ─────────────────────────────────────────────────────────────
@app.route("/api/book", methods=["POST"])
def book_cab():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    # Validate
    error = validate_booking(data)
    if error:
        return jsonify({"success": False, "error": error}), 422

    # Generate booking ID and attach to data
    data["booking_id"] = generate_booking_id()

    results = {
        "booking_id": data["booking_id"],
        "sms":        None,
        "email":      None,
        "db":         None,
    }
    errors = []

    # 1 ─ Save to MongoDB
    try:
        saved = save_booking(data)
        results["db"] = {"success": True, "booking": saved}
        print(f"[DB] Booking saved: {data['booking_id']}")
    except Exception as e:
        error_msg = f"Database error: {str(e)}"
        results["db"] = {"success": False, "error": error_msg}
        errors.append(error_msg)
        print(f"[DB ERROR] {error_msg}")

    # 2 ─ Send SMS
    try:
        sms_result = send_booking_sms(data)
        results["sms"] = sms_result
        print(f"[SMS] Result: {sms_result}")
    except Exception as e:
        error_msg = f"SMS error: {str(e)}"
        results["sms"] = {"success": False, "error": error_msg}
        errors.append(error_msg)
        print(f"[SMS ERROR] {error_msg}")

    # 3 ─ Send Email (only if customer email was provided)
    if data.get("email", "").strip():
        try:
            email_result = send_booking_emails(data)
            results["email"] = email_result
            print(f"[EMAIL] Result: {email_result}")
        except Exception as e:
            error_msg = f"Email error: {str(e)}"
            results["email"] = {"success": False, "error": error_msg}
            errors.append(error_msg)
            print(f"[EMAIL ERROR] {error_msg}")
    else:
        results["email"] = {"skipped": "No customer email provided"}

    # Return response
    if results["db"] and results["db"].get("success"):
        return jsonify({
            "success":    True,
            "message":    "Booking confirmed!",
            "booking_id": data["booking_id"],
            "details":    results,
            "warnings":   errors if errors else None,
        }), 201
    else:
        return jsonify({
            "success": False,
            "error":   "Booking could not be saved. Please check your MongoDB connection.",
            "details": results,
        }), 500


# ─────────────────────────────────────────────────────────────
#  ROUTE 3 — Admin: View All Bookings
#  Usage: GET /api/admin/bookings?password=admin123&limit=50
# ─────────────────────────────────────────────────────────────
@app.route("/api/admin/bookings", methods=["GET"])
def admin_bookings():
    password = request.args.get("password", "")
    if password != os.getenv("ADMIN_PASSWORD", "admin123"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    limit = int(request.args.get("limit", 100))
    try:
        bookings = get_all_bookings(limit=limit)
        return jsonify({
            "success":  True,
            "total":    len(bookings),
            "bookings": bookings,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
#  START SERVER
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"""
  ╔══════════════════════════════════════════╗
  ║       RideEase Backend is running        ║
  ║  Local:  http://127.0.0.1:{port}           ║
  ║                                          ║
  ║  Endpoints:                              ║
  ║   POST /api/book                         ║
  ║   GET  /api/admin/bookings?password=...  ║
  ║   GET  /api/health                       ║
  ╚══════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port)
