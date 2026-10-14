from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from collections import deque
from dataclasses import dataclass
from typing import Callable


class MediaError(RuntimeError):
    pass


class Cancelled(MediaError):
    pass


@dataclass(frozen=True)
class Job:
    source: Path
    output: Path
    mode: str = "pad"
    width: int = 720
    height: int = 1280
    crf: int = 23
    threads: int = 2
    timeout: float = 3600
    fps: int | None = None

    def validate(self):
        if self.fps is not None and not 1 <= self.fps <= 60:
            raise MediaError("FPS는 1~60이어야 합니다.")
        if not self.source.is_file():
            raise MediaError("원본 파일이 없습니다.")
        if self.source.resolve() == self.output.resolve():
            raise MediaError("원본과 출력 경로는 달라야 합니다.")
        if self.output.exists():
            raise MediaError("출력 파일이 이미 있습니다. 다른 이름을 지정하세요.")
        if self.output.suffix.lower() != ".mp4":
            raise MediaError("출력 파일은 .mp4여야 합니다.")
        if self.mode not in {"pad", "crop"}:
            raise MediaError("mode는 pad 또는 crop이어야 합니다.")
        if (not 2 <= self.width <= 2160 or not 2 <= self.height <= 3840
                or self.width % 2 or self.height % 2
                or self.width * 16 != self.height * 9):
            raise MediaError("출력 크기는 짝수 크기의 9:16이어야 합니다 (최대 2160x3840).")
        if not 0 <= self.crf <= 51 or not 1 <= self.threads <= 32:
            raise MediaError("CRF는 0~51, threads는 1~32여야 합니다.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise MediaError("timeout은 양수여야 합니다.")


def binary(name: str, explicit: str | None = None) -> str:
    value = explicit or os.getenv(name.upper() + "_BINARY") or name
    found = shutil.which(value)
    if not found:
        raise MediaError(f"{name}를 찾을 수 없습니다. FFmpeg 설치 또는 {name.upper()}_BINARY 설정이 필요합니다.")
    return found


def flags():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def ensure_free_space(directory: Path, source_size: int, *, copies: int = 2,
                      minimum_bytes: int = 256 * 1024 * 1024) -> int:
    """Fail before encoding when a conservative output-space estimate cannot fit."""
    required = max(minimum_bytes, max(0, int(source_size)) * copies)
    try:
        available = shutil.disk_usage(directory).free
    except OSError as exc:
        raise MediaError(f"저장 공간을 확인하지 못했습니다: {exc}") from exc
    if available < required:
        required_mb, available_mb = required // (1024 * 1024), available // (1024 * 1024)
        raise MediaError(
            f"저장 공간이 부족합니다. 필요한 여유 공간 약 {required_mb} MB, "
            f"현재 {available_mb} MB입니다. 다른 드라이브를 선택하거나 공간을 확보하세요."
        )
    return required


def cleanup_stale_workdirs(directory: Path, *, older_than_seconds: int = 12 * 60 * 60) -> int:
    """Remove only old, direct-child Shorts temp directories after a crash/restart."""
    directory = Path(directory)
    cutoff = time.time() - max(0, older_than_seconds)
    removed = 0
    if not directory.is_dir():
        return removed
    for child in directory.iterdir():
        if (child.is_symlink() or not child.is_dir()
                or not child.name.startswith(".shorts-")
                or not (child / ".shorts-studio-temp").is_file()):
            continue
        # Current jobs are bounded to two hours; the age threshold keeps live work safe.
        try:
            if child.stat(follow_symlinks=False).st_mtime >= cutoff:
                continue
            shutil.rmtree(child)
            removed += 1
        except OSError:
            continue
    return removed


@contextmanager
def managed_tempdir(*, prefix: str, directory: Path, cleanup_attempts: int = 20,
                    retry_delay: float = 0.25):
    """Create a marked temp directory and never mask the job error during cleanup."""
    folder = Path(tempfile.mkdtemp(prefix=prefix, dir=directory))
    (folder / ".shorts-studio-temp").touch()
    try:
        yield folder
    finally:
        for attempt in range(max(1, cleanup_attempts)):
            try:
                shutil.rmtree(folder)
                break
            except FileNotFoundError:
                break
            except OSError:
                if attempt + 1 < max(1, cleanup_attempts):
                    time.sleep(max(0, retry_delay))
                else:
                    # Windows may briefly retain a worker's file handle after cancellation.
                    # Keep the marked folder for safe cleanup on a later app start.
                    try:
                        now = time.time()
                        os.utime(folder, (now, now))
                    except OSError:
                        pass


def publish_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a same-volume file without requiring NTFS hard links."""
    source, destination = Path(source), Path(destination)
    try:
        if os.name == "nt":
            # Windows os.rename fails if destination already exists and works on exFAT too.
            os.rename(source, destination)
        else:
            # POSIX rename may replace a concurrent output; link is atomic and no-clobber.
            os.link(source, destination)
    except OSError as exc:
        raise MediaError(f"출력 파일을 저장하지 못했습니다. 대상 드라이브와 권한을 확인하세요: {exc}") from exc


class Engine:
    def __init__(self, ffmpeg: str | None = None, ffprobe: str | None = None):
        self.ffmpeg = binary("ffmpeg", ffmpeg)
        self.ffprobe = binary("ffprobe", ffprobe)

    def probe(self, path: Path) -> dict:
        try:
            result = subprocess.run(
                [self.ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
                 "-show_entries", "stream=index,codec_type,width,height,sample_aspect_ratio:stream_disposition=attached_pic:format=duration",
                 "-of", "json", str(path.resolve())],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, **flags())
            if result.returncode:
                raise MediaError("영상 정보를 읽지 못했습니다: " + result.stderr[-2000:])
            data = json.loads(result.stdout)
            videos = [s for s in data.get("streams", []) if s["codec_type"] == "video"
                      and not s.get("disposition", {}).get("attached_pic")]
            if not videos:
                raise MediaError("사용 가능한 video stream이 없습니다.")
            data["video"] = videos[0]
            duration = float(data.get("format", {}).get("duration", 0))
            data["duration"] = duration if math.isfinite(duration) and duration > 0 else 0
            return data
        except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
            raise MediaError(f"영상 검사 실패: {exc}") from exc

    @staticmethod
    def filter(job: Job) -> str:
        w, h = job.width, job.height
        # DAR 반영 후 square pixel로 정규화하여 anamorphic 입력 왜곡 방지.
        base = "scale=trunc(ih*dar/2)*2:ih,setsar=1,"
        if job.mode == "pad":
            return base + (f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
        return base + (f"scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,"
                       f"crop={w}:{h},setsar=1")

    def convert(self, job: Job, progress: Callable[[float], None] | None = None,
                cancel: threading.Event | None = None) -> Path:
        job = Job(**{**job.__dict__, "source": Path(job.source), "output": Path(job.output)})
        job.validate()
        if cancel and cancel.is_set():
            raise Cancelled("취소되었습니다.")
        info = self.probe(job.source)
        job.output.parent.mkdir(parents=True, exist_ok=True)
        cleanup_stale_workdirs(job.output.parent)
        ensure_free_space(job.output.parent, job.source.stat().st_size)
        # 같은 디스크의 임시 파일을 검증한 후 publish. 실패한 MP4는 남기지 않음.
        with managed_tempdir(prefix=".shorts-", directory=job.output.parent) as tmp:
            partial = tmp / "result.mp4"
            command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                       "-protocol_whitelist", "file,pipe", "-threads", str(job.threads),
                       "-i", str(job.source.resolve()), "-map", f"0:{info['video']['index']}",
                       "-vf", self.filter(job), "-an", "-sn", "-dn", "-map_metadata", "-1",
                       "-map_chapters", "-1", "-c:v", "libx264", "-preset", "fast",
                       "-crf", str(job.crf), "-pix_fmt", "yuv420p", "-threads", str(job.threads),
                       "-filter_threads", str(job.threads), "-movflags", "+faststart",
                       "-progress", "pipe:1", "-nostats", str(partial)]
            if job.fps:
                command[-1:-1] = ["-r", str(job.fps)]
            self._run(command, info["duration"], job.timeout, progress, cancel)
            output = self.probe(partial)
            v = output["video"]
            if (v["width"], v["height"]) != (job.width, job.height) or any(
                    s["codec_type"] == "audio" for s in output["streams"]):
                raise MediaError("결과 영상의 크기 또는 음성 제거 검증에 실패했습니다.")
            if cancel and cancel.is_set():
                raise Cancelled("취소되었습니다.")
            # 완성된 파일만 원자적으로 게시하며 이미 있는 출력은 덮어쓰지 않음.
            publish_no_replace(partial, job.output)
        if progress:
            progress(1.0)
        return job.output

    @staticmethod
    def _run(command, duration, timeout, progress, cancel, label="FFmpeg"):
        lines = queue.Queue(maxsize=128)
        errors = deque(maxlen=32)
        started = time.monotonic()
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace",
                                       env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                       start_new_session=os.name != "nt", **flags())
        except OSError as exc:
            raise MediaError(f"{label} 실행 실패: {exc}") from exc

        def read_progress():
            for line in process.stdout:
                try:
                    lines.put_nowait(line)
                except queue.Full:
                    pass

        def read_errors():
            for line in process.stderr:
                errors.append(line[-2000:])

        readers = [threading.Thread(target=read_progress), threading.Thread(target=read_errors)]
        for reader in readers:
            reader.start()
        try:
            while process.poll() is None:
                if cancel and cancel.is_set():
                    raise Cancelled("취소되었습니다.")
                if time.monotonic() - started > timeout:
                    raise MediaError(f"{label} 제한 시간을 초과했습니다.")
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if progress and duration and line.startswith("out_time_us="):
                    try:
                        value = int(line.partition("=")[2])
                    except ValueError:
                        continue
                    progress(min(0.99, max(0, value / 1_000_000 / duration)))
            for reader in readers:
                reader.join()
            if process.returncode:
                raise MediaError(f"{label} 실패: " + "".join(errors)[-4000:])
        finally:
            if process.poll() is None:
                # JS challenge solver 등 하위 프로세스까지 취소.
                if os.name == "nt":
                    try:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, timeout=5, **flags())
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                else:
                    import signal
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
            process.wait()
            for reader in readers:
                reader.join()
            process.stdout.close()
            process.stderr.close()
