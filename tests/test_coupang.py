from datetime import datetime, timezone
from io import BytesIO
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.error import HTTPError

from shorts_studio.products.coupang import (
    CoupangCredentials,
    CoupangError,
    CoupangPartnersClient,
    SearchCallLimit,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.payload


class CoupangPartnersTests(unittest.TestCase):
    def test_signs_exact_encoded_query_and_maps_partner_products(self):
        now = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        captured = {}
        payload = {"data": {"productData": [{
            "productId": 123, "productName": "무선 청소기", "productPrice": 34900,
            "productImage": "https://img.example/item.jpg", "productUrl": "https://link.coupang.com/a/test",
            "rank": "2", "reviewCount": "183", "ratingAverage": "4.6", "isRocket": True,
        }]}}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        with tempfile.TemporaryDirectory() as folder:
            client = CoupangPartnersClient(
                CoupangCredentials("access", "secret"),
                limiter=SearchCallLimit(Path(folder) / "calls.json"),
                opener=opener, clock=lambda: now,
            )
            products = client.search("무선 청소기", limit=2)

        query = urlencode((("keyword", "무선 청소기"), ("limit", 2)))
        path_query = f"{client.SEARCH_PATH}?{query}"
        signed_date = "250102T030405Z"
        digest = hmac.new(
            b"secret", f"{signed_date}GET{client.SEARCH_PATH}{query}".encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(captured["url"], client.BASE_URL + path_query)
        self.assertEqual(captured["authorization"],
                         f"CEA algorithm=HmacSHA256, access-key=access, signed-date={signed_date}, signature={digest}")
        self.assertEqual(captured["timeout"], 15)
        self.assertEqual(products[0].id, "123")
        self.assertEqual(products[0].price, 34900)
        self.assertEqual(products[0].affiliate_url, "https://link.coupang.com/a/test")
        self.assertEqual(products[0].rank, 2)
        self.assertEqual(products[0].review_count, 183)
        self.assertEqual(products[0].rating, 4.6)
        self.assertTrue(products[0].is_rocket)
        self.assertIsNone(products[0].sales_count)

    def test_validates_query_and_per_request_result_limit(self):
        client = CoupangPartnersClient(CoupangCredentials("a", "b"), opener=lambda *_args, **_kwargs: None)
        for keyword, limit in ((" ", 1), ("팬", 0), ("팬", 11)):
            with self.subTest(keyword=keyword, limit=limit), self.assertRaises(ValueError):
                client.search(keyword, limit=limit)

    def test_environment_credentials_and_http_errors_do_not_expose_secrets(self):
        with patch.dict(os.environ, {
            "SHORTS_COUPANG_ACCESS_KEY": "private-access",
            "SHORTS_COUPANG_SECRET_KEY": "private-secret",
        }):
            self.assertEqual(CoupangCredentials.load(), CoupangCredentials("private-access", "private-secret"))

        def opener(*_args, **_kwargs):
            raise HTTPError("https://api-gateway.coupang.com/search", 403, "Denied", {},
                            BytesIO(b"private-access private-secret response"))

        with tempfile.TemporaryDirectory() as folder:
            client = CoupangPartnersClient(
                CoupangCredentials("private-access", "private-secret"),
                limiter=SearchCallLimit(Path(folder) / "calls.json"), opener=opener,
            )
            with self.assertRaises(CoupangError) as result:
                client.search("무선 청소기")
        self.assertNotIn("private-access", str(result.exception))
        self.assertNotIn("private-secret", str(result.exception))

    def test_persistent_limit_allows_ten_requests_then_waits_one_hour(self):
        with tempfile.TemporaryDirectory() as folder:
            now = [1_800_000_000.0]
            limiter = SearchCallLimit(Path(folder) / "calls.json", clock=lambda: now[0])
            for _ in range(10):
                limiter.reserve()
            reloaded = SearchCallLimit(Path(folder) / "calls.json", clock=lambda: now[0])
            with self.assertRaisesRegex(CoupangError, "시간당 검색 한도"):
                reloaded.reserve()
            now[0] += 3600
            limiter.reserve()


if __name__ == "__main__":
    unittest.main()
