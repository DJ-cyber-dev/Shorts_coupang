"""Segment TTS, timestamp-aligned SRT, and voiceover composition for text-cleaned video."""
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap
import wave

from shorts_studio.core import Engine, MediaError
from shorts_studio.core.engine import publish_no_replace
from .provider import WindowsLocalTTS
from .settings import TTSSettings


GAP_SECONDS = 0.12


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    whole, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole:02d},{millis:03d}"


def _caption_lines(value: str) -> str:
    return "\n".join(textwrap.wrap(value.strip(), width=24, break_long_words=True, break_on_hyphens=False))


def _write_srt(captions, path: Path):
    rows = []
    for index, (start, end, text) in enumerate(captions, start=1):
        rows.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{_caption_lines(text)}")
    path.write_text("\n\n".join(rows) + "\n", encoding="utf-8-sig")


def _filter_path(path: Path) -> str:
    value = path.resolve().as_posix().replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
    return f"'{value}'"


def _clean_source(video: Path):
    report = video.with_suffix(".report.json")
    if not report.is_file():
        raise MediaError("필수 문자 제거 결과가 아닙니다. 먼저 제작 pipeline으로 문자를 제거하세요.")
    try:
        value = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MediaError("문자 제거 report를 읽을 수 없습니다.") from exc
    method = value.get("method") if isinstance(value, dict) else None
    # Accept the legacy report and the current worker's stable method identifier.
    valid_methods = {
        "CRAFT detection",
        "CRAFT pixel mask + crop LaMa for large masks + Telea for small masks",
        "craft-pixel-mask-lama-telea-v1",
        "craft-pixel-mask-persistent-consensus-lama-telea-v2",
    }
    if not isinstance(value, dict) or method not in valid_methods:
        raise MediaError("문자 제거 검증 정보가 없는 영상은 TTS 합성에 사용할 수 없습니다.")


def _join_wav_segments(paths, output: Path):
    captions = []
    params = None
    cursor_frames = 0
    wav_out = None
    try:
        for index, (path, text) in enumerate(paths):
            with wave.open(str(path), "rb") as source:
                current = source.getparams()
                if current.comptype != "NONE":
                    raise MediaError("압축 WAV는 아직 합성할 수 없습니다.")
                if params is None:
                    params = current
                    wav_out = wave.open(str(output), "wb")
                    wav_out.setnchannels(params.nchannels)
                    wav_out.setsampwidth(params.sampwidth)
                    wav_out.setframerate(params.framerate)
                    wav_out.setcomptype("NONE", "not compressed")
                elif (current.nchannels, current.sampwidth, current.framerate, current.comptype) != (
                        params.nchannels, params.sampwidth, params.framerate, params.comptype):
                    raise MediaError("TTS segment 간 audio sample 형식이 다릅니다.")
                data = source.readframes(source.getnframes())
                speech_frames = len(data) // (params.nchannels * params.sampwidth)
                start = cursor_frames / params.framerate
                wav_out.writeframes(data)
                cursor_frames += speech_frames
                end = cursor_frames / params.framerate
                captions.append((start, end, text))
                silence_frames = round(params.framerate * GAP_SECONDS) if index < len(paths) - 1 else 0
                if silence_frames:
                    silence_byte = 128 if params.sampwidth == 1 else 0
                    wav_out.writeframes(bytes([silence_byte]) * silence_frames * params.nchannels * params.sampwidth)
                    cursor_frames += silence_frames
    finally:
        if wav_out:
            wav_out.close()
    if not captions or not params:
        raise MediaError("합성할 음성 segment가 없습니다.")
    return captions, cursor_frames / params.framerate


class NarrationRenderer:
    def __init__(self, settings: TTSSettings | None = None, *, engine: Engine | None = None, provider=None):
        self.settings = settings or TTSSettings.load()
        self.engine = engine or Engine()
        self.provider = provider or WindowsLocalTTS(self.settings)

    def render(self, cleaned_video: Path, script: dict, output: Path) -> Path:
        cleaned_video, output = Path(cleaned_video), Path(output)
        _clean_source(cleaned_video)
        if output.suffix.lower() != ".mp4" or output.exists():
            raise MediaError("새 .mp4 출력 경로를 지정하세요. 기존 파일은 덮어쓰지 않습니다.")
        segments = script.get("segments") if isinstance(script, dict) else None
        if not isinstance(segments, list) or not 1 <= len(segments) <= 12:
            raise ValueError("대본에는 1~12개 narration segment가 필요합니다.")
        rows = []
        for segment in segments:
            if not isinstance(segment, dict) or not isinstance(segment.get("narration"), str) or not segment["narration"].strip():
                raise ValueError("각 대본 segment에 narration 문장이 필요합니다.")
            rows.append(segment["narration"].strip())
        output.parent.mkdir(parents=True, exist_ok=True)
        srt_output = output.with_suffix(".srt")
        voice_output = output.with_suffix(".voice.wav")
        report_output = output.with_suffix(".narration.json")
        if any(path.exists() for path in (srt_output, voice_output, report_output)):
            raise MediaError("같은 이름의 자막/음성 sidecar가 있습니다. 다른 출력 이름을 선택하세요.")
        video_info = self.engine.probe(cleaned_video)
        temp_root = None
        published = []
        try:
            temp_root = tempfile.TemporaryDirectory(prefix=".shorts-narration-", dir=output.parent)
            work = Path(temp_root.name)
            segment_paths = []
            for index, text in enumerate(rows, start=1):
                audio_path = work / f"segment-{index:02d}.wav"
                self.provider.synthesize(text, audio_path)
                segment_paths.append((audio_path, text))
            voice = work / "voice.wav"
            captions, speech_duration = _join_wav_segments(segment_paths, voice)
            if speech_duration > video_info["duration"] + 0.05:
                raise MediaError(
                    f"대본 음성({speech_duration:.1f}초)이 문자 제거 영상({video_info['duration']:.1f}초)보다 깁니다. 대본을 줄이세요."
                )
            srt = work / "captions.srt"
            _write_srt(captions, srt)
            partial = work / "render.mp4"
            subtitle_filter = (f"subtitles=filename={_filter_path(srt)}:force_style="
                               "'FontName=Malgun Gothic,FontSize=20,Outline=2,Shadow=0,MarginV=120'")
            command = [self.engine.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                       "-i", str(cleaned_video.resolve()), "-i", str(voice),
                       "-map", "0:v:0", "-map", "1:a:0", "-vf", subtitle_filter,
                       "-af", "apad", "-shortest", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                       "-threads", "2", "-c:a", "aac", "-b:a", "160k", "-pix_fmt", "yuv420p",
                       "-movflags", "+faststart", str(partial)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=3600)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise MediaError(f"TTS 영상 합성 실패: {type(exc).__name__}") from exc
            if result.returncode:
                raise MediaError("TTS 영상 합성에 실패했습니다. FFmpeg subtitles/libass와 한글 font를 확인하세요.")
            final = self.engine.probe(partial)
            if (final["video"]["width"], final["video"]["height"]) != (
                    video_info["video"]["width"], video_info["video"]["height"]):
                raise MediaError("TTS 출력 영상의 크기 검증에 실패했습니다.")
            if not any(stream["codec_type"] == "audio" for stream in final["streams"]):
                raise MediaError("TTS 출력에 narration audio가 없습니다.")
            summary = {"segments": len(rows), "speech_duration_sec": round(speech_duration, 3),
                       "caption_count": len(captions), "text_removal_required": True}
            report = work / "narration.json"
            report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            for source, destination in ((partial, output), (srt, srt_output), (voice, voice_output), (report, report_output)):
                publish_no_replace(source, destination)
                published.append(destination)
        except OSError as exc:
            for path in published:
                path.unlink(missing_ok=True)
            raise MediaError(f"합성 결과 저장 실패: {exc}") from exc
        except Exception:
            for path in published:
                path.unlink(missing_ok=True)
            raise
        finally:
            if temp_root:
                temp_root.cleanup()
        return output
