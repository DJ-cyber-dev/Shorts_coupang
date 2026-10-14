"""Private subprocess entry point; download files never leave its job directory."""
import os
from pathlib import Path
import shutil
import sys
from .remote import validate_url

MAX_BYTES = 500 * 1024 * 1024


def options(directory):
    def hook(info):
        received = info.get("downloaded_bytes", 0) or 0
        if received > MAX_BYTES:
            raise RuntimeError("영상 다운로드 용량 제한(500 MB)을 초과했습니다.")
        total = info.get("total_bytes") or info.get("total_bytes_estimate")
        if total:
            print(f"out_time_us={int(min(.99, received / total) * 1_000_000)}", flush=True)

    def single_video(info, *, incomplete=False):
        if info.get("is_live") or info.get("live_status") == "is_upcoming":
            return "라이브 영상은 지원하지 않습니다."
        if (info.get("duration") or 0) > 600:
            return "10분 이하 영상만 지원합니다."

    runtimes = {}
    for runtime in ("deno", "node"):
        path = os.getenv("SHORTS_JS_RUNTIME") if runtime == "node" else None
        path = path or shutil.which(runtime)
        if path:
            runtimes[runtime] = {"path": path}
    return {
        "outtmpl": str(Path(directory).resolve() / "source.%(ext)s"),
        # 결과는 무음이므로 단일 video stream 우선; 불필요한 audio 병합 생략.
        "format": "bestvideo[height<=1920][width<=1920]/best[height<=1920][width<=1920]",
        "noplaylist": True, "playlist_items": "1", "max_downloads": 1,
        "max_filesize": MAX_BYTES, "match_filter": single_video,
        "socket_timeout": 20, "retries": 2, "fragment_retries": 2,
        "concurrent_fragment_downloads": 1, "hls_prefer_native": True,
        "skip_unavailable_fragments": False,
        "quiet": True, "noprogress": True, "cachedir": False,
        "progress_hooks": [hook], "js_runtimes": runtimes,
    }


def main():
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import MaxDownloadsReached
    url, directory = validate_url(sys.argv[1]), sys.argv[2]
    try:
        with YoutubeDL(options(directory)) as downloader:
            downloader.download([url])
    except MaxDownloadsReached:
        pass  # 단일 영상 완료 후의 정상 중단.
    except Exception as exc:
        print(f"URL을 가져오지 못했습니다. 공개 상태/로그인 요구/네트워크를 확인하세요.\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
