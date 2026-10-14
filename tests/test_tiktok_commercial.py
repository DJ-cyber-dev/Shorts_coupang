import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shorts_studio.core import MediaError
from shorts_studio.sourcing.tiktok_commercial import TikTokCommercialSearch
from shorts_studio.sourcing.tiktok_settings import TikTokCommercialSettings


class TikTokCommercialSearchTests(unittest.TestCase):
    def test_token_and_keyword_search_maps_approved_eea_ad_references(self):
        token_payload = {"access_token": "test-token", "expires_in": 7200, "token_type": "Bearer"}
        search_payload = {"data": {"ads": [{
            "ad": {
                "id": 123456789, "first_shown_date": "20261001", "last_shown_date": "20261005",
                "status": "active", "videos": [{"url": "https://example-cdn.test/ad.mp4?sig=x"}],
                "reach": {"unique_users_seen": "11K"},
            },
            "advertiser": {"business_name": "Kitchen Co", "paid_by": "Kitchen Group"},
        }]}, "error": {"code": "ok"}}
        responses = []
        for payload in (token_payload, search_payload):
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = json.dumps(payload).encode()
            responses.append(response)
        requests = []

        def opener(request, timeout):
            self.assertEqual(timeout, 20)
            requests.append(request)
            return responses.pop(0)

        settings = TikTokCommercialSettings()
        with patch.object(TikTokCommercialSettings, "get_secret", side_effect=lambda key: "test-key" if key else "test-secret"):
            candidates = TikTokCommercialSearch(settings, opener=opener).search(
                "coffee", country="FR", lookback_days=30, limit=4
            )
        self.assertEqual(len(candidates), 1)
        result = candidates[0]
        self.assertEqual(result.advertiser, "Kitchen Co")
        self.assertEqual(result.reach, "11K")
        self.assertEqual(result.video_urls, ("https://example-cdn.test/ad.mp4?sig=x",))
        self.assertEqual(result.usage, "참고 후보 전용 · 재사용 권리 별도 확인")
        token_form = requests[0].data.decode()
        self.assertIn("client_key=test-key", token_form)
        self.assertIn("grant_type=client_credentials", token_form)
        self.assertIn("Bearer test-token", requests[1].get_header("Authorization"))
        query = json.loads(requests[1].data)
        self.assertEqual(query["search_term"], "coffee")
        self.assertEqual(query["filters"]["country_code_list"], ["FR"])
        self.assertEqual(query["max_count"], 4)

    def test_query_country_keyword_and_limit_validation(self):
        with patch.object(TikTokCommercialSettings, "get_secret", side_effect=lambda key: "key" if key else "secret"):
            client = TikTokCommercialSearch()
        for kwargs in (
            {"country": "KR"}, {"country": "GB"}, {"lookback_days": 366}, {"limit": 11},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                client.search("coffee", **kwargs)
        with self.assertRaises(ValueError):
            client.search("x" * 51)

    def test_rejects_unapproved_credentials_and_api_errors_without_body_leak(self):
        with patch.object(TikTokCommercialSettings, "get_secret", return_value=None):
            with self.assertRaisesRegex(MediaError, "승인 client key/secret"):
                TikTokCommercialSearch()

        with patch.object(TikTokCommercialSettings, "get_secret", side_effect=lambda key: "key" if key else "secret"):
            client = TikTokCommercialSearch()
        with patch.object(client, "_token", return_value="test-token"), patch.object(
            client, "_post", return_value={"data": {}, "error": {"code": "scope_not_authorized", "message": "secret detail"}}
        ):
            with self.assertRaises(MediaError) as error:
                client.search("coffee")
        self.assertNotIn("secret detail", str(error.exception))

    def test_settings_round_trip_never_persists_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiktok-commercial.toml"
            settings = TikTokCommercialSettings("TEST_TIKTOK_KEY", "TEST_TIKTOK_SECRET")
            settings.save(path)
            loaded = TikTokCommercialSettings.load(path)
            self.assertEqual(loaded, settings)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("client_secret =", text)
            self.assertNotIn("api-key-value", text)


if __name__ == "__main__":
    unittest.main()
