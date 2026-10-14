import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from shorts_studio.core import MediaError
from shorts_studio.sourcing.settings import YouTubeSearchSettings
from shorts_studio.sourcing.youtube_search import YouTubeSourceSearch


class YouTubeSourceSearchTests(unittest.TestCase):
    def test_requests_cc_short_videos_and_validates_result_ids(self):
        settings = YouTubeSearchSettings()
        payload = {"items": [
            {"id": {"videoId": "BaW_jenozKc"}, "snippet": {
                "title": "테스트 영상", "channelTitle": "채널", "publishedAt": "2026-01-01T00:00:00Z",
                "thumbnails": {"medium": {"url": "https://img.youtube.com/1.jpg"}}}},
            {"id": {"videoId": "bad"}, "snippet": {"title": "잘못된 id"}},
        ]}
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload, ensure_ascii=False).encode()
        with patch.object(YouTubeSearchSettings, "get_secret", return_value="test-api-key"), \
             patch("shorts_studio.sourcing.youtube_search.urlopen", return_value=response) as call:
            results = YouTubeSourceSearch(settings).search("주방 정리", limit=7)
        request = call.call_args.args[0]
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(params["videoLicense"], ["creativeCommon"])
        self.assertEqual(params["videoDuration"], ["short"])
        self.assertEqual(params["maxResults"], ["7"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].license, "creativeCommon")
        self.assertEqual(results[0].url, "https://www.youtube.com/watch?v=BaW_jenozKc")
        self.assertNotIn("test-api-key", str(results))

    def test_requires_api_key_and_limits_queries(self):
        with patch.object(YouTubeSearchSettings, "get_secret", return_value=None), self.assertRaises(MediaError):
            YouTubeSourceSearch(YouTubeSearchSettings())
        settings = YouTubeSearchSettings()
        with patch.object(YouTubeSearchSettings, "get_secret", return_value="key"):
            search = YouTubeSourceSearch(settings)
        with self.assertRaises(ValueError):
            search.search("   ")
        with self.assertRaises(ValueError):
            search.search("valid", limit=50)

    def test_settings_key_name_round_trip_without_secret(self):
        path = Path(__file__).with_name(f".youtube-settings-{os.getpid()}.toml")
        try:
            settings = YouTubeSearchSettings()
            settings.save(path)
            self.assertEqual(YouTubeSearchSettings.load(path), settings)
            self.assertNotIn("api_key", path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
