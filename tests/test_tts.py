import io
import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave

from shorts_studio.core import Engine, MediaError
from shorts_studio.narration.provider import WindowsLocalTTS
from shorts_studio.narration.render import NarrationRenderer, _clean_source, _join_wav_segments, _write_srt
from shorts_studio.narration.settings import TTSSettings


def wav_bytes(frames=1600, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\0\0" * frames)
    return output.getvalue()


class TTSSettingsTests(unittest.TestCase):
    def test_local_free_voice_is_the_default_and_needs_no_api_settings(self):
        settings = TTSSettings()
        settings.validate()
        self.assertEqual(settings.provider, "windows-local")
        self.assertIn("Heami", settings.voice)

    def test_legacy_api_settings_migrate_to_free_local_voice(self):
        path = Path(__file__).with_name(f".legacy-tts-test-{os.getpid()}.toml")
        try:
            path.write_text('[tts]\nprovider = "openai-compatible"\nmodel = "old-model"\nbase_url = "https://old.example"\n', encoding="utf-8")
            settings = TTSSettings.load(path)
            self.assertEqual(settings.provider, "windows-local")
            self.assertIn("Heami", settings.voice)
        finally:
            path.unlink(missing_ok=True)

    def test_only_local_or_disabled_tts_is_allowed(self):
        with self.assertRaises(ValueError):
            TTSSettings("openai-compatible").validate()

    def test_speed_bounds(self):
        with self.assertRaises(ValueError):
            TTSSettings(speed=4.1).validate()


class TTSProviderTests(unittest.TestCase):
    def test_local_provider_writes_valid_wav_without_network(self):
        class FakeProvider(WindowsLocalTTS):
            async def _synthesize(self, text):
                self.text = text
                return wav_bytes()

        provider = object.__new__(FakeProvider)
        provider.settings = TTSSettings()
        path = Path(__file__).with_name(f".local-tts-test-{os.getpid()}.wav")
        try:
            provider.synthesize("한국어 로컬 음성", path)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(provider.text, "한국어 로컬 음성")
        finally:
            path.unlink(missing_ok=True)

    def test_winrt_data_reader_copies_synthesized_wav_into_writable_buffer(self):
        payload = wav_bytes(frames=2400)

        class FakeVoice:
            display_name = "Microsoft Heami"
            language = "ko-KR"

        class FakeStream:
            size = len(payload)

            def get_input_stream_at(self, position):
                if position != 0:
                    raise AssertionError("TTS stream should be read from offset zero")
                return object()

        class FakeSynthesizer:
            async def synthesize_text_to_stream_async(self, text):
                self.text = text
                return FakeStream()

        class FakeDataReader:
            def __init__(self, _stream):
                self.loaded_size = 0

            async def load_async(self, size):
                self.loaded_size = size

            def read_bytes(self, buffer):
                if not isinstance(buffer, bytearray):
                    raise TypeError("ReadBytes requires a writable buffer")
                buffer[:] = payload

        provider = object.__new__(WindowsLocalTTS)
        provider.settings = TTSSettings()
        provider.voices = [FakeVoice()]
        provider.SpeechSynthesizer = FakeSynthesizer
        provider.DataReader = FakeDataReader

        result = asyncio.run(provider._synthesize("한국어 테스트"))
        self.assertEqual(result, payload)
        self.assertTrue(result.startswith(b"RIFF"))

    def test_winrt_foundation_projections_are_present_with_tts_runtime(self):
        try:
            import winrt.windows.media.speechsynthesis  # noqa: F401
        except ImportError:
            self.skipTest("Windows TTS optional dependencies are not installed")
        import winrt.windows.foundation  # noqa: F401
        import winrt.windows.foundation.collections  # noqa: F401

class CaptionAlignmentTests(unittest.TestCase):
    def test_segment_audio_duration_maps_to_srt_timestamps(self):
        root = Path(__file__).parent
        first = root / f".tts-segment-a-{os.getpid()}.wav"
        second = root / f".tts-segment-b-{os.getpid()}.wav"
        joined = root / f".tts-joined-{os.getpid()}.wav"
        captions_path = root / f".tts-captions-{os.getpid()}.srt"
        try:
            first.write_bytes(wav_bytes(frames=1600))
            second.write_bytes(wav_bytes(frames=3200))
            captions, duration = _join_wav_segments([(first, "첫 문장"), (second, "둘째 문장")], joined)
            _write_srt(captions, captions_path)
            self.assertAlmostEqual(captions[0][1], 0.1, places=3)
            self.assertAlmostEqual(captions[1][0], 0.22, places=3)
            self.assertAlmostEqual(captions[1][1], 0.42, places=3)
            self.assertAlmostEqual(duration, 0.42, places=3)
            self.assertIn("00:00:00,220 --> 00:00:00,420", captions_path.read_text(encoding="utf-8-sig"))
        finally:
            for path in (first, second, joined, captions_path):
                path.unlink(missing_ok=True)

    def test_audio_composition_requires_text_removal_report(self):
        video = Path("raw-video.mp4")
        with self.assertRaisesRegex(MediaError, "먼저 제작 pipeline"):
            _clean_source(video)
        renderer = NarrationRenderer(TTSSettings(), engine=object(), provider=object())
        with self.assertRaises(MediaError):
            renderer.render(video, {"segments": [{"narration": "안녕하세요"}]}, Path("result.mp4"))

    def test_accepts_worker_report_method_and_legacy_report(self):
        video = Path(__file__).with_name(f".clean-test-{os.getpid()}.mp4")
        report = video.with_suffix(".report.json")
        try:
            for method in (
                "craft-pixel-mask-lama-telea-v1",
                "CRAFT pixel mask + crop LaMa for large masks + Telea for small masks",
            ):
                report.write_text(json.dumps({"method": method}), encoding="utf-8")
                _clean_source(video)
        finally:
            report.unlink(missing_ok=True)


class NarrationRenderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.engine = Engine()
        except MediaError as exc:
            raise unittest.SkipTest(str(exc))

    def test_worker_report_flows_through_tts_to_final_video_and_sidecars(self):
        with tempfile.TemporaryDirectory(prefix="shorts-tts-integration-") as directory:
            root = Path(directory)
            cleaned = root / "cleaned.mp4"
            subprocess.run([
                self.engine.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=360x640:rate=12", "-t", "1.5", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-threads", "1", str(cleaned),
            ], check=True, capture_output=True, timeout=30)
            cleaned.with_suffix(".report.json").write_text(json.dumps({
                "schema_version": 1,
                "text_removal_required": True,
                "method": "craft-pixel-mask-lama-telea-v1",
            }), encoding="utf-8")

            class FakeTTS:
                def synthesize(self, _text, output):
                    Path(output).write_bytes(wav_bytes(frames=8000))

            target = root / "final.mp4"
            renderer = NarrationRenderer(TTSSettings(), engine=self.engine, provider=FakeTTS())
            renderer.render(cleaned, {"segments": [{"narration": "한국어 테스트 문장입니다."}]}, target)

            info = self.engine.probe(target)
            self.assertEqual((info["video"]["width"], info["video"]["height"]), (360, 640))
            self.assertTrue(any(stream["codec_type"] == "audio" for stream in info["streams"]))
            self.assertTrue(target.with_suffix(".srt").is_file())
            self.assertTrue(target.with_suffix(".voice.wav").is_file())
            report = json.loads(target.with_suffix(".narration.json").read_text(encoding="utf-8"))
            self.assertEqual(report["caption_count"], 1)


if __name__ == "__main__":
    unittest.main()
