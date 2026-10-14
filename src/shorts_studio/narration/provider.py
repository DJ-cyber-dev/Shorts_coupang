import os
import asyncio
from pathlib import Path
import tempfile

from shorts_studio.core import MediaError
from shorts_studio.core.engine import publish_no_replace
from .settings import TTSSettings


class WindowsLocalTTS:
    """Offline Windows Runtime TTS. Requires an MSIX package identity and installed Korean voice."""

    def __init__(self, settings: TTSSettings | None = None):
        self.settings = settings or TTSSettings.load()
        self.settings.validate()
        if self.settings.provider != "windows-local":
            raise MediaError("TTS 설정에서 Windows 로컬 음성을 선택하세요.")
        try:
            from winrt.windows.media.speechsynthesis import SpeechSynthesizer
            from winrt.windows.storage.streams import DataReader
        except ImportError as exc:
            raise MediaError("Windows TTS 구성요소가 없습니다. MSIX 패키지를 설치하거나 재빌드하세요.") from exc
        try:
            voices = list(SpeechSynthesizer.all_voices)
        except Exception as exc:
            raise MediaError("Windows 음성 목록을 읽지 못했습니다. MSIX 설치와 한국어 음성 설치를 확인하세요.") from exc
        self.voices = voices
        self.SpeechSynthesizer = SpeechSynthesizer
        self.DataReader = DataReader

    @classmethod
    def status(cls) -> dict:
        try:
            provider = cls(TTSSettings())
            korean = [voice for voice in provider.voices if voice.language.lower().startswith("ko")]
            heami = next((voice for voice in korean if "heami" in voice.display_name.lower()), None)
            return {"ready": bool(heami), "voice": heami.display_name if heami else None,
                    "voice_options": [voice.display_name for voice in korean],
                    "detail": "" if heami else "Windows 한국어 Heami 음성을 설치하세요."}
        except MediaError as exc:
            return {"ready": False, "voice": None, "voice_options": [], "detail": str(exc)}

    async def _synthesize(self, text: str) -> bytes:
        synth = self.SpeechSynthesizer()
        voice = next((item for item in self.voices if item.display_name == self.settings.voice), None)
        if voice is None:
            voice = next((item for item in self.voices if "heami" in item.display_name.lower() and "ko" in item.language.lower()), None)
        if voice is None:
            raise MediaError("Windows에 한국어 Heami 음성이 없습니다. 설정 > 시간 및 언어 > 음성에서 추가하세요.")
        synth.voice = voice
        stream = await synth.synthesize_text_to_stream_async(text)
        reader = self.DataReader(stream.get_input_stream_at(0))
        await reader.load_async(stream.size)
        # WinRT DataReader.ReadBytes fills a writable buffer and returns None.
        audio = bytearray(stream.size)
        reader.read_bytes(audio)
        return bytes(audio)

    def synthesize(self, text: str, output: Path) -> Path:
        text = text.strip()
        if not text or len(text) > 4096:
            raise ValueError("TTS 문장은 1~4096자여야 합니다.")
        output = Path(output)
        if output.suffix.lower() != ".wav" or output.exists():
            raise MediaError("TTS 출력은 기존 파일과 다른 .wav 경로여야 합니다.")
        try:
            audio = asyncio.run(self._synthesize(text))
        except MediaError:
            raise
        except Exception as exc:
            raise MediaError(f"Windows 로컬 TTS 합성 실패: {type(exc).__name__}") from exc
        if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise MediaError("Windows TTS가 유효한 WAV를 반환하지 않았습니다.")
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
        os.close(fd)
        temp = Path(temp_name)
        try:
            temp.write_bytes(audio)
            publish_no_replace(temp, output)
        except OSError as exc:
            raise MediaError(f"TTS 오디오 저장 실패: {exc}") from exc
        finally:
            temp.unlink(missing_ok=True)
        return output
