"""Non-secret GitHub release and update verification settings."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class GitHubUpdateSettings:
    repository: str = ""
    public_key: str = ""

    @staticmethod
    def config_path() -> Path:
        root = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".config")
        return root / "ShortsStudio" / "updates.toml"

    def validate(self):
        if len(self.repository) > 220 or len(self.public_key) > 100:
            raise ValueError("업데이트 설정 길이가 제한을 초과했습니다.")
        if self.repository and not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", self.repository):
            raise ValueError("GitHub 저장소는 owner/repo 형식이어야 합니다.")
        if self.public_key:
            import base64
            try:
                if len(base64.b64decode(self.public_key, validate=True)) != 32:
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise ValueError("Ed25519 공개키는 32-byte raw key의 base64여야 합니다.") from exc

    @classmethod
    def load(cls, path: Path | None = None):
        path = Path(path) if path else cls.config_path()
        if not path.exists():
            return cls()
        with path.open("rb") as stream:
            values = tomllib.load(stream).get("updates", {})
        if not isinstance(values, dict) or values.keys() - {"repository", "public_key"}:
            raise ValueError("업데이트 설정 필드가 올바르지 않습니다.")
        if any(not isinstance(value, str) for value in values.values()):
            raise ValueError("업데이트 설정은 문자열이어야 합니다.")
        settings = cls(**values)
        settings.validate()
        return settings

    def save(self, path: Path | None = None):
        self.validate()
        path = Path(path) if path else self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = ("[updates]\n"
                   f"repository = {json.dumps(self.repository)}\n"
                   f"public_key = {json.dumps(self.public_key)}\n")
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
