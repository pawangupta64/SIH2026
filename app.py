import os
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

import gemini
from models import Analysis, ChatMessage, Reading, User, db

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "kisanmitra.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB uploads

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to open your dashboard."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        farm_name = request.form.get("farm_name", "").strip()
        location = request.form.get("location", "").strip()
        crop = request.form.get("crop", "").strip()

        if not name or not email or len(password) < 6:
            flash("Please fill every field. Password must be at least 6 characters.", "error")
            return render_template("signup.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists. Please log in.", "error")
            return redirect(url_for("login"))

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            farm_name=farm_name,
            location=location,
            crop=crop,
        )
        db.session.add(user)
        db.session.commit()
        seed_demo_readings(user.id)
        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Wrong email or password.", "error")
            return render_template("login.html")
        login_user(user, remember=True)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("landing"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


# --------------------------------------------------------------------------
# Sensor data API
# --------------------------------------------------------------------------
@app.post("/api/ingest")
def ingest():
    """Endpoint the ESP32 board posts to.

    POST JSON: {"email": "...", "temperature": 29.4, "humidity": 61, "soil_moisture": 42}
    Header:    X-Device-Key: <DEVICE_API_KEY from .env>
    """
    expected = os.environ.get("DEVICE_API_KEY", "kisanmitra-device-key")
    if request.headers.get("X-Device-Key") != expected:
        return jsonify({"error": "invalid device key"}), 401

    body = request.get_json(silent=True) or {}
    user = User.query.filter_by(email=str(body.get("email", "")).strip().lower()).first()
    if not user:
        return jsonify({"error": "unknown user email"}), 404

    try:
        reading = Reading(
            user_id=user.id,
            device_id=str(body.get("device_id", "esp32-1"))[:60],
            temperature=float(body["temperature"]),
            humidity=float(body["humidity"]),
            soil_moisture=float(body["soil_moisture"]),
        )
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "temperature, humidity and soil_moisture are required"}), 400

    db.session.add(reading)
    db.session.commit()
    return jsonify({"ok": True, "reading": reading.to_dict()}), 201


@app.get("/api/readings")
@login_required
def readings():
    limit = min(int(request.args.get("limit", 40)), 200)
    rows = (
        Reading.query.filter_by(user_id=current_user.id)
        .order_by(Reading.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return jsonify({"readings": [r.to_dict() for r in rows], "alerts": build_alerts(rows)})


@app.get("/api/analytics")
@login_required
def analytics():
    since = datetime.utcnow() - timedelta(days=7)
    rows = (
        Reading.query.filter(Reading.user_id == current_user.id, Reading.created_at >= since)
        .order_by(Reading.created_at.asc())
        .all()
    )
    buckets = {}
    for r in rows:
        key = r.created_at.strftime("%d %b")
        b = buckets.setdefault(key, {"t": [], "h": [], "m": []})
        b["t"].append(r.temperature)
        b["h"].append(r.humidity)
        b["m"].append(r.soil_moisture)

    def avg(v):
        return round(sum(v) / len(v), 1) if v else 0

    return jsonify(
        {
            "labels": list(buckets.keys()),
            "temperature": [avg(b["t"]) for b in buckets.values()],
            "humidity": [avg(b["h"]) for b in buckets.values()],
            "soil_moisture": [avg(b["m"]) for b in buckets.values()],
            "total_readings": len(rows),
        }
    )


@app.post("/api/simulate")
@login_required
def simulate():
    """Adds one fresh random reading — handy for demos without the board."""
    last = (
        Reading.query.filter_by(user_id=current_user.id)
        .order_by(Reading.created_at.desc())
        .first()
    )
    base_t = last.temperature if last else 28
    base_h = last.humidity if last else 60
    base_m = last.soil_moisture if last else 45
    reading = Reading(
        user_id=current_user.id,
        device_id="simulator",
        temperature=round(min(45, max(8, base_t + random.uniform(-1.5, 1.5))), 1),
        humidity=round(min(98, max(15, base_h + random.uniform(-3, 3))), 1),
        soil_moisture=round(min(95, max(5, base_m + random.uniform(-4, 4))), 1),
    )
    db.session.add(reading)
    db.session.commit()
    return jsonify({"ok": True, "reading": reading.to_dict()})


# --------------------------------------------------------------------------
# AI endpoints
# --------------------------------------------------------------------------
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


@app.post("/api/analyse")
@login_required
def analyse():
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "Please choose an image first."}), 400
    if file.mimetype not in ALLOWED_IMAGE_TYPES:
        return jsonify({"error": "Only JPG, PNG or WEBP images are supported."}), 400

    data = file.read()
    if not data:
        return jsonify({"error": "That file looks empty."}), 400

    try:
        result = gemini.analyse_image(data, file.mimetype)
    except gemini.GeminiError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception:
        return jsonify({"error": "The AI could not read that image. Please try again."}), 502

    db.session.add(
        Analysis(
            user_id=current_user.id,
            filename=file.filename[:255],
            is_crop=bool(result.get("is_crop")),
            verdict=result.get("summary", "")[:2000],
        )
    )
    db.session.commit()
    return jsonify(result)


@app.post("/api/chat")
@login_required
def chat():
    question = (request.get_json(silent=True) or {}).get("message", "").strip()
    if not question:
        return jsonify({"error": "Type a question first."}), 400

    history = [
        {"role": m.role, "content": m.content}
        for m in ChatMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(20)
        .all()
    ]

    try:
        answer = gemini.chat_reply(question, history, field_context())
    except gemini.GeminiError as exc:
        return jsonify({"error": str(exc)}), 502

    db.session.add(ChatMessage(user_id=current_user.id, role="user", content=question))
    db.session.add(ChatMessage(user_id=current_user.id, role="bot", content=answer))
    db.session.commit()
    return jsonify({"reply": answer})


@app.get("/api/chat/history")
@login_required
def chat_history():
    msgs = (
        ChatMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(50)
        .all()
    )
    return jsonify({"messages": [{"role": m.role, "content": m.content} for m in msgs]})


@app.get("/api/advisory")
@login_required
def get_advisory():
    try:
        text = gemini.advisory(field_context(), current_user.crop)
    except gemini.GeminiError as exc:
        return jsonify({"error": str(exc)}), 502
    points = [line.lstrip("-• ").strip() for line in text.splitlines() if line.strip()]
    return jsonify({"points": points[:6]})


# --------------------------------------------------------------------------
# Profile & settings
# --------------------------------------------------------------------------
@app.post("/api/profile")
@login_required
def update_profile():
    body = request.get_json(silent=True) or {}
    for field in ("name", "phone", "farm_name", "location", "crop"):
        if field in body:
            setattr(current_user, field, str(body[field])[:120])
    db.session.commit()
    return jsonify({"ok": True, "user": current_user.to_dict()})


@app.post("/api/settings")
@login_required
def update_settings():
    body = request.get_json(silent=True) or {}
    for field in (
        "temp_min",
        "temp_max",
        "moisture_min",
        "moisture_max",
        "humidity_min",
        "humidity_max",
    ):
        if field in body:
            try:
                setattr(current_user, field, float(body[field]))
            except (TypeError, ValueError):
                pass
    db.session.commit()
    return jsonify({"ok": True, "user": current_user.to_dict()})


@app.get("/api/me")
@login_required
def me():
    return jsonify(current_user.to_dict())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def field_context():
    last = (
        Reading.query.filter_by(user_id=current_user.id)
        .order_by(Reading.created_at.desc())
        .first()
    )
    if not last:
        return "No sensor readings yet."
    return (
        f"Temperature {last.temperature} C, humidity {last.humidity} %, "
        f"soil moisture {last.soil_moisture} %. Crop: {current_user.crop or 'unknown'}. "
        f"Location: {current_user.location or 'India'}."
    )


def build_alerts(rows):
    if not rows:
        return []
    last = rows[-1]
    u = current_user
    alerts = []

    def check(value, low, high, label, unit, low_msg, high_msg):
        if value < low:
            alerts.append({"level": "warning", "title": f"Low {label}", "message": low_msg,
                           "value": f"{value}{unit}"})
        elif value > high:
            alerts.append({"level": "danger", "title": f"High {label}", "message": high_msg,
                           "value": f"{value}{unit}"})

    check(last.soil_moisture, u.moisture_min, u.moisture_max, "soil moisture", "%",
          "Soil is drying out. Irrigate the field soon.",
          "Soil is water-logged. Pause irrigation and check drainage.")
    check(last.temperature, u.temp_min, u.temp_max, "temperature", "°C",
          "Cold stress possible. Consider covering young plants.",
          "Heat stress risk. Irrigate early morning or late evening.")
    check(last.humidity, u.humidity_min, u.humidity_max, "humidity", "%",
          "Dry air increases water loss from leaves.",
          "High humidity raises fungal disease risk. Watch for leaf spots.")

    if not alerts:
        alerts.append({"level": "ok", "title": "Field is healthy",
                       "message": "All sensor values are inside your safe range.", "value": "OK"})
    return alerts


def seed_demo_readings(user_id, hours=48):
    """Fills the graphs with believable data so a new account is never empty."""
    now = datetime.utcnow()
    temp, hum, moist = 27.0, 62.0, 48.0
    for i in range(hours, 0, -1):
        temp = min(41, max(14, temp + random.uniform(-1.2, 1.2)))
        hum = min(95, max(20, hum + random.uniform(-2.5, 2.5)))
        moist = min(90, max(12, moist + random.uniform(-2.5, 2.2)))
        db.session.add(
            Reading(
                user_id=user_id,
                device_id="demo",
                temperature=round(temp, 1),
                humidity=round(hum, 1),
                soil_moisture=round(moist, 1),
                created_at=now - timedelta(hours=i),
            )
        )
    db.session.commit()


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
