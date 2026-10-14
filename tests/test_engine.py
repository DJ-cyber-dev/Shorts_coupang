import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shorts_studio.core import Engine, Job, MediaError, Cancelled
from shorts_studio.core.engine import binary, cleanup_stale_workdirs, ensure_free_space, managed_tempdir
from shorts_studio.providers.settings import ProviderSettings


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"placeholder")

    def test_invalid_options(self):
        for options in [{"width": 721}, {"width": 1280, "height": 720}, {"mode": "bad"},
                        {"threads": 0}, {"crf": 52}, {"timeout": float("nan")}, {"fps": 0}]:
            with self.subTest(options=options), self.assertRaises(MediaError):
                Job(self.source, self.root / "out.mp4", **options).validate()

    def test_preserve_original_and_existing_output(self):
        with self.assertRaises(MediaError):
            Job(self.source, self.source).validate()
        dest = self.root / "out.mp4"
        dest.write_bytes(b"keep")
        with self.assertRaises(MediaError):
            Job(self.source, dest).validate()
        self.assertEqual(dest.read_bytes(), b"keep")

    def test_missing_binary(self):
        with self.assertRaises(MediaError):
            binary("ffmpeg", "shorts-nonexistent-ffmpeg")

    def test_disk_preflight_uses_conservative_estimate(self):
        with patch("shorts_studio.core.engine.shutil.disk_usage",
                   return_value=SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(MediaError, "저장 공간이 부족"):
                ensure_free_space(self.root, 100, copies=3, minimum_bytes=2048)
        with patch("shorts_studio.core.engine.shutil.disk_usage",
                   return_value=SimpleNamespace(free=4096)):
            self.assertEqual(ensure_free_space(self.root, 100, copies=3, minimum_bytes=2048), 2048)

    def test_cleanup_only_removes_old_shorts_temp_directories(self):
        stale = self.root / ".shorts-text-stale"
        recent = self.root / ".shorts-download-recent"
        unrelated = self.root / ".shorts-user-data"
        stale.mkdir()
        recent.mkdir()
        unrelated.mkdir()
        (stale / ".shorts-studio-temp").touch()
        (recent / ".shorts-studio-temp").touch()
        old_time = time.time() - 13 * 60 * 60
        os.utime(stale, (old_time, old_time))
        os.utime(unrelated, (old_time, old_time))
        self.assertEqual(cleanup_stale_workdirs(self.root), 1)
        self.assertFalse(stale.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(recent.exists())

    def test_managed_tempdir_retries_windows_file_lock_cleanup(self):
        import shutil
        real_rmtree = shutil.rmtree
        calls = 0

        def fail_twice(path, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise PermissionError("file is temporarily locked")
            return real_rmtree(path, *args, **kwargs)

        with patch("shorts_studio.core.engine.shutil.rmtree", side_effect=fail_twice):
            with managed_tempdir(prefix=".shorts-text-test-", directory=self.root,
                                 cleanup_attempts=3, retry_delay=0):
                pass
        self.assertEqual(calls, 3)
        self.assertFalse(list(self.root.glob(".shorts-text-test-*")))

    def test_managed_tempdir_preserves_marked_dir_after_cleanup_exhaustion(self):
        with patch("shorts_studio.core.engine.shutil.rmtree", side_effect=PermissionError("locked")):
            with managed_tempdir(prefix=".shorts-text-test-", directory=self.root,
                                 cleanup_attempts=2, retry_delay=0) as folder:
                pass
        self.assertTrue((folder / ".shorts-studio-temp").is_file())
        self.assertGreater(folder.stat().st_mtime, time.time() - 5)

    def test_settings_disabled_and_environment(self):
        self.assertIsNone(ProviderSettings().get_secret())
        with patch.dict(os.environ, {"SHORTS_TEST_KEY": "test-only"}):
            self.assertEqual(ProviderSettings(provider="test", key_name="SHORTS_TEST_KEY").get_secret(), "test-only")

    def test_settings_reject_plaintext_secret(self):
        config = self.root / "config.toml"
        config.write_text('[ai]\napi_key="secret"', encoding="utf-8")
        with self.assertRaises(ValueError):
            ProviderSettings.load(config)

    def test_cancel_running_process(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            Engine._run([sys.executable, "-c", "import time; time.sleep(10)"], 10, 5, None, event)

    def test_timeout(self):
        with self.assertRaisesRegex(MediaError, "제한 시간"):
            Engine._run([sys.executable, "-c", "import time; time.sleep(10)"], 10, .1, None, None)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.engine = Engine()
        except MediaError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="shorts test 한글 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_video(self, size="320x180", audio=True, sar="1"):
        path = self.root / f"원본 {size} {audio} {sar.replace('/', '-')}.mp4"
        command = [self.engine.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=12"]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440"]
        command += ["-t", "1", "-vf", f"setsar={sar}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "1"]
        if audio:
            command += ["-c:a", "aac"]
        subprocess.run(command + [str(path)], check=True, capture_output=True, timeout=30)
        return path

    def test_aspects_modes_and_audio_removal(self):
        for size, audio, sar in [("320x180", True, "1"), ("180x320", False, "1"), ("180x180", True, "4/3")]:
            source = self.make_video(size, audio, sar)
            original = source.read_bytes()
            for mode in ["pad", "crop"]:
                with self.subTest(size=size, mode=mode):
                    target = self.root / f"결과 {size} {mode}.mp4"
                    updates = []
                    self.engine.convert(Job(source, target, mode=mode, width=180, height=320), updates.append)
                    info = self.engine.probe(target)
                    self.assertEqual((info["video"]["width"], info["video"]["height"]), (180, 320))
                    self.assertFalse(any(s["codec_type"] == "audio" for s in info["streams"]))
                    self.assertEqual(info["video"]["sample_aspect_ratio"], "1:1")
                    self.assertAlmostEqual(info["duration"], 1, delta=.2)
                    self.assertEqual(updates[-1], 1)
                    self.assertEqual(source.read_bytes(), original)
                    self.assertFalse(list(self.root.glob(".shorts-*")))

    def test_corrupt_input(self):
        source = self.root / "bad.mp4"
        source.write_bytes(b"not video")
        target = self.root / "output.mp4"
        with self.assertRaises(MediaError):
            self.engine.convert(Job(source, target))
        self.assertFalse(target.exists())

    def test_encoder_failure_cleanup(self):
        source = self.make_video()
        target = self.root / "output.mp4"
        with patch.object(self.engine, "filter", return_value="nonexistent_filter"), self.assertRaises(MediaError):
            self.engine.convert(Job(source, target))
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".shorts-*")))

    def test_cancel_before_start(self):
        source = self.make_video()
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            self.engine.convert(Job(source, self.root / "output.mp4"), cancel=event)


if __name__ == "__main__":
    unittest.main()
