import importlib.util
import os
from pathlib import Path
import sys
from shorts_studio.core import Engine, Job, MediaError, Cancelled
from shorts_studio.core.engine import cleanup_stale_workdirs, ensure_free_space, managed_tempdir, publish_no_replace
from .model import lama_model_path, model_dir, user_network_dir


def check_ready():
    if getattr(sys, "frozen", False):
        worker = Path(sys.executable).parent / "worker" / "ShortsStudioWorker.exe"
        if not worker.is_file():
            raise MediaError("문자 제거 worker가 설치되지 않았습니다. 앱을 재설치하세요.")
    elif not all(importlib.util.find_spec(name) for name in ("easyocr", "cv2", "torch")):
        raise MediaError("필수 문자 제거 모듈이 없습니다. scripts/setup.ps1을 실행하세요.")
    if not (model_dir() / "craft_mlt_25k.pth").is_file():
        raise MediaError("필수 문자 탐지 모델이 없습니다. scripts/setup.ps1을 실행하세요.")
    if not lama_model_path().is_file():
        raise MediaError("필수 LaMa 복원 모델이 없습니다. scripts/setup.ps1을 실행하세요.")


def remove_text(engine, job, progress=None, status=None, cancel=None):
    from .resources import ResourceSettings
    resources = ResourceSettings.load()
    check_ready()
    job.validate()
    if any(job.output.with_suffix(s).exists() for s in (".preview.jpg", ".report.json")):
        raise MediaError("같은 이름의 문자 제거 기록이 있습니다. 다른 출력 이름을 선택하세요.")
    job.output.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_workdirs(job.output.parent)
    ensure_free_space(job.output.parent, job.source.stat().st_size,
                      copies=4, minimum_bytes=512 * 1024 * 1024)
    with managed_tempdir(prefix=".shorts-text-", directory=job.output.parent) as folder:
        normalized, cleaned = folder / "normalized.mp4", folder / "cleaned.mp4"
        if status:
            status("문자 제거용 영상 준비 중…")
        # CFR로 정규화하여 프레임 단위 처리 후에도 재생 시간을 유지.
        engine.convert(Job(**{**job.__dict__, "output": normalized, "fps": 30, "crf": 18,
                              "threads": resources.cpu_threads}), progress, cancel,
                       low_priority=resources.background_priority)
        if status:
            status("전체 화면 문자 탐지·제거 중… (CPU 처리)")
        if getattr(sys, "frozen", False):
            worker = Path(sys.executable).parent / "worker" / "ShortsStudioWorker.exe"
            command = [str(worker), str(normalized), str(cleaned), engine.ffmpeg]
        else:
            command = [sys.executable, "-m", "shorts_studio.text_removal.worker", str(normalized), str(cleaned), engine.ffmpeg]
        os.environ.setdefault("SHORTS_MODEL_DIR", str(model_dir()))
        os.environ.setdefault("SHORTS_USER_NETWORK_DIR", str(user_network_dir()))
        engine._run(command, 1, 7200, progress, cancel, label="문자 제거",
                    low_priority=resources.background_priority,
                    extra_env={
                        "SHORTS_STUDIO_CPU_THREADS": str(resources.cpu_threads),
                        "SHORTS_STUDIO_LOW_PRIORITY": "1" if resources.background_priority else "0",
                    })
        info = engine.probe(cleaned)
        prepared = engine.probe(normalized)
        if abs(info["duration"] - prepared["duration"]) > .1:
            raise MediaError("문자 제거 결과의 재생 시간이 원본과 다릅니다.")
        if (info["video"]["width"], info["video"]["height"]) != (job.width, job.height) or any(
                s["codec_type"] == "audio" for s in info["streams"]):
            raise MediaError("문자 제거 결과 검증 실패")
        if cancel and cancel.is_set():
            raise Cancelled("취소되었습니다.")
        published = []
        publish_no_replace(cleaned, job.output)
        published.append(job.output)
        for suffix in (".preview.jpg", ".report.json"):
            artifact, target = cleaned.with_suffix(suffix), job.output.with_suffix(suffix)
            if suffix == ".report.json" and not artifact.is_file():
                for path in published:
                    path.unlink(missing_ok=True)
                raise MediaError("문자 제거 report가 없어 결과를 TTS 단계에 전달할 수 없습니다.")
            if suffix == ".report.json" and target.exists():
                for path in published:
                    path.unlink(missing_ok=True)
                raise MediaError("기존 문자 제거 report를 덮어쓰지 않습니다. 다른 출력 이름을 선택하세요.")
            if artifact.exists() and not target.exists():
                try:
                    publish_no_replace(artifact, target)
                    published.append(target)
                except MediaError:
                    if suffix == ".report.json":
                        for path in published:
                            path.unlink(missing_ok=True)
                        raise
                    # Preview is optional; the report is required by TTS stage validation.
    if progress:
        progress(1)
    return job.output
