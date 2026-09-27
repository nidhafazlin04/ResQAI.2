import os
import json
import uuid
import socket
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from gtts import gTTS
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from twilio.rest import Client as TwilioClient
except Exception:
    TwilioClient = None

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None


alerts = []
pending_queue = []

SYSTEM_PROMPT = """
You are an Emergency Message Triage Assistant.
Analyze an emergency report and classify its urgency.

Priority levels:
CRITICAL:
Immediate threat to life or serious danger.
Examples: active fire, person trapped, unconscious person,
severe bleeding, drowning, explosion, immediate violent threat.

HIGH:
Serious situation requiring prompt response but immediate
life-threatening danger is not clearly established.

MEDIUM:
Important situation requiring attention but not apparently
immediately dangerous.

LOW:
Non-urgent request or informational message.

Emergency types:
FIRE
MEDICAL
ACCIDENT
VIOLENCE
NATURAL_DISASTER
OTHER
NONE

Rules:
1. Do not diagnose medical conditions.
2. Do not invent facts.
3. Use only information contained in the message.
4. If ambiguous, mention uncertainty.
5. Never downgrade because information is missing.
6. CRITICAL situations should be escalated to a human rescue operator.
7. Return ONLY valid JSON.

Required JSON:
{
  "priority": "CRITICAL/HIGH/MEDIUM/LOW",
  "emergency_type": "FIRE/MEDICAL/ACCIDENT/VIOLENCE/NATURAL_DISASTER/OTHER/NONE",
  "reason": "short explanation",
  "recommended_action": "short general action",
  "confidence": "HIGH/MEDIUM/LOW"
}
"""

CRITICAL_TERMS = [
    "trapped", "unconscious", "not breathing", "fire", "explosion",
    "drowning", "severe bleeding", "gunshot", "collapsed",
    "heart attack", "stroke"
]
URGENT_TERMS = [
    "bleeding", "injured", "broken", "flooded", "stranded",
    "pregnant", "labour", "missing"
]

def keyword_fallback_triage(message):
    low = message.lower()
    if any(t in low for t in CRITICAL_TERMS):
        return {
            "priority": "CRITICAL",
            "emergency_type": "OTHER",
            "reason": "Keyword fallback: critical term detected while the AI service was unavailable.",
            "recommended_action": "Escalate immediately to a human responder.",
            "confidence": "LOW"
        }
    if any(t in low for t in URGENT_TERMS):
        return {
            "priority": "HIGH",
            "emergency_type": "OTHER",
            "reason": "Keyword fallback: urgent term detected while the AI service was unavailable.",
            "recommended_action": "Route to a human responder for review.",
            "confidence": "LOW"
        }
    return {
        "priority": "MEDIUM",
        "emergency_type": "OTHER",
        "reason": "AI service unavailable; message needs human review.",
        "recommended_action": "Escalate to a human responder.",
        "confidence": "LOW"
    }

def ai_triage(message):
    if not message or not message.strip():
        return {
            "priority": "LOW",
            "emergency_type": "NONE",
            "reason": "No emergency message was provided.",
            "recommended_action": "Ask the user to provide an emergency message.",
            "confidence": "HIGH"
        }

    if client is None:
        return keyword_fallback_triage(message)

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ]
        )
        result = response.choices[0].message.content.strip()
        result = result.replace("```json", "").replace("```", "").strip()
        data = json.loads(result)

        # Basic validation before trusting model output.
        allowed_priority = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        allowed_type = {
            "FIRE", "MEDICAL", "ACCIDENT", "VIOLENCE",
            "NATURAL_DISASTER", "OTHER", "NONE"
        }
        if data.get("priority") not in allowed_priority:
            raise ValueError("Invalid priority")
        if data.get("emergency_type") not in allowed_type:
            raise ValueError("Invalid emergency type")

        return data
    except Exception as e:
        print("AI error:", e)
        return keyword_fallback_triage(message)

def internet_available(timeout=2.0):
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("8.8.8.8", 53))
        s.close()
        return True
    except OSError:
        return False

def generate_alert_id():
    return "EMG-" + str(uuid.uuid4())[:8].upper()

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def find_incident(new_alert, existing_alerts, text_threshold=0.35, distance_km=0.5):
    if not existing_alerts:
        return None

    texts = [a["message"] for a in existing_alerts] + [new_alert["message"]]
    X = TfidfVectorizer(stop_words="english").fit_transform(texts)
    sims = cosine_similarity(X[-1], X[:-1])[0]

    for i, old in enumerate(existing_alerts):
        close = haversine_km(
            new_alert["latitude"], new_alert["longitude"],
            old["latitude"], old["longitude"]
        ) <= distance_km
        if sims[i] >= text_threshold and close:
            return old["incident_id"]

    return None

def create_alert(message, latitude, longitude):
    analysis = ai_triage(message)
    alert_id = generate_alert_id()

    matched = find_incident(
        {"latitude": latitude, "longitude": longitude, "message": message},
        alerts
    )

    return {
        "alert_id": alert_id,
        "incident_id": matched if matched else alert_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "priority": analysis["priority"],
        "emergency_type": analysis["emergency_type"],
        "reason": analysis["reason"],
        "recommended_action": analysis["recommended_action"],
        "confidence": analysis["confidence"],
        "latitude": latitude,
        "longitude": longitude,
        "communication": "PENDING",
        "status": "CREATED"
    }

def generate_sms(alert):
    return (
        "RESQAI EMERGENCY ALERT\n"
        f"ID: {alert['alert_id']}\n"
        f"PRIORITY: {alert['priority']}\n"
        f"TYPE: {alert['emergency_type']}\n"
        f"MESSAGE: {alert['message']}\n"
        f"LOCATION: {alert['latitude']}, {alert['longitude']}"
    )

def send_via_twilio(alert):
    if not TwilioClient:
        return False

    sid = os.getenv("TWILIO_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("RESPONDER_PHONE_NUMBER")

    if not all([sid, token, from_number, to_number]):
        return False

    try:
        tw_client = TwilioClient(sid, token)
        tw_client.messages.create(
            body=generate_sms(alert),
            from_=from_number,
            to=to_number
        )
        return True
    except Exception as e:
        print("Twilio error:", e)
        return False

def send_sms_fallback(alert):
    sent = send_via_twilio(alert)
    pending_queue.append(alert["alert_id"])
    print("SMS:", generate_sms(alert))
    return "SMS" if sent else "SMS-SIMULATED"

def send_internet_alert(alert):
    # Replace this function later with a real responder dashboard push,
    # email, webhook, or notification provider.
    print("INTERNET ALERT:", alert)
    return "INTERNET"

def dispatch_alert(alert):
    if internet_available():
        channel = send_internet_alert(alert)
    else:
        channel = send_sms_fallback(alert)

    alert["communication"] = channel
    return channel

def create_responder_voice(alert):
    voice_message = (
        f"Emergency alert. Priority {alert['priority']}. "
        f"Emergency type {alert['emergency_type']}. "
        f"{alert['reason']} "
        f"Recommended action: {alert['recommended_action']}. "
        f"Location latitude {alert['latitude']}, "
        f"longitude {alert['longitude']}. "
        f"Alert ID {alert['alert_id']}. "
        "Rescue team response is required."
    )

    filename = AUDIO_DIR / f"{alert['alert_id']}_responder_warning.mp3"
    gTTS(text=voice_message, lang="en", slow=False).save(filename)
    return f"/static/audio/{filename.name}"

def get_history():
    return [
        {
            "alert_id": a["alert_id"],
            "incident_id": a["incident_id"],
            "timestamp": a["timestamp"],
            "priority": a["priority"],
            "emergency_type": a["emergency_type"],
            "message": a["message"],
            "latitude": a["latitude"],
            "longitude": a["longitude"],
            "communication": a["communication"],
            "status": a["status"]
        }
        for a in reversed(alerts)
    ]

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/manifest.json")
def manifest():
    return send_from_directory(BASE_DIR / "static", "manifest.json")

@app.get("/sw.js")
def service_worker():
    return send_from_directory(BASE_DIR / "static", "sw.js", mimetype="application/javascript")

@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "internet": internet_available(),
        "alerts": len(alerts)
    })

@app.get("/api/history")
def history():
    return jsonify(get_history())

@app.post("/api/triage")
def triage():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Emergency message is required."}), 400

    return jsonify(ai_triage(message))

    audio = request.files.get("audio")

    if audio:
        audio_path = BASE_DIR / "static" / f"input_{uuid.uuid4().hex}.webm"
        audio.save(audio_path)
        try:
            spoken = voice_to_text(str(audio_path))
            message = f"{message} {spoken}".strip() if message else spoken
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

@app.post("/api/acknowledge")
def acknowledge():
    if not alerts:
        return jsonify({"error": "No alerts available."}), 404

    alerts[-1]["status"] = "ACKNOWLEDGED"
    return jsonify(alerts[-1])

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
