"""Private HTTP adapter between the chat container and Gemini."""

import json
import os
import urllib.error
import urllib.request

from flask import Flask, jsonify, request

app = Flask(__name__)
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent"
)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.post("/v1/chat")
def generate_reply():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify(error="Gemini API key is not configured"), 503

    payload = request.get_json(silent=True)
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list) or not messages or len(messages) > 40:
        return jsonify(error="messages must contain between 1 and 40 entries"), 400

    contents = []
    for message in messages:
        if not isinstance(message, dict):
            return jsonify(error="Each message must be an object"), 400
        role = message.get("role")
        text = message.get("text")
        if role not in ("user", "model") or not isinstance(text, str) or not text.strip():
            return jsonify(error="Each message needs a valid role and non-empty text"), 400
        if len(text) > 8000:
            return jsonify(error="A message exceeds the 8000 character limit"), 400
        contents.append({"role": role, "parts": [{"text": text}]})

    body = json.dumps({"contents": contents}).encode("utf-8")
    upstream_request = urllib.request.Request(
        GEMINI_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=90) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        app.logger.warning("Gemini request failed with HTTP %s", error.code)
        return jsonify(error="Gemini rejected the request", upstream_status=error.code), 502
    except (urllib.error.URLError, TimeoutError):
        app.logger.exception("Gemini request could not be completed")
        return jsonify(error="Gemini is unavailable or timed out"), 502
    except (json.JSONDecodeError, KeyError, TypeError):
        app.logger.exception("Gemini returned an invalid response")
        return jsonify(error="Gemini returned an invalid response"), 502

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        app.logger.warning("Gemini response contained no usable candidate")
        return jsonify(error="Gemini returned no response text"), 502
    return jsonify(reply=text)
