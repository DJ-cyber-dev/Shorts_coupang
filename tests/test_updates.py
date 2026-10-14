import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shorts_studio import __version__
from shorts_studio.core import MediaError
from shorts_studio.updates.github_release import (
    ASSET_NAME, HELPER_NAME, MANIFEST_DOMAIN, MANIFEST_NAME, GitHubReleaseUpdater, UpdateRelease,
)
from shorts_studio.updates.settings import GitHubUpdateSettings


class GitHubUpdateTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        raw_public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public = base64.b64encode(raw_public).decode("ascii")

    def _client(self, responses, **kwargs):
        remaining = list(responses)
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = remaining.pop(0)
            return response

        return GitHubReleaseUpdater("owner/project", self.public, opener=opener, **kwargs), requests

    @staticmethod
    def _next_version():
        major, minor, patch = (int(part) for part in __version__.split("."))
        return f"{major}.{minor}.{patch + 1}"

    def _release(self, *, version=None, signature_valid=True):
        version = version or self._next_version()
        package = b"signed portable package bytes"
        digest = hashlib.sha256(package).hexdigest()
        message = MANIFEST_DOMAIN + f"{version}\n{ASSET_NAME}\n{digest}\n".encode("ascii")
        signature = self.private.sign(message)
        if not signature_valid:
            signature = b"x" * 64
        manifest = json.dumps({
            "version": version,
            "asset": ASSET_NAME,
            "sha256": digest,
            "signature": base64.b64encode(signature).decode("ascii"),
        }).encode()
        metadata = json.dumps({
            "tag_name": "v" + version,
            "draft": False,
            "prerelease": False,
            "body": "Bug fixes",
            "assets": [
                {"name": ASSET_NAME, "browser_download_url": f"https://github.com/owner/project/releases/download/v{version}/ShortsStudio-Portable.zip"},
                {"name": MANIFEST_NAME, "browser_download_url": f"https://github.com/owner/project/releases/download/v{version}/shorts-studio-update.json"},
            ],
        }).encode()
        return metadata, manifest, package, digest

    def test_checks_signed_release_manifest_and_returns_update(self):
        metadata, manifest, _, digest = self._release()
        client, requests = self._client([metadata, manifest])
        result = client.check_latest()
        self.assertEqual(result.version, self._next_version())
        self.assertEqual(result.sha256, digest)
        self.assertEqual(result.notes, "Bug fixes")
        self.assertEqual(len(requests), 2)
        self.assertIn("/repos/owner/project/releases/latest", requests[0][0].full_url)
        self.assertEqual(requests[0][1], 20)

    def test_rejects_invalid_signature_and_external_asset_urls(self):
        metadata, manifest, _, _ = self._release(signature_valid=False)
        client, _ = self._client([metadata, manifest])
        with self.assertRaisesRegex(MediaError, "서명이 올바르지 않습니다"):
            client.check_latest()

        metadata, manifest, _, _ = self._release()
        payload = json.loads(metadata)
        payload["assets"][0]["browser_download_url"] = "https://attacker.invalid/archive.zip"
        client, _ = self._client([json.dumps(payload).encode()])
        with self.assertRaisesRegex(MediaError, "Release에"):
            client.check_latest()

    def test_current_version_does_not_fetch_manifest(self):
        metadata = json.dumps({"tag_name": "v" + __version__, "draft": False, "prerelease": False}).encode()
        client, requests = self._client([metadata])
        self.assertIsNone(client.check_latest())
        self.assertEqual(len(requests), 1)

    def test_download_hash_mismatch_is_removed_before_launch(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [b"tampered", b""]
        client = GitHubReleaseUpdater("owner/project", self.public, opener=lambda *_args, **_kwargs: response)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "Programs" / "ShortsStudio"
            install.mkdir(parents=True)
            (install / "ShortsStudio.exe").write_bytes(b"app")
            data = root / "ShortsStudio"
            release = UpdateRelease(
                "0.2.1", "https://github.com/owner/project/releases/download/v0.2.1/ShortsStudio-Portable.zip",
                "0" * 64,
            )
            from unittest.mock import patch
            with patch("shorts_studio.updates.github_release._is_windows", return_value=True), \
                 patch("shorts_studio.updates.github_release.subprocess.Popen") as launch:
                with self.assertRaisesRegex(MediaError, "SHA-256"):
                    client.download_and_launch(release, install_dir=install, data_dir=data)
            launch.assert_not_called()
            self.assertFalse((data / "updates" / "ShortsStudio-0.2.1.zip").exists())

    def test_verified_download_extracts_only_helper_and_launches_updater(self):
        helper_text = "# signed test helper\n"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle_path = root / "bundle.zip"
            with zipfile.ZipFile(bundle_path, "w") as bundle:
                bundle.writestr(HELPER_NAME, helper_text)
                bundle.writestr("unsafe.txt", "not extracted")
            content = bundle_path.read_bytes()
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.side_effect = [content, b""]
            client = GitHubReleaseUpdater("owner/project", self.public, opener=lambda *_args, **_kwargs: response)
            install = root / "Programs" / "ShortsStudio"
            install.mkdir(parents=True)
            (install / "ShortsStudio.exe").write_bytes(b"app")
            release = UpdateRelease(
                "0.2.1", "https://github.com/owner/project/releases/download/v0.2.1/ShortsStudio-Portable.zip",
                hashlib.sha256(content).hexdigest(),
            )
            from unittest.mock import patch
            from types import SimpleNamespace
            with patch("shorts_studio.updates.github_release._is_windows", return_value=True), \
                 patch("shorts_studio.updates.github_release.subprocess.STARTUPINFO",
                       return_value=SimpleNamespace(dwFlags=0), create=True), \
                 patch("shorts_studio.updates.github_release.subprocess.STARTF_USESHOWWINDOW", 1, create=True), \
                 patch("shorts_studio.updates.github_release.subprocess.CREATE_NO_WINDOW", 2, create=True), \
                 patch("shorts_studio.updates.github_release.subprocess.Popen") as launch:
                archive = client.download_and_launch(release, install_dir=install, data_dir=root / "ShortsStudio", process_id=123)
            launch.assert_called_once()
            helper = root / "ShortsStudio" / "updates" / HELPER_NAME
            self.assertEqual(helper.read_text(encoding="utf-8"), helper_text)
            self.assertTrue(archive.is_file())
            self.assertIn("123", launch.call_args.args[0])

    def test_settings_round_trip_and_reject_invalid_public_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "updates.toml"
            settings = GitHubUpdateSettings("owner/project", self.public)
            settings.save(path)
            self.assertEqual(GitHubUpdateSettings.load(path), settings)
            with self.assertRaisesRegex(ValueError, "공개키"):
                GitHubUpdateSettings("owner/project", "not-base64").save(path)

    def test_release_manifest_builder_signs_archive_and_refuses_repo_private_key(self):
        script = Path(__file__).parents[1] / "scripts" / "create-update-manifest.py"
        spec = importlib.util.spec_from_file_location("create_update_manifest", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key_path = root / "release.pem"
            key_path.write_bytes(self.private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(b"test-passphrase"),
            ))
            archive = root / ASSET_NAME
            archive.write_bytes(b"release payload")
            output = root / MANIFEST_NAME
            from unittest.mock import patch
            with patch.object(module.getpass, "getpass", return_value="test-passphrase"):
                module.create_manifest("0.2.1", archive, key_path, output)
            manifest = json.loads(output.read_text(encoding="utf-8"))
            expected_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(manifest["sha256"], expected_hash)
            self.private.public_key().verify(
                base64.b64decode(manifest["signature"]),
                MANIFEST_DOMAIN + f"0.2.1\n{ASSET_NAME}\n{expected_hash}\n".encode("ascii"),
            )
            with self.assertRaisesRegex(ValueError, "outside the repository"):
                module.create_manifest("0.2.1", archive, script, output)

    def test_release_version_script_updates_runtime_package_and_installer(self):
        script = Path(__file__).parents[1] / "scripts" / "set-version.py"
        spec = importlib.util.spec_from_file_location("set_shorts_version", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "src/shorts_studio").mkdir(parents=True)
            (root / "installer").mkdir()
            (root / "pyproject.toml").write_text('version = "0.2.0"\n', encoding="utf-8")
            (root / "src/shorts_studio/__init__.py").write_text('__version__ = "0.2.0"\n', encoding="utf-8")
            (root / "installer/ShortsStudio.iss").write_text("AppVersion=0.2.0\n", encoding="utf-8")
            (root / "README.md").write_text("# Shorts Studio 0.2\n", encoding="utf-8")
            module.set_version(root, "0.2.1")
            self.assertIn('version = "0.2.1"', (root / "pyproject.toml").read_text(encoding="utf-8"))
            self.assertIn('__version__ = "0.2.1"', (root / "src/shorts_studio/__init__.py").read_text(encoding="utf-8"))
            self.assertIn("AppVersion=0.2.1", (root / "installer/ShortsStudio.iss").read_text(encoding="utf-8"))
            self.assertIn("# Shorts Studio 0.2.1", (root / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
