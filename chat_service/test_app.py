import os
import tempfile
import unittest
from unittest.mock import patch

os.environ["FLASK_SECRET_KEY"] = "test-secret"
os.environ["DATABASE_PATH"] = "/tmp/ics-chat-test.db"

from app import app


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = os.path.join(self.tempdir.name, "test.db")
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_healthz(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_create_rename_send_and_delete_chat(self):
        created = self.client.post("/api/chats")
        self.assertEqual(created.status_code, 201)
        chat_id = created.get_json()["id"]

        renamed = self.client.patch(
            f"/api/chats/{chat_id}",
            json={"title": "Prueba PaaS"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.get_json()["title"], "Prueba PaaS")

        fake_response = unittest.mock.Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {"reply": "Respuesta de prueba"}

        with patch("app.requests.post", return_value=fake_response) as post:
            sent = self.client.post(
                f"/api/chats/{chat_id}/messages",
                json={"text": "Hola"},
            )

        self.assertEqual(sent.status_code, 201)
        self.assertEqual(sent.get_json()["reply"], "Respuesta de prueba")
        post.assert_called_once()

        deleted = self.client.delete(f"/api/chats/{chat_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.get(f"/api/chats/{chat_id}/messages").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
