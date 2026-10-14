"""Local-only browser UI and API for the installed Shorts Studio application."""
from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from shorts_studio.core import Cancelled, MediaError
from shorts_studio.jobs.history import JobHistory
from shorts_studio.providers.settings import settings_path

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


class LocalJobManager:
    """Owns uploaded files and a single active pipeline job for this local app."""

    def __init__(self, history: JobHistory | None = None, upload_dir: Path | None = None):
        self.history = history or JobHistory()
        self.upload_dir = Path(upload_dir or settings_path().parent / "web-uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active: dict | None = None
        self._cancel = threading.Event()
        self._uploads: dict[str, Path] = {}
        self._outputs: dict[str, Path] = {}
        self._finals: dict[str, Path] = {}
        self._product_matches: dict[str, dict[str, object]] = {}

    def save_upload(self, filename: str, stream, size: int) -> dict:
        safe_name = Path(filename.replace("\\", "/")).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_VIDEO_SUFFIXES:
            raise ValueError("MP4, MOV, MKV, AVI, WEBM 영상만 업로드할 수 있습니다.")
        if size < 1 or size > MAX_UPLOAD_BYTES:
            raise ValueError("업로드 크기는 1 byte~2 GB로 제한됩니다.")
        token = os.urandom(16).hex()
        target = self.upload_dir / f"{token}{suffix}"
        written = 0
        try:
            with target.open("xb") as out:
                while written < size:
                    chunk = stream.read(min(1024 * 1024, size - written))
                    if not chunk:
                        raise ValueError("업로드 데이터가 요청 크기보다 짧습니다.")
                    out.write(chunk)
                    written += len(chunk)
            with self._lock:
                self._uploads[token] = target
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {"token": token, "name": safe_name, "size": written}

    def start(self, source: str, output: str, mode: str) -> dict:
        source = str(source or "").strip()
        if not source:
            raise ValueError("영상 URL 또는 업로드한 파일이 필요합니다.")
        if mode not in {"pad", "crop"}:
            raise ValueError("화면 처리 방식이 올바르지 않습니다.")
        parsed = urlsplit(source)
        if parsed.scheme:
            if parsed.scheme != "https" or parsed.hostname not in {
                "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
                "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
            }:
                raise ValueError("HTTPS YouTube 또는 TikTok 영상 URL만 입력할 수 있습니다.")
            source_value, is_url = source, True
        else:
            with self._lock:
                source_path = self._uploads.get(source)
            if not source_path or not source_path.is_file():
                raise ValueError("업로드 파일을 찾지 못했습니다. 파일을 다시 선택하세요.")
            source_value, is_url = source_path, False

        output_path = Path(output).expanduser() if output else self._default_output(source_value)
        if output_path.suffix.lower() != ".mp4":
            raise ValueError("저장 파일명은 .mp4로 끝나야 합니다.")
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._active and self._active.get("status") == "running":
                raise ValueError("진행 중인 작업을 먼저 완료하거나 취소하세요.")
            record = self.history.create(kind="web_core", source=str(source_value), output=str(output_path))
            job = {**record, "mode": mode, "source_name": self._source_name(source_value),
                   "is_url": is_url, "preview_url": "", "video_url": ""}
            self._active = job
            self._outputs[record["id"]] = output_path
            self._cancel = threading.Event()
        threading.Thread(target=self._run, args=(record["id"], source_value, output_path, mode, is_url),
                         name=f"shorts-job-{record['id'][:8]}", daemon=True).start()
        return self.public_job(job)

    def _run(self, job_id: str, source, output: Path, mode: str, is_url: bool):
        def update(**values):
            with self._lock:
                if not self._active or self._active["id"] != job_id:
                    return
                self._active.update(values)
                self.history.update(job_id, **{k: values[k] for k in ("status", "stage", "progress", "error", "output") if k in values})

        def progress(value):
            with self._lock:
                stage = (self._active or {}).get("stage", "")
            if stage in {"downloading", "preparing"}:
                update(progress=min(0.45, max(0.02, float(value) * 0.45)))
            elif stage == "text_removal":
                # Worker stdout reports a normalized frame-level progress value.
                update(progress=0.55 + min(0.4, max(0, float(value) * 0.4)))

        def status(value):
            text = str(value)
            if "다운로드" in text or "분석" in text:
                stage = "downloading"
            elif "준비" in text or "변환" in text:
                stage = "preparing"
            elif "탐지" in text or "제거" in text:
                stage = "text_removal"
            else:
                stage = "processing"
            update(stage=stage, status_text=text)

        try:
            update(stage="starting", status_text="입력 영상과 필수 문자 제거 준비를 확인합니다.")
            from shorts_studio.pipeline import convert_source
            convert_source(source, output, is_url=is_url, mode=mode, progress=progress,
                           status=status, cancel=self._cancel)
            preview = output.with_suffix(".preview.jpg")
            report = output.with_suffix(".report.json")
            details = {}
            if report.is_file():
                try:
                    details = json.loads(report.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    details = {}
            analysis = self._read_sidecar(output.with_suffix(".analysis.json"))
            script = self._read_sidecar(output.with_suffix(".script.json"))
            with self._lock:
                if self._active and self._active["id"] == job_id:
                    self._active.update(status="completed", stage="completed", progress=1.0,
                                        status_text="완료 · 결과 영상을 확인하세요.",
                                        preview_url=f"/api/jobs/{job_id}/preview" if preview.is_file() else "",
                                        video_url=f"/api/jobs/{job_id}/video", report=details,
                                        output=str(output), analysis=analysis, script=script)
                    self.history.update(job_id, status="completed", stage="completed", progress=1.0)
        except Cancelled as exc:
            update(status="cancelled", stage="cancelled", status_text="작업이 취소되었습니다.", error=str(exc))
        except (MediaError, OSError, ValueError) as exc:
            update(status="failed", stage="failed", status_text="작업을 완료하지 못했습니다.", error=str(exc))
        except Exception as exc:  # Keep unexpected worker failures visible in the UI.
            update(status="failed", stage="failed", status_text="예상하지 못한 오류가 발생했습니다.", error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _source_name(source) -> str:
        return Path(str(source)).name if not str(source).startswith("https://") else str(source)

    @staticmethod
    def _default_output(source) -> Path:
        base = Path.home() / "Videos" / "ShortsStudio"
        name = Path(str(source)).stem if not str(source).startswith("https://") else "shorts"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return base / f"{name[:60]}_{timestamp}.mp4"

    @staticmethod
    def public_job(job: dict | None) -> dict | None:
        if job is None:
            return None
        return dict(job)

    def current(self) -> dict | None:
        with self._lock:
            return self.public_job(dict(self._active)) if self._active else None

    def cancel(self) -> dict:
        with self._lock:
            if not self._active or self._active.get("status") != "running":
                raise ValueError("취소할 작업이 없습니다.")
            self._cancel.set()
            self._active["status_text"] = "안전하게 현재 처리를 중지합니다…"
            return self.public_job(dict(self._active))

    def start_action(self, job_id: str, action: str, body: dict) -> dict:
        if action not in {"analyze", "script", "render", "upload"}:
            raise ValueError("지원하지 않는 작업 단계입니다.")
        with self._lock:
            if not self._active or self._active.get("id") != job_id:
                raise ValueError("현재 앱에서 찾을 수 있는 작업이 아닙니다. 작업을 다시 불러오세요.")
            if self._active.get("status") not in {"completed", "failed"}:
                raise ValueError("앞선 영상 처리 작업이 완료된 뒤 실행할 수 있습니다.")
            source = self._outputs.get(job_id)
            if not source or not source.is_file():
                raise ValueError("필수 문자 제거 영상 파일이 없습니다.")
            if action == "script":
                analysis = body.get("analysis")
                if not isinstance(analysis, dict):
                    analysis = self._read_sidecar(source.with_suffix(".analysis.json"))
                if not isinstance(analysis, dict):
                    raise ValueError("먼저 AI 영상 분석을 완료하세요.")
                body = {**body, "analysis": analysis}
            if action == "render":
                script = body.get("script")
                if not isinstance(script, dict):
                    script = self._read_sidecar(source.with_suffix(".script.json"))
                if not isinstance(script, dict):
                    raise ValueError("먼저 한국어 대본을 생성하거나 입력하세요.")
                body = {**body, "script": script}
            if action == "upload":
                final = self._finals.get(job_id, source.with_name(source.stem + "_final.mp4"))
                if not final.is_file():
                    raise ValueError("먼저 한국어 음성·자막 최종 영상을 합성하세요.")
                if not (settings_path().parent / "youtube-oauth-client.json").is_file():
                    raise ValueError("YouTube OAuth client JSON 파일을 설정에 등록하세요.")
            self._active.update(status="running", stage=action, progress=0.0,
                                status_text={"analyze": "AI 영상 분석 중…", "script": "한국어 대본 생성 중…",
                                             "render": "음성·자막 영상 합성 중…", "upload": "YouTube 업로드 준비 중…"}[action], error="")
            self.history.update(job_id, status="running", stage=action, progress=0.0, error="")
            self._cancel.clear()
        threading.Thread(target=self._run_action, args=(job_id, source, action, dict(body)),
                         name=f"shorts-{action}-{job_id[:8]}", daemon=True).start()
        return self.current()

    @staticmethod
    def _read_sidecar(path: Path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write_sidecar(path: Path, value: dict):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def _run_action(self, job_id: str, source: Path, action: str, body: dict):
        stage_done = f"{action}_completed"
        try:
            if action == "analyze":
                from shorts_studio.pipeline import analyze_source
                result = analyze_source(source, status=lambda text: self._action_status(job_id, text), cancel=self._cancel)
                self._write_sidecar(source.with_suffix(".analysis.json"), result)
                changes = {"analysis": result}
            elif action == "script":
                from shorts_studio.narration.script import KoreanShortsScriptWriter
                result = KoreanShortsScriptWriter().generate(
                    body["analysis"], duration_sec=int(body.get("duration_sec", 30)),
                    tone=str(body.get("tone", "friendly")), call_to_action=str(body.get("call_to_action", "")))
                self._write_sidecar(source.with_suffix(".script.json"), result)
                changes = {"script": result}
            elif action == "render":
                from shorts_studio.narration.render import NarrationRenderer
                script = body["script"]
                target = source.with_name(source.stem + "_final.mp4")
                if target.exists():
                    raise ValueError("최종 영상 파일이 이미 있습니다. 기존 파일을 덮어쓰지 않습니다.")
                NarrationRenderer().render(source, script, target)
                changes = {"final_output": str(target), "final_video_url": f"/api/jobs/{job_id}/final"}
                self._finals[job_id] = target
            else:
                from shorts_studio.upload.youtube import UploadMetadata, YouTubeUploader, authenticated_service
                target = self._finals.get(job_id, source.with_name(source.stem + "_final.mp4"))
                metadata = UploadMetadata(
                    title=str(body.get("title", "")), description=str(body.get("description", "")),
                    tags=tuple(body.get("tags", [])), category_id=str(body.get("category_id", "22")),
                    privacy_status=str(body.get("privacy_status", "private")), publish_at=body.get("publish_at"))
                allow_public = body.get("allow_public") is True
                metadata.validate(allow_public=allow_public)
                client_file = settings_path().parent / "youtube-oauth-client.json"
                service = authenticated_service(client_file)
                receipt = YouTubeUploader(service).upload(
                    target, metadata, allow_public=allow_public,
                    progress=lambda value: self._action_progress(job_id, value))
                changes = {"upload_receipt": receipt}
            with self._lock:
                if self._active and self._active.get("id") == job_id:
                    self._active.update(**changes, status="completed", stage=stage_done, progress=1.0,
                                        status_text={"analyze": "AI 분석 결과를 확인하고 저장하세요.",
                                                     "script": "대본을 확인·편집한 뒤 음성 합성을 진행하세요.",
                                                     "render": "한국어 음성·자막 영상이 완성되었습니다.",
                                                     "upload": "YouTube 업로드가 완료되었습니다."}[action], error="")
                    self.history.update(job_id, status="completed", stage=stage_done, progress=1.0)
        except (MediaError, OSError, ValueError, RuntimeError) as exc:
            self._action_failed(job_id, action, str(exc))
        except Exception as exc:
            self._action_failed(job_id, action, f"{type(exc).__name__}: {exc}")

    def _action_status(self, job_id: str, message: str):
        with self._lock:
            if self._active and self._active.get("id") == job_id:
                self._active["status_text"] = str(message)[:500]

    def _action_progress(self, job_id: str, value: float):
        amount = min(1.0, max(0.0, float(value)))
        with self._lock:
            if self._active and self._active.get("id") == job_id:
                self._active["progress"] = amount
                self.history.update(job_id, progress=amount)

    def _action_failed(self, job_id: str, action: str, error: str):
        with self._lock:
            if self._active and self._active.get("id") == job_id:
                self._active.update(status="failed", stage=f"{action}_failed", error=error[:2000],
                                    status_text="작업 단계에 실패했습니다.")
                self.history.update(job_id, status="failed", stage=f"{action}_failed", error=error[:2000])

    def search_products(self, keyword: str) -> list[dict]:
        from shorts_studio.products import rank_products
        from shorts_studio.products.coupang import CoupangCredentials, CoupangPartnersClient
        credentials = CoupangCredentials.load()
        if credentials is None:
            raise ValueError("Coupang Partners Access Key/Secret을 설정에 등록하세요.")
        matches = rank_products(keyword, CoupangPartnersClient(credentials).search(keyword, limit=10),
                                limit=10, include_unmatched=True)
        self._product_matches = {match.product.id: match for match in matches}
        return [{"id": item.product.id, "title": item.product.title, "url": item.product.url,
                 "affiliate_url": item.product.affiliate_url, "price": item.product.price,
                 "image_url": item.product.image_url, "score": item.score,
                 "matched_terms": list(item.matched_terms), "rank": item.product.rank,
                 "sales_count": item.product.sales_count, "review_count": item.product.review_count,
                 "rating": item.product.rating, "is_rocket": item.product.is_rocket,
                 "is_free_shipping": item.product.is_free_shipping} for item in matches]

    def select_product(self, job_id: str, product_id: str) -> dict:
        from shorts_studio.products import attach_product_match
        with self._lock:
            if not self._active or self._active.get("id") != job_id:
                raise ValueError("현재 작업이 아닙니다. 작업을 먼저 불러오세요.")
            match = self._product_matches.get(product_id)
            source = self._outputs.get(job_id)
        if match is None:
            raise ValueError("먼저 상품 후보를 검색하세요.")
        script = self._read_sidecar(source.with_suffix(".script.json")) if source else None
        if not script:
            raise ValueError("상품 연결 전에 한국어 대본을 생성하세요.")
        updated = attach_product_match(script, match)
        self._write_sidecar(source.with_suffix(".script.json"), updated)
        with self._lock:
            self._active["script"] = updated
        return updated

    def history_rows(self) -> list[dict]:
        return self.history.list_recent(30)

    def media_path(self, job_id: str, kind: str) -> Path | None:
        with self._lock:
            path = self._outputs.get(job_id)
        if path is None:
            for row in self.history.list_recent(100):
                if row.get("id") == job_id and row.get("status") == "completed":
                    path = Path(row.get("output", ""))
                    break
        if path is None:
            return None
        if kind == "final":
            candidate = self._finals.get(job_id, path.with_name(path.stem + "_final.mp4"))
        elif kind == "preview":
            candidate = path.with_suffix(".preview.jpg")
        elif kind in {"srt", "voice", "narration-report"}:
            final = self._finals.get(job_id, path.with_name(path.stem + "_final.mp4"))
            suffix = {"srt": ".srt", "voice": ".voice.wav", "narration-report": ".narration.json"}[kind]
            candidate = final.with_suffix(suffix)
        else:
            candidate = path
        return candidate if candidate.is_file() else None

    def readiness(self) -> dict:
        from shorts_studio.text_removal.service import check_ready
        try:
            check_ready()
            text_removal = {"ready": True, "label": "필수 문자 제거 사용 가능"}
        except (MediaError, OSError) as exc:
            text_removal = {"ready": False, "label": "문자 제거 준비가 필요합니다", "detail": str(exc)}
        return {"text_removal": text_removal, "local_only": True}

    @staticmethod
    def settings_snapshot() -> dict:
        from shorts_studio.narration.settings import TTSSettings
        from shorts_studio.providers.gemini import GeminiScriptSettings, MODEL_OPTIONS
        from shorts_studio.products.coupang import CoupangCredentials
        from shorts_studio.sourcing.settings import YouTubeSearchSettings
        from shorts_studio.sourcing.tiktok_settings import TikTokCommercialSettings
        from shorts_studio.updates.settings import GitHubUpdateSettings
        from shorts_studio.providers.settings import ProviderSettings

        ai = ProviderSettings.load()
        script_ai = GeminiScriptSettings.load()
        tts = TTSSettings.load()
        from shorts_studio.narration.provider import WindowsLocalTTS
        tts_status = WindowsLocalTTS.status() if tts.provider == "windows-local" else {"ready": False, "detail": "TTS가 비활성화되었습니다."}
        youtube = YouTubeSearchSettings.load()
        tiktok = TikTokCommercialSettings.load()
        update = GitHubUpdateSettings.load()
        return {
            "ai": {"provider": ai.provider, "model": ai.model, "base_url": ai.base_url,
                   "key_name": ai.key_name, "key_saved": bool(ai.get_secret())},
            "script_ai": {"provider": "gemini", "model": script_ai.model,
                          "key_name": script_ai.key_name, "key_saved": bool(script_ai.get_secret()),
                          "models": list(MODEL_OPTIONS)},
            "tts": {"provider": tts.provider, "voice": tts_status["voice"] or tts.voice,
                    "voice_options": tts_status["voice_options"],
                    "ready": tts_status["ready"], "detail": tts_status["detail"]},
            "youtube": {"key_name": youtube.key_name, "key_saved": bool(youtube.get_secret())},
            "youtube_oauth_saved": (settings_path().parent / "youtube-oauth-client.json").is_file(),
            "tiktok": {"client_key_name": tiktok.client_key_name,
                       "client_secret_name": tiktok.client_secret_name,
                       "client_key_saved": bool(tiktok.get_secret(True)),
                       "client_secret_saved": bool(tiktok.get_secret(False))},
            "coupang": {"credentials_saved": CoupangCredentials.load() is not None},
            "updates": {"repository": update.repository, "public_key": update.public_key},
        }

    @staticmethod
    def save_settings(name: str, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("설정 본문은 JSON object여야 합니다.")
        if name == "script-ai":
            from shorts_studio.providers.gemini import GeminiScriptSettings
            settings = GeminiScriptSettings(body.get("model", "gemini-3.8-flash"),
                                            body.get("key_name", "SHORTS_GEMINI_API_KEY"))
            settings.validate()
            settings.save()
            if body.get("secret"):
                settings.store_secret(body["secret"])
        elif name == "ai":
            from shorts_studio.providers.settings import ProviderSettings
            settings = ProviderSettings(body.get("provider", "disabled"), body.get("model", ""),
                                        body.get("base_url", ""), body.get("key_name", "SHORTS_AI_KEY"))
            settings.validate()
            settings.save()
            if body.get("secret"):
                settings.store_secret(body["secret"])
        elif name == "tts":
            from shorts_studio.narration.settings import TTSSettings
            settings = TTSSettings(body.get("provider", "windows-local"),
                                   body.get("voice", "Microsoft Heami Desktop - Korean"), float(body.get("speed", 1.0)))
            settings.validate()
            settings.save()
        elif name == "youtube":
            from shorts_studio.sourcing.settings import YouTubeSearchSettings
            settings = YouTubeSearchSettings(body.get("key_name", "SHORTS_YOUTUBE_API_KEY"))
            settings.validate()
            settings.save()
            if body.get("secret"):
                settings.store_secret(body["secret"])
        elif name == "tiktok":
            from shorts_studio.sourcing.tiktok_settings import TikTokCommercialSettings
            settings = TikTokCommercialSettings(body.get("client_key_name", "SHORTS_TIKTOK_CLIENT_KEY"),
                                                body.get("client_secret_name", "SHORTS_TIKTOK_CLIENT_SECRET"))
            settings.validate()
            settings.save()
            if body.get("client_key") or body.get("client_secret"):
                settings.store_secrets(body.get("client_key", ""), body.get("client_secret", ""))
        elif name == "coupang":
            from shorts_studio.products.coupang import CoupangCredentials
            CoupangCredentials.store(body.get("access_key", ""), body.get("secret_key", ""))
        elif name == "updates":
            from shorts_studio.updates.settings import GitHubUpdateSettings
            settings = GitHubUpdateSettings(body.get("repository", ""), body.get("public_key", ""))
            settings.validate()
            settings.save()
        else:
            raise ValueError("알 수 없는 설정 항목입니다.")
        return LocalJobManager.settings_snapshot()

    @staticmethod
    def test_script_ai() -> dict:
        from shorts_studio.providers.gemini import GeminiScriptClient, GeminiScriptSettings
        settings = GeminiScriptSettings.load()
        GeminiScriptClient(settings).test_connection()
        return {"ok": True, "model": settings.model, "message": "Gemini 연결에 성공했습니다."}

    @staticmethod
    def save_youtube_oauth_client(raw: str) -> dict:
        if not isinstance(raw, str) or not raw or len(raw) > 256_000:
            raise ValueError("OAuth client JSON은 256 KB 이하여야 합니다.")
        try:
            payload = json.loads(raw)
            app = payload.get("installed") or payload.get("web")
            if not isinstance(app, dict) or not all(
                    isinstance(app.get(key), str) and app[key]
                    for key in ("client_id", "client_secret", "auth_uri", "token_uri")):
                raise ValueError
        except (json.JSONDecodeError, AttributeError, ValueError) as exc:
            raise ValueError("Google OAuth client JSON 형식을 확인하세요.") from exc
        path = settings_path().parent / "youtube-oauth-client.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        if os.name == "nt":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        return {"saved": True}


class LocalWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, manager: LocalJobManager):
        self.manager = manager
        self._shutdown_event = threading.Event()
        super().__init__(address, LocalWebHandler)


class LocalWebHandler(BaseHTTPRequestHandler):
    server: LocalWebServer

    def log_message(self, _format, *args):
        return  # Do not write local URL/source details into a console log.

    def _json(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"}:
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == self.server.server_port

    def _body_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("요청 크기가 올바르지 않습니다.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if not self._allowed_host():
            return self._json({"error": "허용되지 않은 Host입니다."}, 403)
        path = urlsplit(self.path).path
        manager = self.server.manager
        if path == "/api/status":
            return self._json({"job": manager.current(), "readiness": manager.readiness()})
        if path == "/api/settings":
            try:
                return self._json(manager.settings_snapshot())
            except (OSError, ValueError, RuntimeError, ImportError) as exc:
                return self._json({"error": str(exc)}, 500)
        if path == "/api/history":
            return self._json({"jobs": manager.history_rows()})
            if path == "/api/products":
                return self._json({"error": "상품 후보 검색은 POST 요청을 사용하세요."}, 405)
        media_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/(video|preview|final|srt|voice|narration-report)", path)
        if media_match:
            return self._serve_media(*media_match.groups())
        if path.startswith("/api/"):
            return self._json({"error": "요청한 API를 찾을 수 없습니다."}, 404)
        if path not in {"/", "/index.html", "/app.css", "/app.js"}:
            return self._json({"error": "페이지를 찾을 수 없습니다."}, 404)
        filename = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
        asset = Path(__file__).parent / "static" / filename
        if not asset.is_file():
            return self._json({"error": "UI 파일을 찾을 수 없습니다."}, 500)
        raw = asset.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def _serve_media(self, job_id: str, kind: str):
        path = self.server.manager.media_path(job_id, kind)
        if path is None:
            return self._json({"error": "결과 파일이 없습니다."}, 404)
        size = path.stat().st_size
        content_type = {"preview": "image/jpeg", "video": "video/mp4", "final": "video/mp4",
                        "srt": "application/x-subrip; charset=utf-8", "voice": "audio/wav",
                        "narration-report": "application/json; charset=utf-8"}[kind]
        start, end, status = 0, size - 1, 200
        byte_range = self.headers.get("Range", "")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range.strip())
            if not match:
                return self._json({"error": "잘못된 Range 요청입니다."}, 416)
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(size - 1, int(right)) if right else size - 1
            elif right:
                start = max(0, size - int(right))
            if start > end or start >= size:
                return self._json({"error": "요청 범위가 파일을 벗어났습니다."}, 416)
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as media:
            media.seek(start)
            remaining = length
            while remaining:
                chunk = media.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        if not self._allowed_host():
            self.close_connection = True
            return self._json({"error": "허용되지 않은 Host입니다."}, 403)
        path = urlsplit(self.path).path
        manager = self.server.manager
        try:
            if path == "/api/upload":
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get_content_type() != "application/octet-stream":
                    self.close_connection = True
                    return self._json({"error": "영상 업로드 요청 형식이 올바르지 않습니다."}, 415)
                if length <= 0 or length > MAX_UPLOAD_BYTES:
                    self.close_connection = True
                    return self._json({"error": "업로드 크기는 1 byte~2 GB로 제한됩니다."}, 413)
                name = parse_qs(urlsplit(self.path).query).get("name", [""])[0]
                return self._json(manager.save_upload(name, self.rfile, length), 201)
            if path == "/api/jobs":
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                body = self._body_json()
                return self._json(manager.start(body.get("source", ""), body.get("output", ""),
                                                  body.get("mode", "pad")), 202)
            if path == "/api/products/search":
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                body = self._body_json()
                return self._json({"products": manager.search_products(str(body.get("keyword", "")))})
            action_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/(analyze|script|render|upload)", path)
            if action_match:
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                job_id, action = action_match.groups()
                return self._json(manager.start_action(job_id, action, self._body_json()), 202)
            product_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/product", path)
            if product_match:
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                body = self._body_json()
                return self._json({"script": manager.select_product(product_match.group(1), str(body.get("product_id", "")))})
            if path == "/api/settings/script-ai/test":
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                return self._json(manager.test_script_ai())
            settings_match = re.fullmatch(r"/api/settings/(script-ai|ai|tts|youtube|tiktok|coupang|updates)", path)
            if settings_match:
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                result = manager.save_settings(settings_match.group(1), self._body_json())
                return self._json({"ok": True, "settings": result})
            if path == "/api/settings/youtube-oauth":
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                body = self._body_json()
                return self._json(manager.save_youtube_oauth_client(body.get("oauth_json", "")))
            if path == "/api/cancel":
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    return self._json({"error": "application/json 요청만 허용됩니다."}, 415)
                return self._json(manager.cancel())
            if path == "/api/shutdown":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self._json({"error": "요청한 API를 찾을 수 없습니다."}, 404)
        except (ValueError, OSError, RuntimeError, ImportError, json.JSONDecodeError) as exc:
            if path == "/api/upload":
                self.close_connection = True
            return self._json({"error": str(exc)}, 400)

    def do_OPTIONS(self):
        return self._json({"error": "CORS is disabled."}, 405)


def _find_port(host="127.0.0.1") -> int:
    with socket.socket() as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def run(*, open_browser: bool = True, port: int | None = None, manager: LocalJobManager | None = None):
    manager = manager or LocalJobManager()
    server = LocalWebServer(("127.0.0.1", port or _find_port()), manager)
    address = f"http://127.0.0.1:{server.server_port}/"
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    if getattr(__import__("sys"), "frozen", False):
        app_dir = Path(__import__("sys").executable).parent
        ffmpeg = app_dir / "ffmpeg" / "ffmpeg.exe"
        ffprobe = app_dir / "ffmpeg" / "ffprobe.exe"
        if ffmpeg.is_file():
            os.environ.setdefault("FFMPEG_BINARY", str(ffmpeg))
        if ffprobe.is_file():
            os.environ.setdefault("FFPROBE_BINARY", str(ffprobe))
    run()


if __name__ == "__main__":
    main()
