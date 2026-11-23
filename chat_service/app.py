"""Web chat with browser-scoped sessions and SQLite persistence."""

import os
import secrets
import sqlite3
from datetime import timedelta

import requests
from flask import Flask, g, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be configured")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(days=365),
)

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/chats.db")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ia:8000").rstrip("/")


def get_db():
    """Open one connection per request and create the schema on first use."""
    if "db" not in g:
        os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
        g.db = sqlite3.connect(DATABASE_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'model')),
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS messages_chat_id_id
                ON messages(chat_id, id);
            """
        )
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def owner_id():
    # A persistent signed cookie lets the same browser resume its chats later.
    session.permanent = True
    if "owner_id" not in session:
        session["owner_id"] = secrets.token_urlsafe(24)
    return session["owner_id"]


def owned_chat(chat_id):
    return get_db().execute(
        "SELECT id, title FROM chats WHERE id = ? AND owner_id = ?",
        (chat_id, owner_id()),
    ).fetchone()


@app.get("/healthz")
def healthz():
    get_db().execute("SELECT 1")
    return jsonify(status="ok")


@app.get("/")
def index():
    owner_id()
    return render_template("index.html")


@app.get("/api/chats")
def list_chats():
    rows = get_db().execute(
        "SELECT id, title, created_at FROM chats WHERE owner_id = ? ORDER BY id DESC",
        (owner_id(),),
    ).fetchall()
    return jsonify(chats=[dict(row) for row in rows])


@app.post("/api/chats")
def create_chat():
    db = get_db()
    cursor = db.execute(
        "INSERT INTO chats (owner_id, title) VALUES (?, ?)",
        (owner_id(), "Nuevo chat"),
    )
    db.commit()
    return jsonify(id=cursor.lastrowid, title="Nuevo chat"), 201


@app.patch("/api/chats/<int:chat_id>")
def rename_chat(chat_id):
    if not owned_chat(chat_id):
        return jsonify(error="Chat not found"), 404
    payload = request.get_json(silent=True)
    title = payload.get("title", "").strip() if isinstance(payload, dict) else ""
    if not title or len(title) > 100:
        return jsonify(error="Title must contain between 1 and 100 characters"), 400
    get_db().execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
    get_db().commit()
    return jsonify(id=chat_id, title=title)


@app.delete("/api/chats/<int:chat_id>")
def delete_chat(chat_id):
    if not owned_chat(chat_id):
        return jsonify(error="Chat not found"), 404
    db = get_db()
    db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    db.commit()
    return "", 204


@app.get("/api/chats/<int:chat_id>/messages")
def list_messages(chat_id):
    if not owned_chat(chat_id):
        return jsonify(error="Chat not found"), 404
    rows = get_db().execute(
        "SELECT id, role, text, created_at FROM messages WHERE chat_id = ? ORDER BY id",
        (chat_id,),
    ).fetchall()
    return jsonify(messages=[dict(row) for row in rows])


@app.post("/api/chats/<int:chat_id>/messages")
def send_message(chat_id):
    if not owned_chat(chat_id):
        return jsonify(error="Chat not found"), 404
    payload = request.get_json(silent=True)
    text = payload.get("text", "").strip() if isinstance(payload, dict) else ""
    if not text or len(text) > 8000:
        return jsonify(error="Message must contain between 1 and 8000 characters"), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO messages (chat_id, role, text) VALUES (?, 'user', ?)",
        (chat_id, text),
    )
    user_message_id = cursor.lastrowid
    history = db.execute(
        "SELECT role, text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 40",
        (chat_id,),
    ).fetchall()
    messages = [
        {"role": row["role"], "text": row["text"]}
        for row in reversed(history)
    ]

    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/v1/chat",
            json={"messages": messages},
            timeout=100,
        )
        response.raise_for_status()
        reply = response.json()["reply"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("AI service returned an empty reply")
    except (requests.RequestException, ValueError, KeyError) as error:
        db.execute("DELETE FROM messages WHERE id = ?", (user_message_id,))
        db.commit()
        app.logger.warning("AI service request failed: %s", error)
        return jsonify(error="No se pudo obtener respuesta del servicio de IA"), 502

    db.execute(
        "INSERT INTO messages (chat_id, role, text) VALUES (?, 'model', ?)",
        (chat_id, reply.strip()),
    )
    db.commit()
    return jsonify(reply=reply.strip()), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
