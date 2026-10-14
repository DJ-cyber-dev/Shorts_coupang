"""Verify and stage signed GitHub Release updates for Shorts Studio."""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from shorts_studio import __version__
from shorts_studio.core import MediaError
from .settings import GitHubUpdateSettings


ASSET_NAME = "ShortsStudio-Portable.zip"
MANIFEST_NAME = "shorts-studio-update.json"
HELPER_NAME = "Apply-ShortsStudioUpdate.ps1"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 1_500_000_000
MANIFEST_DOMAIN = b"shorts-studio-update-v1\n"
VERSION_RE = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _is_windows() -> bool:
    """Keep platform gating small and easy to exercise in cross-platform tests."""
    return os.name == "nt"


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    asset_url: str
    sha256: str
    notes: str = ""


def _version_key(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        raise MediaError("업데이트 버전은 vMAJOR.MINOR.PATCH 형식이어야 합니다.")
    return tuple(map(int, match.groups()))


def _signed_message(version: str, asset_name: str, digest: str) -> bytes:
    return MANIFEST_DOMAIN + f"{version}\n{asset_name}\n{digest.lower()}\n".encode("ascii")


class GitHubReleaseUpdater:
    def __init__(self, repository: str | None = None, public_key: str | None = None, *,
                 timeout: int = 20, opener=urllib.request.urlopen):
        configured_repository = repository or os.getenv("SHORTS_STUDIO_REPOSITORY")
        configured_key = public_key or os.getenv("SHORTS_STUDIO_UPDATE_PUBLIC_KEY")
        settings = GitHubUpdateSettings.load() if not configured_repository or not configured_key else None
        self.repository = (configured_repository or settings.repository).strip()
        self.public_key = (configured_key or settings.public_key).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", self.repository):
            raise MediaError("SHORTS_STUDIO_REPOSITORY에 GitHub owner/repo를 설정하세요.")
        try:
            key_bytes = base64.b64decode(self.public_key, validate=True)
            if len(key_bytes) != 32:
                raise ValueError("wrong Ed25519 key size")
            self._key = Ed25519PublicKey.from_public_bytes(key_bytes)
        except (ValueError, TypeError) as exc:
            raise MediaError("SHORTS_STUDIO_UPDATE_PUBLIC_KEY에 유효한 base64 Ed25519 공개키를 설정하세요.") from exc
        if not 5 <= timeout <= 60:
            raise ValueError("GitHub update timeout은 5~60초여야 합니다.")
        self.timeout = timeout
        self.opener = opener

    def _read(self, url: str, maximum: int, *, accept: str) -> bytes:
        request = urllib.request.Request(url, headers={
            "Accept": accept,
            "User-Agent": "ShortsStudio-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with self.opener(request, timeout=self.timeout) as response:
                data = response.read(maximum + 1)
        except urllib.error.HTTPError as exc:
            raise MediaError(f"GitHub Release 조회에 실패했습니다 (HTTP {exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MediaError(f"GitHub Release에 연결할 수 없습니다: {type(exc).__name__}") from exc
        if len(data) > maximum:
            raise MediaError("GitHub 업데이트 응답 크기 제한을 초과했습니다.")
        return data

    def check_latest(self) -> UpdateRelease | None:
        api_url = f"https://api.github.com/repos/{self.repository}/releases/latest"
        try:
            release = json.loads(self._read(api_url, MAX_MANIFEST_BYTES, accept="application/vnd.github+json"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaError("GitHub Release 응답을 해석하지 못했습니다.") from exc
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            raise MediaError("최신 GitHub Release 응답이 올바르지 않습니다.")
        tag = release.get("tag_name")
        version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else tag
        latest_key = _version_key(version) if isinstance(version, str) else None
        current_key = _version_key(__version__)
        if latest_key is None or latest_key <= current_key:
            return None
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise MediaError("GitHub Release에 업데이트 파일이 없습니다.")
        asset_urls = {}
        for item in assets:
            if isinstance(item, dict) and item.get("name") in {ASSET_NAME, MANIFEST_NAME}:
                url = item.get("browser_download_url")
                if isinstance(url, str) and url.startswith("https://github.com/"):
                    asset_urls[item["name"]] = url
        if set(asset_urls) != {ASSET_NAME, MANIFEST_NAME}:
            raise MediaError(f"Release에 {ASSET_NAME} 및 서명 manifest가 필요합니다.")
        try:
            manifest = json.loads(self._read(asset_urls[MANIFEST_NAME], MAX_MANIFEST_BYTES,
                                             accept="application/octet-stream"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaError("업데이트 서명 manifest 형식이 올바르지 않습니다.") from exc
        if not isinstance(manifest, dict):
            raise MediaError("업데이트 서명 manifest 구조가 올바르지 않습니다.")
        digest = manifest.get("sha256")
        signature = manifest.get("signature")
        if manifest.get("version") != version or manifest.get("asset") != ASSET_NAME:
            raise MediaError("업데이트 manifest의 버전 또는 파일명이 Release와 일치하지 않습니다.")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise MediaError("업데이트 manifest의 SHA-256 형식이 올바르지 않습니다.")
        try:
            signature_bytes = base64.b64decode(signature, validate=True)
            self._key.verify(signature_bytes, _signed_message(version, ASSET_NAME, digest))
        except (ValueError, TypeError, InvalidSignature) as exc:
            raise MediaError("업데이트 서명이 올바르지 않습니다. 파일을 실행하지 않았습니다.") from exc
        notes = release.get("body")
        return UpdateRelease(version, asset_urls[ASSET_NAME], digest.lower(),
                             notes[:4000] if isinstance(notes, str) else "")

    @classmethod
    def settings(cls) -> GitHubUpdateSettings:
        return GitHubUpdateSettings.load()

    def download_and_launch(self, release: UpdateRelease, *, install_dir: Path | None = None,
                            data_dir: Path | None = None, process_id: int | None = None) -> Path:
        if not _is_windows():
            raise MediaError("서명 업데이트 적용은 Windows 설치본에서만 지원합니다.")
        _version_key(release.version)
        if (not release.asset_url.startswith(f"https://github.com/{self.repository}/releases/download/")
                or not re.fullmatch(r"[0-9a-f]{64}", release.sha256)):
            raise MediaError("서명된 GitHub 업데이트 정보가 올바르지 않습니다.")
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        install = Path(install_dir) if install_dir else local / "Programs" / "ShortsStudio"
        data = Path(data_dir) if data_dir else local / "ShortsStudio"
        if not (install / "ShortsStudio.exe").is_file():
            raise MediaError("설치된 앱 경로를 찾지 못했습니다. Portable 실행본은 자동 업데이트를 지원하지 않습니다.")
        update_dir = data / "updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        archive = update_dir / f"ShortsStudio-{release.version}.zip"
        digest = hashlib.sha256()
        request = urllib.request.Request(release.asset_url, headers={"User-Agent": "ShortsStudio-Updater"})
        try:
            with self.opener(request, timeout=self.timeout) as response, archive.open("wb") as output:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise MediaError("업데이트 파일 크기 제한을 초과했습니다.")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != release.sha256:
                raise MediaError("업데이트 파일의 SHA-256이 서명 manifest와 일치하지 않습니다.")
            with zipfile.ZipFile(archive) as bundle:
                infos = [item for item in bundle.infolist() if item.filename.replace("\\", "/") == HELPER_NAME]
                if len(infos) != 1 or infos[0].file_size > 128 * 1024:
                    raise MediaError("업데이트에 안전한 적용 helper가 없습니다.")
                helper = update_dir / HELPER_NAME
                helper.write_bytes(bundle.read(infos[0]))
        except MediaError:
            archive.unlink(missing_ok=True)
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, zipfile.BadZipFile) as exc:
            archive.unlink(missing_ok=True)
            raise MediaError(f"업데이트 파일을 받을 수 없습니다: {type(exc).__name__}") from exc
        if digest.hexdigest() != release.sha256:
            archive.unlink(missing_ok=True)
            raise MediaError("업데이트 파일 검증에 실패했습니다.")
        script = update_dir / HELPER_NAME
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", str(script), "-WaitPid", str(process_id or os.getpid()),
            "-Archive", str(archive), "-InstallDir", str(install), "-DataDir", str(data),
        ]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            subprocess.Popen(command, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
                             close_fds=True)
        except OSError as exc:
            archive.unlink(missing_ok=True)
            raise MediaError("업데이트 적용 프로그램을 시작하지 못했습니다.") from exc
        return archive
