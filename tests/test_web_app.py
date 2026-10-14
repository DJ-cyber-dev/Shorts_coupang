import json
import os
from pathlib import Path
import shutil
import threading
import time
import unittest
from uuid import uuid4
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from shorts_studio.jobs.history import JobHistory
from shorts_studio.products import Product, ProductMatch
from shorts_studio.providers.gemini import GeminiScriptSettings
from shorts_studio.ui.web_app import LocalJobManager, LocalWebServer


class LocalWebAppTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / "build" / f"_web-ui-test-{uuid4().hex}"
        self.root.mkdir(parents=True)
        self.manager = LocalJobManager(
            JobHistory(self.root / "jobs"), self.root / "uploads")
        self.server = LocalWebServer(("127.0.0.1", 0), self.manager)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        shutil.rmtree(self.root, ignore_errors=True)

    def request(self, path, *, method="GET", body=None, headers=None):
        request = Request(self.base + path, data=body, headers=headers or {}, method=method)
        with urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read()

    def test_serves_single_page_and_blocks_foreign_origin(self):
        status, _, html = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Shorts Studio", html)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/jobs", method="POST", body=b"{}", headers={
                "Content-Type": "application/json", "Origin": "http://attacker.example",
            })
        self.assertEqual(error.exception.code, 403)

    def test_gemini_connection_test_returns_model_without_secret(self):
        with patch("shorts_studio.providers.gemini.GeminiScriptSettings.load",
                   return_value=GeminiScriptSettings()), \
             patch("shorts_studio.providers.gemini.GeminiScriptSettings.get_secret", return_value="test-secret"), \
             patch("shorts_studio.providers.gemini.GeminiScriptClient.test_connection"):
            status, _, raw = self.request("/api/settings/script-ai/test", method="POST",
                body=b"{}", headers={"Content-Type": "application/json"})
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["model"], "gemini-3.8-flash")
        self.assertNotIn("secret", payload)

    def test_coupang_search_returns_ten_candidates_and_optional_metrics(self):
        from shorts_studio.products.coupang import CoupangCredentials, CoupangPartnersClient

        products = [Product(str(index), f"검색 후보 {index}", f"https://shop.example/{index}",
                            rank=index, review_count=index * 10 if index == 1 else None)
                    for index in range(1, 11)]
        with patch("shorts_studio.products.coupang.CoupangCredentials.load",
                   return_value=CoupangCredentials("a", "b")), \
             patch.object(CoupangPartnersClient, "search", return_value=products) as search:
            status, _, raw = self.request("/api/products/search", method="POST",
                body=json.dumps({"keyword": "무선청소기"}).encode(),
                headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        result = json.loads(raw)["products"]
        self.assertEqual(len(result), 10)
        self.assertEqual(search.call_args.kwargs["limit"], 10)
        self.assertEqual(result[0]["review_count"], 10)
        self.assertIsNone(result[0]["sales_count"])
        self.assertIsNone(result[-1]["review_count"])

    def test_gemini_settings_route_saves_model_without_returning_key(self):
        with patch.object(GeminiScriptSettings, "save") as save, \
             patch.object(LocalJobManager, "settings_snapshot",
                          return_value={"script_ai": {"provider": "gemini", "key_saved": False}}):
            status, _, raw = self.request("/api/settings/script-ai", method="POST",
                body=json.dumps({"model": "gemini-3.8-flash", "key_name": "SHORTS_GEMINI_API_KEY"}).encode(),
                headers={"Content-Type": "application/json"})
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertNotIn("secret", payload["settings"]["script_ai"])
        save.assert_called_once_with()

    def test_upload_pipeline_status_and_media_range(self):
        status, _, raw = self.request("/api/upload?name=sample.mp4", method="POST",
                                      body=b"fake source", headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 201)
        token = json.loads(raw)["token"]
        output = self.root / "result.mp4"

        def fake_convert(source, target, **kwargs):
            self.assertTrue(Path(source).is_file())
            kwargs["status"]("전체 화면 문자 탐지·제거 중…")
            kwargs["progress"](0.5)
            target.write_bytes(b"completed-video")
            target.with_suffix(".preview.jpg").write_bytes(b"preview-image")
            target.with_suffix(".report.json").write_text(json.dumps({
                "frames": 12, "frames_with_text": 4, "method": "fake-removal",
            }), encoding="utf-8")

        with patch("shorts_studio.pipeline.convert_source", side_effect=fake_convert):
            status, _, raw = self.request("/api/jobs", method="POST",
                body=json.dumps({"source": token, "output": str(output), "mode": "pad"}).encode(),
                headers={"Content-Type": "application/json"})
            self.assertEqual(status, 202)
            job_id = json.loads(raw)["id"]
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                _, _, raw = self.request("/api/status")
                job = json.loads(raw)["job"]
                if job and job["status"] != "running":
                    break
                time.sleep(0.03)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["report"]["frames_with_text"], 4)
        analysis = {"summary": "테스트 분석", "scenes": [], "product_keywords": ["테스트"]}
        with patch("shorts_studio.pipeline.analyze_source", return_value=analysis):
            status, _, _ = self.request(f"/api/jobs/{job_id}/analyze", method="POST", body=b"{}",
                                        headers={"Content-Type": "application/json"})
            self.assertEqual(status, 202)
            job = self._wait_job_stage("analyze_completed")
        self.assertEqual(job["analysis"]["summary"], "테스트 분석")
        script = {"title": "테스트", "hook": "시작", "segments": [{"narration": "문장"}], "cta": "완료", "product_keywords": []}
        with patch("shorts_studio.narration.script.KoreanShortsScriptWriter.__init__", return_value=None), \
                patch("shorts_studio.narration.script.KoreanShortsScriptWriter.generate", return_value=script):
            payload = {"analysis": analysis, "duration_sec": 15, "tone": "friendly", "call_to_action": ""}
            status, _, _ = self.request(f"/api/jobs/{job_id}/script", method="POST",
                                        body=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            self.assertEqual(status, 202)
            job = self._wait_job_stage("script_completed")
        self.assertEqual(job["script"]["title"], "테스트")
        self.manager._product_matches = {"p1": ProductMatch(Product("p1", "테스트 상품", "https://shop.example/p1", 12000,
                                                                          affiliate_url="https://shop.example/p1?ref=x"),
                                                              0.9, ("테스트",))}
        status, _, raw = self.request(f"/api/jobs/{job_id}/product", method="POST",
                                      body=b'{"product_id":"p1"}', headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["script"]["product"]["id"], "p1")
        status, headers, video = self.request(f"/api/jobs/{job_id}/video", headers={"Range": "bytes=0-4"})
        self.assertEqual(status, 206)
        self.assertEqual(video, b"compl")
        self.assertEqual(headers["Content-Range"], "bytes 0-4/15")
        status, _, preview = self.request(f"/api/jobs/{job_id}/preview")
        self.assertEqual(status, 200)
        self.assertEqual(preview, b"preview-image")

        def fake_render(_renderer, _source, _script, target):
            target.write_bytes(b"final-video")
            target.with_suffix(".srt").write_text("captions", encoding="utf-8")
            target.with_suffix(".voice.wav").write_bytes(b"voice")
            target.with_suffix(".narration.json").write_text("{}", encoding="utf-8")
            return target

        with patch("shorts_studio.narration.render.NarrationRenderer.__init__", return_value=None), \
                patch("shorts_studio.narration.render.NarrationRenderer.render", fake_render):
            status, _, _ = self.request(f"/api/jobs/{job_id}/render", method="POST",
                body=json.dumps({"script": script}).encode(), headers={"Content-Type": "application/json"})
            self.assertEqual(status, 202)
            job = self._wait_job_stage("render_completed")
        self.assertTrue(job["final_video_url"].endswith("/final"))
        status, _, final_video = self.request(f"/api/jobs/{job_id}/final", headers={"Range": "bytes=0-4"})
        self.assertEqual(status, 206)
        self.assertEqual(final_video, b"final")

        oauth = {"installed": {"client_id": "id", "client_secret": "secret",
                                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                "token_uri": "https://oauth2.googleapis.com/token"}}
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "local-app-data")}):
            self.request("/api/settings/youtube-oauth", method="POST",
                         body=json.dumps({"oauth_json": json.dumps(oauth)}).encode(),
                         headers={"Content-Type": "application/json"})
            upload_result = {"video_id": "abc123", "url": "https://www.youtube.com/watch?v=abc123", "privacy_status": "private"}
            with patch("shorts_studio.upload.youtube.authenticated_service", return_value=object()), \
                    patch("shorts_studio.upload.youtube.YouTubeUploader.upload", return_value=upload_result):
                status, _, _ = self.request(f"/api/jobs/{job_id}/upload", method="POST",
                    body=json.dumps({"title": "테스트 업로드", "privacy_status": "private"}).encode(),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(status, 202)
                job = self._wait_job_stage("upload_completed")
        self.assertEqual(job["upload_receipt"]["video_id"], "abc123")

    def _wait_job_stage(self, expected_stage):
        deadline = time.monotonic() + 3
        job = None
        while time.monotonic() < deadline:
            _, _, raw = self.request("/api/status")
            job = json.loads(raw)["job"]
            if job and job.get("stage") == expected_stage:
                return job
            if job and job.get("status") == "failed":
                self.fail(job.get("error", "action failed"))
            time.sleep(0.03)
        self.fail(f"Timed out waiting for {expected_stage}: {job}")

    def test_upload_rejects_unsupported_file_type_and_url(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/upload?name=notes.txt", method="POST", body=b"text",
                         headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(error.exception.code, 400)

    def test_settings_are_editable_without_returning_secret_values(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "local-app-data")}):
            status, _, raw = self.request("/api/settings")
            self.assertEqual(status, 200)
            snapshot = json.loads(raw)
            self.assertIn("key_saved", snapshot["ai"])
            self.assertNotIn("secret", snapshot["ai"])
            self.assertEqual(snapshot["script_ai"]["model"], "gemini-3.8-flash")
            self.assertIn({"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash · 권장"}, snapshot["script_ai"]["models"])
            status, _, raw = self.request("/api/settings/tts", method="POST",
                body=json.dumps({"provider": "windows-local", "voice": "Microsoft Heami Desktop - Korean"}).encode(),
                headers={"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            tts = json.loads(raw)["settings"]["tts"]
            self.assertEqual(tts["provider"], "windows-local")
            self.assertNotIn("key_saved", tts)
            self.assertNotIn("secret", tts)
            status, _, raw = self.request("/api/settings/updates", method="POST",
                body=json.dumps({"repository": "owner/repo", "public_key": ""}).encode(),
                headers={"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["settings"]["updates"]["repository"], "owner/repo")
            oauth = {"installed": {"client_id": "id", "client_secret": "secret", "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
            status, _, raw = self.request("/api/settings/youtube-oauth", method="POST",
                body=json.dumps({"oauth_json": json.dumps(oauth)}).encode(),
                headers={"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(raw)["saved"])
            stored = self.root / "local-app-data" / "ShortsStudio" / "youtube-oauth-client.json"
            self.assertTrue(stored.is_file())
        with self.assertRaises(HTTPError) as error:
            self.request("/api/jobs", method="POST",
                         body=b'{"source":"https://example.com/video.mp4","output":"x.mp4"}',
                         headers={"Content-Type": "application/json"})
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
