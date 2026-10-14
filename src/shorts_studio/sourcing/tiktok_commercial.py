"""Search TikTok's approved Commercial Content API for EEA ad-library references."""
from dataclasses import dataclass
from datetime import date, timedelta
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shorts_studio.core import MediaError
from .tiktok_settings import TikTokCommercialSettings


TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SEARCH_URL = "https://open.tiktokapis.com/v2/research/adlib/ad/query/"
EEA_COUNTRIES = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
    "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
    "RO", "SK", "SI", "ES", "SE", "NO", "IS", "LI",
})
FIELDS = ",".join((
    "ad.id", "ad.first_shown_date", "ad.last_shown_date", "ad.status",
    "ad.videos", "ad.image_urls", "ad.reach", "advertiser.business_name", "advertiser.paid_by",
))


@dataclass(frozen=True)
class TikTokAdCandidate:
    ad_id: str
    advertiser: str
    paid_by: str
    first_shown_date: str
    last_shown_date: str
    status: str
    reach: str
    video_urls: tuple[str, ...]
    image_urls: tuple[str, ...]
    country: str
    source: str = "TikTok Commercial Content API · EEA 광고 라이브러리"
    usage: str = "참고 후보 전용 · 재사용 권리 별도 확인"


class TikTokCommercialSearch:
    def __init__(self, settings: TikTokCommercialSettings | None = None, *, timeout: int = 20,
                 opener=urlopen):
        self.settings = settings or TikTokCommercialSettings.load()
        self.settings.validate()
        self.client_key = self.settings.get_secret(key=True)
        self.client_secret = self.settings.get_secret(key=False)
        if not self.client_key or not self.client_secret:
            raise MediaError(
                "TikTok Commercial Content API 승인 client key/secret이 없습니다. "
                "환경 변수 또는 TikTok API 설정을 확인하세요."
            )
        if not 5 <= timeout <= 60:
            raise ValueError("TikTok API timeout은 5~60초여야 합니다.")
        self.timeout = timeout
        self.opener = opener
        self._access_token = ""
        self._token_expires = 0

    def _post(self, request: Request) -> dict:
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise MediaError("TikTok API 응답 크기 제한을 초과했습니다.")
            payload = json.loads(raw)
        except HTTPError as exc:
            raise MediaError(f"TikTok API 요청 실패 (HTTP {exc.code}). 승인 상태와 quota를 확인하세요.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MediaError(f"TikTok API에 연결할 수 없습니다: {type(exc).__name__}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaError("TikTok API 응답이 JSON이 아닙니다.") from exc
        if not isinstance(payload, dict):
            raise MediaError("TikTok API 응답 구조가 올바르지 않습니다.")
        return payload

    def _token(self) -> str:
        from time import monotonic
        if self._access_token and monotonic() < self._token_expires:
            return self._access_token
        body = urlencode({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }).encode("ascii")
        request = Request(TOKEN_URL, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }, method="POST")
        payload = self._post(request)
        token = payload.get("access_token")
        expires = payload.get("expires_in", 0)
        if not isinstance(token, str) or not token or not isinstance(expires, int) or expires <= 0:
            raise MediaError("TikTok client access token을 발급하지 못했습니다. API 승인과 credentials를 확인하세요.")
        self._access_token = token
        self._token_expires = monotonic() + max(1, expires - 60)
        return token

    def search(self, keyword: str, *, country: str = "FR", lookback_days: int = 30,
               limit: int = 10) -> list[TikTokAdCandidate]:
        keyword = keyword.strip()
        country = country.strip().upper()
        if not keyword or len(keyword) > 50:
            raise ValueError("검색어는 1~50자로 입력하세요.")
        if country not in EEA_COUNTRIES:
            raise ValueError("TikTok Commercial Content API 데이터는 EEA 국가 코드만 지원합니다.")
        if not 1 <= lookback_days <= 365:
            raise ValueError("조회 기간은 최근 1~365일이어야 합니다.")
        if not 1 <= limit <= 10:
            raise ValueError("한 번에 1~10개 광고 후보를 검색할 수 있습니다.")
        end = date.today()
        start = end - timedelta(days=lookback_days - 1)
        query = urlencode({"fields": FIELDS})
        payload = {
            "filters": {
                "ad_published_date_range": {"min": start.strftime("%Y%m%d"), "max": end.strftime("%Y%m%d")},
                "country_code_list": [country],
                "ad_type": "VIDEO",
            },
            "search_term": keyword,
            "search_type": "fuzzy_phrase",
            "max_count": limit,
        }
        request = Request(f"{SEARCH_URL}?{query}", data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, method="POST")
        response = self._post(request)
        error = response.get("error", {})
        if error and (not isinstance(error, dict) or error.get("code") not in {None, "ok"}):
            raise MediaError("TikTok 광고 검색 요청을 처리하지 못했습니다. 승인 scope, 국가, 날짜 범위를 확인하세요.")
        data = response.get("data")
        rows = data.get("ads", []) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise MediaError("TikTok 광고 검색 응답에 ads 목록이 없습니다.")
        results = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            ad = row.get("ad", {})
            advertiser = row.get("advertiser", {})
            if not isinstance(ad, dict) or not isinstance(advertiser, dict):
                continue
            videos = ad.get("videos", [])
            images = ad.get("image_urls", [])
            if not isinstance(videos, list):
                videos = []
            if not isinstance(images, list):
                images = []
            video_urls = tuple(
                item["url"][:2000] for item in videos
                if isinstance(item, dict) and isinstance(item.get("url"), str)
                and item["url"].startswith("https://")
            )[:5]
            image_urls = tuple(url[:2000] for url in images
                               if isinstance(url, str) and url.startswith("https://"))[:5]
            ad_id = str(ad.get("id", ""))
            if not ad_id.isdigit():
                continue
            reach = ad.get("reach", {})
            reach_value = reach.get("unique_users_seen", "") if isinstance(reach, dict) else ""
            results.append(TikTokAdCandidate(
                ad_id=ad_id,
                advertiser=str(advertiser.get("business_name", ""))[:200],
                paid_by=str(advertiser.get("paid_by", ""))[:200],
                first_shown_date=str(ad.get("first_shown_date", ""))[:20],
                last_shown_date=str(ad.get("last_shown_date", ""))[:20],
                status=str(ad.get("status", ""))[:40],
                reach=str(reach_value)[:40],
                video_urls=video_urls,
                image_urls=image_urls,
                country=country,
            ))
        return results
