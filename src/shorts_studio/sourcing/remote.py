"""Single-video URL acquisition with a cancellable, isolated downloader."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit, parse_qs

from shorts_studio.core import Engine, MediaError, Cancelled


def validate_url(value: str) -> str:
    value = value.strip()
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            raise ValueError()
        host, path = url.hostname, url.path.rstrip("/")
        video_id = r"[A-Za-z0-9_-]{11}"
        valid = False
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            valid = bool(re.fullmatch(rf"/(shorts|embed)/{video_id}", path)) or (
                path == "/watch" and bool(re.fullmatch(video_id, parse_qs(url.query).get("v", [""])[0])))
        elif host == "youtu.be":
            valid = bool(re.fullmatch(rf"/{video_id}", path))
        elif host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
            valid = bool(re.fullmatch(r"/@[^/]+/video/\d+|/t/[A-Za-z0-9]+", path))
        elif host in {"vm.tiktok.com", "vt.tiktok.com"}:
            valid = bool(re.fullmatch(r"/[A-Za-z0-9]+", path))
        if not valid:
            raise ValueError()
    except ValueError as exc:
        raise MediaError("YouTube Shorts/동영상 또는 TikTok 개별 영상의 HTTPS URL을 입력하세요.") from exc
    return value


@contextmanager
def downloaded_video(url, *, progress=None, cancel=None, parent=None):
    url = validate_url(url)
    if cancel and cancel.is_set():
        raise Cancelled("취소되었습니다.")
    if not importlib.util.find_spec("yt_dlp"):
        raise MediaError("URL 다운로드 모듈이 없습니다. scripts/setup.ps1을 다시 실행하세요.")
    with tempfile.TemporaryDirectory(prefix=".shorts-download-", dir=parent) as directory:
        (Path(directory) / ".shorts-studio-temp").touch()
        command = [sys.executable, "-m", "shorts_studio.sourcing.worker", url, directory]
        Engine._run(command, 1, 900, progress, cancel, label="다운로드")
        files = [p for p in Path(directory).glob("source.*") if p.suffix in {".mp4", ".webm", ".mkv", ".mov", ".flv"}]
        if len(files) != 1 or not files[0].stat().st_size:
            raise MediaError("영상이 다운로드되지 않았습니다. 공개 상태와 영상 길이를 확인하세요.")
        yield files[0]
