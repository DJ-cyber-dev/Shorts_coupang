from pathlib import Path
from .core import Cancelled, Engine, Job, MediaError
from .sourcing.remote import downloaded_video


def convert_source(source, output, *, is_url=False, mode="pad", width=720, height=1280,
                   threads=2, progress=None, status=None, cancel=None):
    output = Path(output)
    if output.exists() or output.suffix.lower() != ".mp4":
        raise MediaError("기존 파일과 다른 .mp4 저장 위치를 선택하세요.")
    engine = Engine()  # 다운로드 전 FFmpeg 설치 여부 확인.
    from .text_removal.service import check_ready, remove_text
    check_ready()
    def convert(path):
        if status:
            status("변환 중…")
        job = Job(path, output, mode=mode, width=width, height=height, threads=threads)
        return remove_text(engine, job, progress, status, cancel)
    if is_url:
        if status:
            status("URL 분석 및 다운로드 중…")
        output.parent.mkdir(parents=True, exist_ok=True)
        with downloaded_video(source, progress=progress, cancel=cancel, parent=output.parent) as path:
            return convert(path)
    return convert(Path(source))


def analyze_source(source, *, is_url=False, status=None, cancel=None):
    """Analyze a local file or explicitly supplied URL with the configured vision Provider."""
    from .providers.settings import ProviderSettings
    from .providers.vision import OpenAICompatibleVisionAnalyzer

    analyzer = OpenAICompatibleVisionAnalyzer(ProviderSettings.load())
    if cancel and cancel.is_set():
        raise Cancelled("취소되었습니다.")
    if is_url:
        if status:
            status("AI 분석용 원본 다운로드 중…")
        with downloaded_video(source, cancel=cancel) as path:
            if status:
                status("선택한 Provider로 frame sample 분석 중…")
            return analyzer.analyze(path, cancel)
    if status:
        status("선택한 Provider로 frame sample 분석 중…")
    return analyzer.analyze(Path(source), cancel)
