"""YouTube Data API search for short, Creative Commons reuse candidates."""
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shorts_studio.core import MediaError
from .settings import YouTubeSearchSettings


VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
API_URL = "https://www.googleapis.com/youtube/v3/search"


@dataclass(frozen=True)
class SourceCandidate:
    video_id: str
    title: str
    channel: str
    published_at: str
    thumbnail_url: str
    url: str
    license: str = "creativeCommon"


class YouTubeSourceSearch:
    def __init__(self, settings: YouTubeSearchSettings | None = None, *, timeout: int = 20):
        self.settings = settings or YouTubeSearchSettings.load()
        self.api_key = self.settings.get_secret()
        if not self.api_key:
            raise MediaError(f"YouTube Data API key가 없습니다. {self.settings.key_name}를 설정하세요.")
        if not 5 <= timeout <= 60:
            raise ValueError("YouTube API timeout은 5~60초여야 합니다.")
        self.timeout = timeout

    def search(self, keyword: str, *, limit: int = 10) -> list[SourceCandidate]:
        keyword = keyword.strip()
        if not keyword or len(keyword) > 100:
            raise ValueError("검색어는 1~100자로 입력하세요.")
        if not 1 <= limit <= 25:
            raise ValueError("한 번에 1~25개 후보를 검색할 수 있습니다.")
        params = urlencode({
            "part": "snippet", "q": keyword, "type": "video", "videoLicense": "creativeCommon",
            "videoDuration": "short", "maxResults": limit, "regionCode": "KR",
            "relevanceLanguage": "ko", "key": self.api_key,
        })
        request = Request(f"{API_URL}?{params}", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise MediaError("YouTube Search 응답 크기가 제한을 초과했습니다.")
            payload = json.loads(raw)
        except HTTPError as exc:
            raise MediaError(f"YouTube Search 요청 실패 (HTTP {exc.code}). API key와 quota를 확인하세요.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MediaError(f"YouTube Search에 연결할 수 없습니다: {type(exc).__name__}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaError("YouTube Search 응답이 JSON이 아닙니다.") from exc
        candidates = []
        for item in payload.get("items", []):
            video_id = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})
            if not VIDEO_ID.fullmatch(video_id):
                continue
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = (thumbnails.get("medium") or thumbnails.get("default") or {}).get("url", "")
            candidates.append(SourceCandidate(
                video_id=video_id,
                title=str(snippet.get("title", ""))[:500],
                channel=str(snippet.get("channelTitle", ""))[:200],
                published_at=str(snippet.get("publishedAt", ""))[:40],
                thumbnail_url=thumbnail if thumbnail.startswith("https://") else "",
                url=f"https://www.youtube.com/watch?v={video_id}",
            ))
        return candidates
