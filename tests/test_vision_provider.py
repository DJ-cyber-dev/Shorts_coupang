import base64
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from shorts_studio.core import MediaError
from shorts_studio.providers.settings import ProviderSettings
from shorts_studio.providers.vision import OpenAICompatibleVisionAnalyzer, _jpeg_frames


class FrameParsingTests(unittest.TestCase):
    def test_splits_concatenated_jpegs(self):
        first = b"\xff\xd8frame-a\xff\xd9"
        second = b"\xff\xd8frame-b\xff\xd9"
        self.assertEqual(_jpeg_frames(first + second), [first, second])

    def test_rejects_truncated_jpeg(self):
        with self.assertRaises(MediaError):
            _jpeg_frames(b"\xff\xd8incomplete")


class VisionAdapterTests(unittest.TestCase):
    def test_sends_bounded_frame_samples_and_parses_json(self):
        settings = ProviderSettings("openai-compatible", "vision-model", "https://api.example/v1")
        frame = b"\xff\xd8jpeg-sample\xff\xd9"
        reply = {"choices": [{"message": {"content": json.dumps({
            "summary": "손으로 제품을 보여줌", "scenes": [{"timestamp_sec": 0.0}],
            "shorts_hooks": [], "product_keywords": [],
        }, ensure_ascii=False)}}]}
        encoded_result = reply["choices"][0]["message"]["content"]
        with patch.object(ProviderSettings, "get_secret", return_value="test-secret"):
            analyzer = OpenAICompatibleVisionAnalyzer(settings, ffmpeg="ffmpeg")
        with patch.object(Path, "is_file", return_value=True), \
             patch("shorts_studio.providers.vision.Engine") as engine_cls, \
             patch("shorts_studio.providers.vision.sample_frames", return_value=[(0.0, frame), (2.0, frame)]), \
             patch.object(analyzer.client, "complete", return_value=encoded_result) as completion:
            engine_cls.return_value.probe.return_value = {"duration": 4.0}
            result = analyzer.analyze(Path("sample.mp4"))
        messages = completion.call_args.args[0]
        image_part = messages[0]["content"][1]
        self.assertEqual(base64.b64decode(image_part["image_url"]["url"].split(",", 1)[1]), frame)
        self.assertIn("timestamp_sec", messages[0]["content"][0]["text"])
        self.assertEqual(result["summary"], "손으로 제품을 보여줌")
        self.assertEqual(result["meta"]["sampled_frames"], 2)

    def test_requires_enabled_provider_and_secret(self):
        with self.assertRaises(MediaError):
            OpenAICompatibleVisionAnalyzer(ProviderSettings())
        settings = ProviderSettings("openai-compatible", "vision-model", "https://api.example/v1")
        with patch.object(ProviderSettings, "get_secret", return_value=None), self.assertRaisesRegex(MediaError, "API key"):
            OpenAICompatibleVisionAnalyzer(settings)


if __name__ == "__main__":
    unittest.main()
