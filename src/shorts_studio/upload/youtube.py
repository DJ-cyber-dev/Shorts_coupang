"""YouTube Data API upload adapter. Uploads default to private visibility."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from shorts_studio.providers.settings import settings_path


@dataclass(frozen=True)
class UploadMetadata:
    title: str
    description: str = ""
    tags: tuple[str, ...] = ()
    category_id: str = "22"
    privacy_status: str = "private"
    publish_at: str | None = None

    def validate(self, *, allow_public: bool = False):
        if not self.title.strip() or len(self.title) > 100:
            raise ValueError("YouTube title은 1~100자로 입력하세요.")
        if len(self.description) > 5000:
            raise ValueError("YouTube description은 5000자를 넘을 수 없습니다.")
        if len(self.tags) > 500 or any(not tag.strip() or len(tag) > 100 for tag in self.tags):
            raise ValueError("tag는 비어 있지 않은 1~100자 항목으로 최대 500개까지 입력하세요.")
        if not self.category_id.isdigit():
            raise ValueError("category_id는 숫자 문자열이어야 합니다.")
        if self.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("privacy_status는 private, unlisted, public 중 하나여야 합니다.")
        if self.privacy_status == "public" and not allow_public:
            raise ValueError("공개 업로드는 명시적 허용(allow_public=True)이 필요합니다.")
        if self.publish_at:
            try:
                scheduled = datetime.fromisoformat(self.publish_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("publish_at은 ISO 8601 timestamp여야 합니다.") from exc
            if scheduled.tzinfo is None or scheduled <= datetime.now(timezone.utc):
                raise ValueError("publish_at은 timezone이 포함된 미래 시각이어야 합니다.")
            if self.privacy_status != "private":
                raise ValueError("예약 게시 영상은 private 상태로 업로드해야 합니다.")

    def request_body(self):
        self.validate(allow_public=self.privacy_status == "public")
        status = {"privacyStatus": self.privacy_status, "selfDeclaredMadeForKids": False}
        if self.publish_at:
            status["publishAt"] = self.publish_at
        return {
            "snippet": {
                "title": self.title.strip(), "description": self.description,
                "tags": list(self.tags), "categoryId": self.category_id,
            },
            "status": status,
        }


def token_path() -> Path:
    return settings_path().parent / "tokens" / "youtube-token.json"


def authenticated_service(client_secrets_file: Path):
    """Open local OAuth consent only when needed; retain refresh token locally."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("업로드 기능 설치 필요: pip install 'shorts-studio[upload]'") from exc
    client_secrets_file = Path(client_secrets_file)
    if not client_secrets_file.is_file():
        raise FileNotFoundError("Google OAuth client secrets JSON 파일을 선택하세요.")
    credentials_path = token_path()
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    credentials = None
    if credentials_path.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(str(credentials_path), ["https://www.googleapis.com/auth/youtube.upload"])
        except (ValueError, OSError):
            credentials_path.unlink(missing_ok=True)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), ["https://www.googleapis.com/auth/youtube.upload"])
        credentials = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="브라우저에서 YouTube 업로드 권한을 승인하세요.")
    credentials_path.write_text(credentials.to_json(), encoding="utf-8")
    if os.name == "nt":
        try:
            os.chmod(credentials_path, 0o600)
        except OSError:
            pass
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


class YouTubeUploader:
    def __init__(self, service, *, media_upload_factory=None, sleep=time.sleep):
        self.service = service
        self._media_upload_factory = media_upload_factory
        self._sleep = sleep

    def upload(self, video_path: Path, metadata: UploadMetadata, *, allow_public=False, progress=None):
        video_path = Path(video_path)
        if not video_path.is_file() or video_path.suffix.lower() != ".mp4":
            raise ValueError("업로드할 MP4 파일을 찾을 수 없습니다.")
        metadata.validate(allow_public=allow_public)
        media_factory = self._media_upload_factory
        if media_factory is None:
            try:
                from googleapiclient.http import MediaFileUpload
            except ImportError as exc:
                raise RuntimeError("업로드 기능 설치 필요: pip install 'shorts-studio[upload]'") from exc
            media_factory = MediaFileUpload
        media = media_factory(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        request = self.service.videos().insert(part="snippet,status", body=metadata.request_body(), media_body=media)
        response = None
        retries = 0
        while response is None:
            try:
                status, response = request.next_chunk()
                retries = 0
                if status and progress:
                    progress(float(status.progress()))
            except Exception as exc:
                code = getattr(getattr(exc, "resp", None), "status", None)
                if code not in {429, 500, 502, 503, 504} or retries >= 5:
                    raise RuntimeError(f"YouTube upload failed ({code or type(exc).__name__}).") from exc
                self._sleep(min(2 ** retries, 30))
                retries += 1
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube upload response did not include a video id.")
        result = {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "privacy_status": metadata.privacy_status}
        receipt = token_path().parent / "uploads.jsonl"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("a", encoding="utf-8") as file:
            file.write(json.dumps({**result, "title": metadata.title, "uploaded_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n")
        return result
