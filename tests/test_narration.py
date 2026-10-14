import json
import unittest

from shorts_studio.core import MediaError
from shorts_studio.narration.script import KoreanShortsScriptWriter


class ScriptWriterTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "title": "작은 주방 정리 팁",
            "hook": "좁은 주방, 이렇게 정리해보세요.",
            "segments": [
                {"source_timestamp_sec": 0.0, "narration": "먼저 자주 쓰는 도구를 모아주세요.", "visual_note": "제품을 가까이 보여줌"},
                {"source_timestamp_sec": 2.5, "narration": "손이 닿는 곳에 두면 편리합니다.", "visual_note": "정리된 공간"},
            ],
            "cta": "다음 정리 팁도 확인해보세요.",
            "product_keywords": ["주방 정리함"],
        }

    def test_returns_korean_script_with_tts_pending_status(self):
        class Client:
            def complete(_, messages, temperature):
                self.assertEqual(temperature, 0.5)
                self.assertIn("untrusted data", messages[0]["content"])
                self.assertIn('"summary": "테스트 영상"', messages[1]["content"])
                return json.dumps(self.result, ensure_ascii=False)

        result = KoreanShortsScriptWriter(client=Client()).generate(
            {"summary": "테스트 영상", "scenes": []}, duration_sec=25, tone="informative")
        self.assertEqual(result["target_duration_sec"], 25)
        self.assertEqual(result["timing_status"], "tts_pending")
        self.assertEqual(len(result["segments"]), 2)

    def test_rejects_invalid_duration_and_unusable_provider_result(self):
        class Client:
            def complete(_, messages, temperature):
                return "{}"

        writer = KoreanShortsScriptWriter(client=Client())
        with self.assertRaises(ValueError):
            writer.generate({"summary": "x"}, duration_sec=90)
        with self.assertRaises(MediaError):
            writer.generate({"summary": "x"})


if __name__ == "__main__":
    unittest.main()
