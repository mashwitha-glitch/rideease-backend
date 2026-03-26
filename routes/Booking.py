import os
import uuid
import requests
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_db():
    global _client
    if _client is None:
        _client = MongoClient(os.getenv("MONGO_URI"))
    return _client["rideease"]

def generate_booking_id():
    return "RE" + str(uuid.uuid4().hex[:6]).upper()

def format_datetime(date_str, time_str):
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return dt.strftime("%d %b %Y at %I:%M %p")
    except Exception:
        return f"{date_str} {time_str}"

def save_booking(data: dict) -> dict:
    db = get_db()
    booking = {
        "booking_id": data["booking_id"],
        "trip_type":  data["trip_type"],
        "pickup":     data["pickup"],
        "drop":       data["drop"],
        "date":       data["date"],
        "time":       data["time"],
        "cab_type":   data["cab_type"],
        "name":       data["name"],
        "mobile":     data["mobile"],
        "email":      data.get("email", ""),
        "status":     "confirmed",
        "created_at": datetime.utcnow(),
    }
    db.bookings.insert_one(booking)
    booking.pop("_id", None)
    return booking

def send_sms(mobile: str, message: str) -> dict:
    api_key = os.getenv("FAST2SMS_API_KEY", "")
    if not api_key or api_key == "your_fast2sms_api_key_here":
        return {"success": False, "error": "Fast2SMS API key not configured in .env"}

    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "route":    "q",
        "message":  message,
        "language": "english",
        "flash":    0,
        "numbers":  mobile,
    }
    headers = {
        "authorization": api_key,
        "Content-Type":  "application/json",
    }
    try:
        resp   = requests.post(url, json=payload, headers=headers, timeout=10)
        result = resp.json()
        # This prints the EXACT Fast2SMS response in your VS Code terminal
        print(f"[SMS] To:{mobile} | Chars:{len(message)} | Response:{result}")
        return {"success": result.get("return", False), "raw": result}
    except requests.RequestException as e:
        print(f"[SMS ERROR] {str(e)}")
        return {"success": False, "error": str(e)}

def send_booking_sms(data: dict):
    dt = format_datetime(data["date"], data["time"])

    # SHORT messages under 160 chars — avoids DLT rejection
    customer_msg = (
        f"RideEase: Booking {data['booking_id']} confirmed! "
        f"{data['pickup']} to {data['drop']} on {dt}. "
        f"We will call you shortly."
    )

    owner_msg = (
        f"New Booking {data['booking_id']}! "
        f"{data['name']} {data['mobile']}: "
        f"{data['pickup']} to {data['drop']} "
        f"{data['cab_type']} {dt}."
    )

    print(f"[SMS] Customer msg: {len(customer_msg)} chars")
    print(f"[SMS] Owner msg: {len(owner_msg)} chars")

    customer_result = send_sms(data["mobile"], customer_msg)
    owner_result    = send_sms(os.getenv("OWNER_MOBILE", ""), owner_msg)
    return {"customer": customer_result, "owner": owner_result}

def build_email_html(data: dict) -> str:
    dt = format_datetime(data["date"], data["time"])
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f9f9f9;padding:24px;border-radius:10px;">
      <div style="background:#FF5C00;padding:20px 28px;border-radius:8px 8px 0 0;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:26px;">RideEase</h1>
        <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px;">Booking Confirmation</p>
      </div>
      <div style="background:#fff;padding:28px;border-radius:0 0 8px 8px;border:1px solid #e8e8e8;">
        <p style="font-size:16px;color:#333;">Hi <strong>{data['name']}</strong>,</p>
        <p style="color:#555;font-size:14px;">Your cab booking is <strong style="color:#FF5C00;">confirmed</strong>!</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:14px;">
          <tr style="background:#fff8f5;"><td style="padding:10px 14px;color:#888;border-bottom:1px solid #f0f0f0;width:40%;">Booking ID</td><td style="padding:10px 14px;color:#FF5C00;font-weight:bold;border-bottom:1px solid #f0f0f0;">{data['booking_id']}</td></tr>
          <tr><td style="padding:10px 14px;color:#888;border-bottom:1px solid #f0f0f0;">Trip Type</td><td style="padding:10px 14px;color:#333;border-bottom:1px solid #f0f0f0;">{data['trip_type']}</td></tr>
          <tr style="background:#fff8f5;"><td style="padding:10px 14px;color:#888;border-bottom:1px solid #f0f0f0;">From</td><td style="padding:10px 14px;color:#333;border-bottom:1px solid #f0f0f0;">{data['pickup']}</td></tr>
          <tr><td style="padding:10px 14px;color:#888;border-bottom:1px solid #f0f0f0;">To</td><td style="padding:10px 14px;color:#333;border-bottom:1px solid #f0f0f0;">{data['drop']}</td></tr>
          <tr style="background:#fff8f5;"><td style="padding:10px 14px;color:#888;border-bottom:1px solid #f0f0f0;">Date & Time</td><td style="padding:10px 14px;color:#333;border-bottom:1px solid #f0f0f0;">{dt}</td></tr>
          <tr><td style="padding:10px 14px;color:#888;">Cab Type</td><td style="padding:10px 14px;color:#333;">{data['cab_type']}</td></tr>
        </table>
        <p style="color:#555;font-size:14px;">Our team will call you within <strong>15 minutes</strong>. For help: <strong>1800-123-4567</strong></p>
      </div>
      <p style="text-align:center;color:#bbb;font-size:12px;margin-top:16px;">2025 RideEase</p>
    </div>"""

def send_email(to_address: str, subject: str, html_body: str) -> dict:
    gmail_user     = os.getenv("GMAIL_USER", "")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
    if not gmail_user or gmail_user == "your_gmail_address@gmail.com":
        return {"success": False, "error": "Gmail credentials not set in .env"}
    if not to_address or "@" not in to_address:
        return {"success": False, "error": "Invalid or missing email address"}
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"RideEase Bookings <{gmail_user}>"
    msg["To"]      = to_address
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_address, msg.as_string())
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def send_booking_emails(data: dict) -> dict:
    dt = format_datetime(data["date"], data["time"])
    customer_html    = build_email_html(data)
    customer_subject = f"Booking Confirmed - {data['booking_id']} | RideEase"
    customer_result  = send_email(data.get("email", ""), customer_subject, customer_html)
    admin_html = f"<div style='font-family:Arial;padding:20px;'><h2 style='color:#FF5C00;'>New Booking!</h2><p><b>ID:</b> {data['booking_id']}</p><p><b>Customer:</b> {data['name']} - {data['mobile']}</p><p><b>Route:</b> {data['pickup']} to {data['drop']} ({data['trip_type']})</p><p><b>Cab:</b> {data['cab_type']}</p><p><b>When:</b> {dt}</p></div>"
    admin_subject = f"New Booking: {data['name']} | {data['pickup']} to {data['drop']}"
    admin_result  = send_email(os.getenv("ADMIN_EMAIL", ""), admin_subject, admin_html)
    return {"customer": customer_result, "admin": admin_result}

def send_booking_whatsapp(data: dict) -> dict:
    return {"skipped": "WhatsApp not configured yet"}

def get_all_bookings(limit: int = 100) -> list:
    db     = get_db()
    cursor = db.bookings.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    bookings = []
    for doc in cursor:
        if "created_at" in doc:
            doc["created_at"] = doc["created_at"].strftime("%d %b %Y %I:%M %p")
        bookings.append(doc)
    return bookings
