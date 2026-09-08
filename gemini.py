"""Thin wrapper around the Google Gemini REST API.

Only two things are needed by the app:
  * analyse_image()  -> crop/leaf/field photo health report (rejects other photos)
  * chat_reply()     -> agriculture-only chatbot answer
"""

import base64
import json
import os

import requests

MODEL = "gemini-3.7-flash"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

CROP_PROMPT = """You are KisanMitra AI, an agriculture crop-health expert for Indian farmers.

Look at the attached photo.

STEP 1 - Decide if the photo actually shows a plant, crop, leaf, fruit, soil or a farm field.
STEP 2 - Reply with ONLY a JSON object, no markdown fences, in this exact shape:

{
  "is_crop": true or false,
  "crop_name": "best guess or Unknown",
  "health_status": "Healthy | Mild stress | Diseased | Severe damage",
  "confidence": "High | Medium | Low",
  "issues": ["short issue 1", "short issue 2"],
  "recommendations": ["clear practical action 1", "action 2", "action 3"],
  "summary": "2-3 sentence plain-language explanation for a farmer"
}

If the photo is NOT a plant/crop/leaf/field/soil (for example a car, house, person, phone,
animal, screenshot), set "is_crop" to false, leave the lists empty and set "summary" to
"This image cannot be analysed. Please upload a photo of a crop, leaf, plant or field."
"""

CHAT_SYSTEM = """You are KisanMitra AI, a friendly farming assistant built by Team CropTech
for Indian farmers. Answer ONLY agriculture-related questions: crops, soil, irrigation,
fertilisers, pests, diseases, weather impact, seeds, harvesting, storage, mandi practices
and government farm schemes.

If the question is not about agriculture, politely reply that you can only help with
farming topics. Keep answers short (under 150 words), practical, and use simple language.
Use the farmer's live field data when it is provided.
"""


class GeminiError(Exception):
    pass


def _api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the server."
        )
    return key


def _call(payload):
    url = ENDPOINT.format(model=MODEL)
    try:
        res = requests.post(
            url,
            params={"key": _api_key()},
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:  # network problem
        raise GeminiError(f"Could not reach Gemini: {exc}") from exc

    if res.status_code != 200:
        raise GeminiError(f"Gemini error {res.status_code}: {res.text[:300]}")

    data = res.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise GeminiError("Gemini returned an empty response.")


def analyse_image(image_bytes: bytes, mime_type: str) -> dict:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": CROP_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }
    text = _call(payload)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = text.strip().strip("`")
        cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
        return json.loads(cleaned)


def chat_reply(question: str, history: list, field_context: str = "") -> str:
    contents = []
    for msg in history[-10:]:
        contents.append(
            {
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}],
            }
        )
    contents.append({"role": "user", "parts": [{"text": question}]})

    system_text = CHAT_SYSTEM
    if field_context:
        system_text += f"\n\nCurrent live field data:\n{field_context}"

    payload = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.6},
    }
    return _call(payload).strip()


def advisory(field_context: str, crop: str) -> str:
    prompt = (
        f"Give a short daily farming advisory for a farmer growing {crop or 'mixed crops'} "
        f"in India, based on this live sensor data:\n{field_context}\n\n"
        "Reply with 3 to 4 short bullet points (start each line with '- '). "
        "Cover irrigation, disease/pest risk and one preventive action. Simple language."
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.5},
    }
    return _call(payload).strip()