import unittest
from unittest.mock import patch

import app


class AiApiTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def test_healthz(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_generate_reply_validates_messages(self):
        response = self.client.post("/v1/chat", json={"messages": "invalid"})
        self.assertEqual(response.status_code, 400)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_generate_reply_returns_gemini_text(self):
        upstream = unittest.mock.MagicMock()
        upstream.__enter__.return_value.read.return_value = (
            b'{"candidates":[{"content":{"parts":[{"text":"Hola desde Gemini"}]}}]}'
        )

        with patch("app.urllib.request.urlopen", return_value=upstream):
            response = self.client.post(
                "/v1/chat",
                json={"messages": [{"role": "user", "text": "Hola"}]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "Hola desde Gemini")


if __name__ == "__main__":
    unittest.main()
