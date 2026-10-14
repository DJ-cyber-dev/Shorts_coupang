import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

from shorts_studio.core import MediaError
from shorts_studio.providers.gemini import MODEL_OPTIONS, GeminiScriptClient, GeminiScriptSettings


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.payload


class GeminiScriptTests(unittest.TestCase):
    def test_model_options_only_include_current_stable_api_models(self):
        self.assertEqual(
            [option["id"] for option in MODEL_OPTIONS],
            ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        )

    def test_settings_round_trip_contains_no_secret(self):
        folder = Path(__file__).resolve().parents[1] / "build" / f"_gemini-settings-test-{uuid4().hex}"
        folder.mkdir(parents=True)
        path = folder / "script-ai.json"
        try:
            settings = GeminiScriptSettings("gemini-3.8-flash", "SHORTS_GEMINI_API_KEY")
            settings.save(path)
            self.assertEqual(GeminiScriptSettings.load(path), settings)
            self.assertNotIn("secret", path.read_text(encoding="utf-8").lower())
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)
            folder.rmdir()

    def test_native_api_header_payload_and_response_parsing(self):
        captured = {}
        response = {"candidates": [{"content": {"parts": [{"text": '{"title":"테스트"}'}]}}]}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["key"] = request.get_header("X-goog-api-key")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(json.dumps(response, ensure_ascii=False).encode("utf-8"))

        with patch.object(GeminiScriptSettings, "get_secret", return_value="test-secret"):
            client = GeminiScriptClient(GeminiScriptSettings(), opener=opener)
            output = client.complete([
                {"role": "system", "content": "JSON only"},
                {"role": "user", "content": "대본을 작성해"},
            ])

        self.assertEqual(output, '{"title":"테스트"}')
        self.assertEqual(captured["key"], "test-secret")
        self.assertNotIn("test-secret", captured["url"])
        self.assertTrue(captured["url"].endswith("/gemini-3.8-flash:generateContent"))
        self.assertEqual(captured["body"]["systemInstruction"]["parts"][0]["text"], "JSON only")
        self.assertEqual(captured["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(captured["body"]["contents"][0]["parts"][0]["text"], "대본을 작성해")

    def test_connection_check_and_quota_error(self):
        response = {"candidates": [{"content": {"parts": [{"text": '{"status":"ok"}'}]}}]}
        with patch.object(GeminiScriptSettings, "get_secret", return_value="secret"):
            client = GeminiScriptClient(GeminiScriptSettings(), opener=lambda *_args, **_kwargs:
                                        FakeResponse(json.dumps(response).encode()))
            client.test_connection()

        def quota(*_args, **_kwargs):
            raise HTTPError("https://generativelanguage.googleapis.com", 429, "quota", {}, None)

        with patch.object(GeminiScriptSettings, "get_secret", return_value="secret"):
            client = GeminiScriptClient(GeminiScriptSettings(), opener=quota)
            with self.assertRaisesRegex(MediaError, "사용량 제한"):
                client.complete([{"role": "user", "content": "test"}])

    def test_retries_transient_503_with_exponential_backoff(self):
        response = {"candidates": [{"content": {"parts": [{"text": '{"status":"ok"}'}]}}]}
        failures = 0
        delays = []

        def opener(*_args, **_kwargs):
            nonlocal failures
            failures += 1
            if failures < 3:
                raise HTTPError("https://generativelanguage.googleapis.com", 503, "unavailable", {}, None)
            return FakeResponse(json.dumps(response).encode())

        with patch.object(GeminiScriptSettings, "get_secret", return_value="secret"):
            client = GeminiScriptClient(GeminiScriptSettings(), opener=opener, sleep_fn=delays.append)
            client.test_connection()

        self.assertEqual(failures, 3)
        self.assertEqual(delays, [1, 2])

    def test_exhausted_503_retries_returns_actionable_error(self):
        def unavailable(*_args, **_kwargs):
            raise HTTPError("https://generativelanguage.googleapis.com", 503, "unavailable", {}, None)

        delays = []
        with patch.object(GeminiScriptSettings, "get_secret", return_value="secret"):
            client = GeminiScriptClient(GeminiScriptSettings(), opener=unavailable, sleep_fn=delays.append)
            with self.assertRaisesRegex(MediaError, "HTTP 503.*잠시 후 다시 시도"):
                client.complete([{"role": "user", "content": "test"}])

        self.assertEqual(delays, [1, 2, 4])

    def test_invalid_model_is_rejected(self):
        with self.assertRaises(ValueError):
            GeminiScriptSettings("gemini model", "SHORTS_GEMINI_API_KEY").validate()


if __name__ == "__main__":
    unittest.main()
