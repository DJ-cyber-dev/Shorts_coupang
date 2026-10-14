import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from shorts_studio.upload.youtube import UploadMetadata, YouTubeUploader


class YouTubeUploadTests(unittest.TestCase):
    def test_private_default_and_public_guard(self):
        self.assertEqual(UploadMetadata("테스트").request_body()["status"]["privacyStatus"], "private")
        with self.assertRaises(ValueError):
            UploadMetadata("테스트", privacy_status="public").validate()
        UploadMetadata("테스트", privacy_status="public").validate(allow_public=True)

    def test_scheduled_video_requires_future_timezone_and_private(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        UploadMetadata("테스트", publish_at=future).validate()
        with self.assertRaises(ValueError):
            UploadMetadata("테스트", publish_at="2030-01-01T00:00:00").validate()
        with self.assertRaises(ValueError):
            UploadMetadata("테스트", privacy_status="unlisted", publish_at=future).validate()

    def test_upload_request_metadata_and_result(self):
        folder = Path(__file__).parent
        video = folder / f".tmp-upload-{__import__('os').getpid()}-success.mp4"
        video.write_bytes(b"fake mp4")
        try:
            request = MagicMock()
            request.next_chunk.side_effect = [(MagicMock(progress=lambda: .5), None), (None, {"id": "abc123"})]
            videos = MagicMock()
            videos.insert.return_value = request
            service = MagicMock()
            service.videos.return_value = videos
            progress = []
            uploader = YouTubeUploader(service, media_upload_factory=lambda *args, **kwargs: "media", sleep=lambda _: None)
            with patch("shorts_studio.upload.youtube.token_path", return_value=folder / ".tmp-token.json"):
                result = uploader.upload(video, UploadMetadata("테스트", tags=("한글",)), progress=progress.append)
            self.assertEqual(result["url"], "https://www.youtube.com/watch?v=abc123")
            body = videos.insert.call_args.kwargs["body"]
            self.assertEqual(body["snippet"]["tags"], ["한글"])
            self.assertEqual(body["status"]["privacyStatus"], "private")
            self.assertEqual(progress, [.5])
        finally:
            video.unlink(missing_ok=True)
            (folder / ".tmp-token.json").parent.joinpath("uploads.jsonl").unlink(missing_ok=True)

    def test_retries_transient_upload_error(self):
        folder = Path(__file__).parent
        video = folder / f".tmp-upload-{__import__('os').getpid()}-retry.mp4"
        video.write_bytes(b"fake mp4")
        try:
            retry = RuntimeError("temporary")
            retry.resp = MagicMock(status=503)
            request = MagicMock()
            request.next_chunk.side_effect = [retry, (None, {"id": "retry-id"})]
            service = MagicMock()
            service.videos.return_value.insert.return_value = request
            delays = []
            with patch("shorts_studio.upload.youtube.token_path", return_value=folder / ".tmp-token.json"):
                result = YouTubeUploader(service, media_upload_factory=lambda *a, **k: None, sleep=delays.append).upload(video, UploadMetadata("test"))
            self.assertEqual(result["video_id"], "retry-id")
            self.assertEqual(delays, [1])
        finally:
            video.unlink(missing_ok=True)
            (folder / "uploads.jsonl").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
