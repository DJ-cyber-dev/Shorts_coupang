from dataclasses import dataclass
import json
from pathlib import Path
import os
import re
import tomllib
from urllib.parse import urlparse


def settings_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".config")
    return root / "ShortsStudio" / "config.toml"


@dataclass(frozen=True)
class ProviderSettings:
    provider: str = "disabled"
    model: str = ""
    base_url: str = ""
    key_name: str = "SHORTS_AI_KEY"

    def validate(self):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", self.provider):
            raise ValueError("Provider 이름은 영문 소문자, 숫자, 하이픈, 밑줄만 사용할 수 있습니다.")
        if any(not isinstance(value, str) or len(value) > 500 for value in
               (self.model, self.base_url, self.key_name)):
            raise ValueError("Provider 설정 값이 올바르지 않습니다.")
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", self.key_name):
            raise ValueError("API key 환경 변수 이름이 올바르지 않습니다.")
        if self.provider != "disabled":
            parsed = urlparse(self.base_url)
            local_http = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if parsed.scheme != "https" and not (parsed.scheme == "http" and local_http):
                raise ValueError("Provider URL은 HTTPS여야 합니다 (로컬 주소는 HTTP 허용).")
            if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or not self.model.strip():
                raise ValueError("활성 Provider에는 Base URL과 model이 필요합니다.")

    @classmethod
    def load(cls, path: Path | None = None):
        path = Path(path) if path else settings_path()
        if not path.exists():
            return cls()
        with path.open("rb") as file:
            values = tomllib.load(file).get("ai", {})
        allowed = {"provider", "model", "base_url", "key_name"}
        if values.keys() - allowed or any(not isinstance(v, str) for v in values.values()):
            raise ValueError("AI 설정 필드 또는 값이 올바르지 않습니다. 키 원문을 설정 파일에 저장하지 마세요.")
        settings = cls(**values)
        settings.validate()
        return settings

    def save(self, path: Path | None = None):
        self.validate()
        path = Path(path) if path else settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # JSON string literals are valid TOML basic strings; never serialize a key here.
        content = "[ai]\n" + "".join(
            f"{name} = {json.dumps(value, ensure_ascii=False)}\n"
            for name, value in (("provider", self.provider), ("model", self.model),
                                ("base_url", self.base_url), ("key_name", self.key_name)))
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)

    def store_secret(self, secret: str):
        if not secret.strip():
            raise ValueError("API key가 비어 있습니다.")
        if os.name != "nt":
            raise RuntimeError(f"Windows 이외 환경에서는 {self.key_name} 환경 변수로 API key를 설정하세요.")
        from keyring.backends.Windows import WinVaultKeyring
        WinVaultKeyring().set_password("shorts-studio", self.key_name, secret)

    def get_secret(self) -> str | None:
        if self.provider == "disabled":
            return None
        value = os.getenv(self.key_name)
        if value:
            return value
        if os.name == "nt":
            # Windows Credential Manager backend를 명시해 평문 backend 사용 방지.
            try:
                from keyring.backends.Windows import WinVaultKeyring
            except ModuleNotFoundError:
                # The secrets extra is optional; settings UI must still load without it.
                return None
            return WinVaultKeyring().get_password("shorts-studio", self.key_name)
        return None
