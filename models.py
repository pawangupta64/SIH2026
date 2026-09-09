from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), default="")
    farm_name = db.Column(db.String(120), default="")
    location = db.Column(db.String(120), default="")
    crop = db.Column(db.String(80), default="")
    # thresholds used to raise alerts
    temp_min = db.Column(db.Float, default=10.0)
    temp_max = db.Column(db.Float, default=38.0)
    moisture_min = db.Column(db.Float, default=30.0)
    moisture_max = db.Column(db.Float, default=80.0)
    humidity_min = db.Column(db.Float, default=25.0)
    humidity_max = db.Column(db.Float, default=85.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    readings = db.relationship("Reading", backref="user", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "farm_name": self.farm_name,
            "location": self.location,
            "crop": self.crop,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "moisture_min": self.moisture_min,
            "moisture_max": self.moisture_max,
            "humidity_min": self.humidity_min,
            "humidity_max": self.humidity_max,
            "created_at": self.created_at.strftime("%d %b %Y"),
        }


class Reading(db.Model):
    """One sensor sample coming from the ESP32 board."""

    __tablename__ = "readings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    device_id = db.Column(db.String(60), default="esp32-1")
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    soil_moisture = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "temperature": round(self.temperature, 1),
            "humidity": round(self.humidity, 1),
            "soil_moisture": round(self.soil_moisture, 1),
            "created_at": self.created_at.isoformat() + "Z",
            "time_label": self.created_at.strftime("%H:%M"),
        }


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(10), nullable=False)  # "user" or "bot"
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Analysis(db.Model):
    """Stored result of a Gemini crop-image analysis."""

    __tablename__ = "analyses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    is_crop = db.Column(db.Boolean, default=True)
    verdict = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
