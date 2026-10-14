from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from shorts_studio.core import MediaError, Cancelled
from shorts_studio.pipeline import convert_source
from shorts_studio.sourcing.remote import validate_url, downloaded_video
from shorts_studio.sourcing.worker import options, MAX_BYTES

URL = "https://www.youtube.com/shorts/BaW_jenozKc"


class URLTests(unittest.TestCase):
    def test_supported_urls(self):
        for url in [URL, "https://youtu.be/BaW_jenozKc", "https://www.youtube.com/watch?v=BaW_jenozKc&list=test",
                    "https://www.tiktok.com/@creator/video/123456789", "https://vm.tiktok.com/ABC123/",
                    "https://vt.tiktok.com/ABC123/", "https://www.tiktok.com/t/ABC123/"]:
            with self.subTest(url=url):
                self.assertEqual(validate_url(url), url)

    def test_reject_nonvideo_and_host_spoofing(self):
        for url in ["http://youtu.be/BaW_jenozKc", "https://youtube.com.evil.test/shorts/BaW_jenozKc",
                    "https://youtube.com/playlist?list=abc", "https://youtube.com/@channel",
                    "file:///input.mp4", "https://localhost/video", "https://www.tiktok.com/@name",
                    "https://user:pass@youtu.be/BaW_jenozKc", "https://youtu.be:99/BaW_jenozKc"]:
            with self.subTest(url=url), self.assertRaises(MediaError):
                validate_url(url)

    def test_options_resource_limits(self):
        opts = options(".")
        self.assertEqual(opts["concurrent_fragment_downloads"], 1)
        self.assertTrue(opts["noplaylist"])
        self.assertIsNotNone(opts["match_filter"]({"duration": 601}))
        self.assertIsNotNone(opts["match_filter"]({"is_live": True}))
        self.assertIsNone(opts["match_filter"]({"duration": 30}))
        with self.assertRaises(RuntimeError):
            opts["progress_hooks"][0]({"downloaded_bytes": MAX_BYTES + 1})

    def test_cancel_before_download(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled), downloaded_video(URL, cancel=event):
            self.fail("must not start")

    def test_temp_cleanup_success_and_consumer_failure(self):
        def fake_run(command, *args, **kwargs):
            (Path(command[-1]) / "source.mp4").write_bytes(b"test")
        for fail in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                with patch("shorts_studio.sourcing.remote.Engine._run", side_effect=fake_run), \
                     patch("shorts_studio.sourcing.remote.importlib.util.find_spec", return_value=True):
                    try:
                        with downloaded_video(URL, parent=folder) as video:
                            self.assertEqual(video.read_bytes(), b"test")
                            if fail:
                                raise ValueError("conversion failure")
                    except ValueError:
                        pass
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_download_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("shorts_studio.sourcing.remote.Engine._run", side_effect=MediaError("network")), \
                 patch("shorts_studio.sourcing.remote.importlib.util.find_spec", return_value=True):
                with self.assertRaises(MediaError), downloaded_video(URL, parent=folder):
                    self.fail("must not yield")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_existing_output_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "existing.mp4"
            output.write_bytes(b"keep")
            with patch("shorts_studio.pipeline.downloaded_video") as download:
                with self.assertRaises(MediaError):
                    convert_source(URL, output, is_url=True)
                download.assert_not_called()
            self.assertEqual(output.read_bytes(), b"keep")
