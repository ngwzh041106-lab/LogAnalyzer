import json
import unittest
from unittest.mock import patch, MagicMock
from app.services.llm_client import LLMClient, LLMError


class ClientTests(unittest.TestCase):
    def client(self, provider="ollama"):
        return LLMClient("https://example.test/v1/", "test-model", 0.2,
                         "system", "{log_text}", "test", "secret", provider)

    def reply(self, value):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(value).encode()
        return response

    @patch("app.services.llm_client.urlopen")
    def test_external_api(self, open_url):
        open_url.return_value = self.reply({"choices": [{"message": {"content": '{"summary":"ok"}'}}]})
        client = self.client("openai")
        self.assertEqual(client.summarize("log")["summary"], "ok")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        payload = json.loads(request.data)
        self.assertNotIn("options", payload)
        self.assertNotIn("think", payload)
        self.assertNotIn("secret", client.last_raw_input)

    @patch("app.services.llm_client.urlopen")
    def test_ollama_default(self, open_url):
        open_url.return_value = self.reply({"message": {"content": '{"summary":"ok"}'}})
        self.assertEqual(self.client().summarize("log")["summary"], "ok")
        request = open_url.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/api/chat"))
        self.assertEqual(json.loads(request.data)["format"], "json")

    @patch("app.services.llm_client.urlopen")
    def test_invalid_envelope(self, open_url):
        open_url.return_value = self.reply({"choices": []})
        with self.assertRaises(LLMError):
            self.client("openai").summarize("log")

    @patch("app.services.llm_client.urlopen")
    def test_invalid_json(self, open_url):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"not json"
        open_url.return_value = response
        with self.assertRaises(LLMError):
            self.client("openai").summarize("log")

    @patch("app.services.llm_client.urlopen")
    def test_timeout_setting_and_message(self, open_url):
        client = self.client("openai")
        client.timeout_seconds = 600
        open_url.side_effect = TimeoutError("read timed out")
        with self.assertRaisesRegex(LLMError, "600"):
            client.summarize("log")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 600)
        self.assertEqual(open_url.call_count, 1)

    @patch("app.services.llm_client.urlopen")
    def test_wrapped_timeout(self, open_url):
        from urllib.error import URLError
        open_url.side_effect = URLError(TimeoutError("timed out"))
        with self.assertRaisesRegex(LLMError, "逾時"):
            self.client().summarize("log")
