"""Coupang Partners product search with local credential and request limits."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import Product
from shorts_studio.providers.settings import settings_path


class CoupangError(RuntimeError):
    """Safe, user-facing Coupang API or local quota error."""


@dataclass(frozen=True)
class CoupangCredentials:
    access_key: str
    secret_key: str

    @classmethod
    def load(cls) -> "CoupangCredentials | None":
        access = os.getenv("SHORTS_COUPANG_ACCESS_KEY", "").strip()
        secret = os.getenv("SHORTS_COUPANG_SECRET_KEY", "").strip()
        if access and secret:
            return cls(access, secret)
        if os.name != "nt":
            return None
        try:
            from keyring.backends.Windows import WinVaultKeyring
            vault = WinVaultKeyring()
            access = vault.get_password("shorts-studio-coupang", "access_key") or ""
            secret = vault.get_password("shorts-studio-coupang", "secret_key") or ""
        except Exception:
            return None
        return cls(access, secret) if access and secret else None

    @classmethod
    def store(cls, access_key: str, secret_key: str) -> None:
        access_key, secret_key = access_key.strip(), secret_key.strip()
        if not access_key or not secret_key:
            raise ValueError("Access Key와 Secret Key를 모두 입력하세요.")
        if os.name != "nt":
            raise RuntimeError("Windows Credential Manager 저장은 Windows에서만 지원합니다.")
        try:
            from keyring.backends.Windows import WinVaultKeyring
            vault = WinVaultKeyring()
            vault.set_password("shorts-studio-coupang", "access_key", access_key)
            vault.set_password("shorts-studio-coupang", "secret_key", secret_key)
        except Exception as exc:
            raise RuntimeError("Windows Credential Manager에 저장하지 못했습니다.") from exc


class SearchCallLimit:
    """Conservative persistent rolling limit for the Partners search endpoint."""
    _lock = threading.Lock()
    MAX_CALLS = 10
    WINDOW_SECONDS = 3600

    def __init__(self, path: Path | None = None, *, clock=time.time):
        self.path = Path(path) if path else settings_path().parent / "coupang-search-calls.json"
        self.clock = clock

    def reserve(self) -> None:
        now = self.clock()
        with self._lock:
            try:
                calls = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
            except (OSError, json.JSONDecodeError) as exc:
                raise CoupangError("쿠팡 검색 호출 기록을 읽지 못했습니다. 설정 폴더를 확인하세요.") from exc
            if not isinstance(calls, list) or any(not isinstance(value, (int, float)) for value in calls):
                raise CoupangError("쿠팡 검색 호출 기록 형식이 올바르지 않습니다.")
            recent = [float(value) for value in calls if 0 <= now - float(value) < self.WINDOW_SECONDS]
            if len(recent) >= self.MAX_CALLS:
                remaining = max(1, int(self.WINDOW_SECONDS - (now - min(recent))))
                minutes = (remaining + 59) // 60
                raise CoupangError(f"시간당 검색 한도(10회)에 도달했습니다. 약 {minutes}분 후 다시 검색하세요.")
            recent.append(now)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(recent), encoding="utf-8")
            os.replace(temp, self.path)


class CoupangPartnersClient:
    BASE_URL = "https://api-gateway.coupang.com"
    SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def __init__(self, credentials: CoupangCredentials, *, limiter: SearchCallLimit | None = None,
                 opener=urlopen, clock=lambda: datetime.now(timezone.utc)):
        if not credentials.access_key or not credentials.secret_key:
            raise ValueError("쿠팡 Partners API credentials가 필요합니다.")
        self.credentials = credentials
        self.limiter = limiter or SearchCallLimit()
        self.opener = opener
        self.clock = clock

    def _authorization(self, method: str, path_query: str) -> str:
        signed_date = self.clock().astimezone(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        path, separator, query = path_query.partition("?")
        message = f"{signed_date}{method.upper()}{path}{query if separator else ''}"
        signature = hmac.new(self.credentials.secret_key.encode("utf-8"),
                             message.encode("utf-8"), hashlib.sha256).hexdigest()
        return ("CEA algorithm=HmacSHA256, "
                f"access-key={self.credentials.access_key}, signed-date={signed_date}, signature={signature}")

    def search(self, keyword: str, *, limit: int = 10) -> list[Product]:
        keyword = keyword.strip() if isinstance(keyword, str) else ""
        if not 1 <= limit <= 10:
            raise ValueError("쿠팡 상품 검색 개수는 1~10개여야 합니다.")
        if not keyword or len(keyword) > 100:
            raise ValueError("쿠팡 상품 검색어는 1~100자로 입력하세요.")
        query = urlencode((("keyword", keyword), ("limit", limit)))
        path_query = f"{self.SEARCH_PATH}?{query}"
        request = Request(
            self.BASE_URL + path_query,
            headers={"Authorization": self._authorization("GET", path_query),
                     "Content-Type": "application/json;charset=UTF-8"},
            method="GET",
        )
        self.limiter.reserve()
        try:
            with self.opener(request, timeout=15) as response:
                body = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise CoupangError(f"쿠팡 상품 검색 API가 HTTP {exc.code}을 반환했습니다. 계정 권한과 API key를 확인하세요.") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise CoupangError("쿠팡 상품 검색 API에 연결하지 못했습니다. 네트워크를 확인하세요.") from None
        if len(body) > self.MAX_RESPONSE_BYTES:
            raise CoupangError("쿠팡 상품 검색 응답이 허용 크기를 초과했습니다.")
        try:
            payload = json.loads(body.decode("utf-8"))
            rows = payload["data"]["productData"]
            if not isinstance(rows, list):
                raise TypeError
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            raise CoupangError("쿠팡 상품 검색 응답 형식이 올바르지 않습니다.") from None

        products = []
        for index, row in enumerate(rows[:limit], start=1):
            if not isinstance(row, dict):
                continue
            product_id = row.get("productId")
            title = row.get("productName")
            url = row.get("productUrl")
            if not product_id or not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                continue
            raw_price = row.get("productPrice")
            try:
                price = int(raw_price) if raw_price is not None else None
            except (TypeError, ValueError):
                price = None
            def optional_number(*names, integer=False):
                value = next((row.get(name) for name in names if row.get(name) not in (None, "")), None)
                try:
                    return (int(value) if integer else float(value)) if value is not None else None
                except (TypeError, ValueError):
                    return None

            def optional_flag(*names):
                value = next((row.get(name) for name in names if row.get(name) is not None), None)
                if isinstance(value, str):
                    return value.strip().lower() in {"true", "1", "yes"}
                return bool(value) if value is not None else None

            try:
                rank = int(row.get("rank", index))
            except (TypeError, ValueError):
                rank = index
            products.append(Product(
                id=str(product_id), title=title.strip(), url=url,
                price=price, image_url=str(row.get("productImage") or ""),
                affiliate_url=url,
                rank=rank,
                sales_count=optional_number("salesCount", "sales_count", "salesVolume", "sales_volume", integer=True),
                review_count=optional_number("reviewCount", "review_count", "productReviewCount", integer=True),
                rating=optional_number("ratingAverage", "rating_average", "rating"),
                is_rocket=optional_flag("isRocket", "is_rocket"),
                is_free_shipping=optional_flag("isFreeShipping", "is_free_shipping"),
            ))
        return products
