import json
import unittest
from unittest.mock import MagicMock, patch

from shorts_studio.core import MediaError
from shorts_studio.providers.openai_compatible import OpenAICompatibleClient
from shorts_studio.providers.settings import ProviderSettings


class ChatClientTests(unittest.TestCase):
    def setUp(self):
        self.settings = ProviderSettings("openai-compatible", "model", "https://api.example/v1")

    def test_posts_chat_completion_and_returns_text(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
        messages = [{"role": "user", "content": "hello"}]
        with patch.object(ProviderSettings, "get_secret", return_value="secret-value"), \
             patch("shorts_studio.providers.openai_compatible.urlopen", return_value=response) as call:
            client = OpenAICompatibleClient(self.settings)
            self.assertEqual(client.complete(messages), "ok")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-value")
        self.assertEqual(json.loads(request.data)["messages"], messages)

    def test_http_error_does_not_expose_provider_response(self):
        from urllib.error import HTTPError
        error = HTTPError("https://api.example", 401, "bad", {}, None)
        with patch.object(ProviderSettings, "get_secret", return_value="secret-value"), \
             patch("shorts_studio.providers.openai_compatible.urlopen", side_effect=error):
            client = OpenAICompatibleClient(self.settings)
            with self.assertRaisesRegex(MediaError, "HTTP 401") as caught:
                client.complete([{"role": "user", "content": "hello"}])
            self.assertNotIn("secret-value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
