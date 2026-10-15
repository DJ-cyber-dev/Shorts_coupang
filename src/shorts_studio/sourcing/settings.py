from dataclasses import dataclass
import json
import os
from pathlib import Path
import tomllib

from shorts_studio.providers.settings import settings_path


@dataclass(frozen=True)
class YouTubeSearchSettings:
    key_name: str = "SHORTS_YOUTUBE_API_KEY"

    def validate(self):
        if not isinstance(self.key_name, str) or not self.key_name.isidentifier() or self.key_name.upper() != self.key_name:
            raise ValueError("YouTube API key 환경 변수 이름이 올바르지 않습니다.")

    @staticmethod
    def config_path() -> Path:
        return settings_path().with_name("sourcing.toml")

    @classmethod
    def load(cls, path: Path | None = None):
        path = Path(path) if path else cls.config_path()
        if not path.exists():
            return cls()
        with path.open("rb") as file:
            values = tomllib.load(file).get("youtube", {})
        if values.keys() != {"key_name"} or not isinstance(values["key_name"], str):
            raise ValueError("YouTube Search 설정에 key_name 환경 변수 이름이 필요합니다.")
        settings = cls(values["key_name"])
        settings.validate()
        return settings

    def save(self, path: Path | None = None):
        self.validate()
        path = Path(path) if path else self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text("[youtube]\nkey_name = " + json.dumps(self.key_name) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def get_secret(self) -> str | None:
        value = os.getenv(self.key_name)
        if value:
            return value
        if os.name == "nt":
            try:
                from keyring.backends.Windows import WinVaultKeyring
            except ModuleNotFoundError:
                return None
            return WinVaultKeyring().get_password("shorts-studio-youtube", self.key_name)
        return None

    def store_secret(self, secret: str):
        self.validate()
        if not secret.strip():
            raise ValueError("YouTube API key가 비어 있습니다.")
        if os.name != "nt":
            raise RuntimeError(f"Windows 이외 환경에서는 {self.key_name} 환경 변수로 API key를 설정하세요.")
        from keyring.backends.Windows import WinVaultKeyring
        WinVaultKeyring().set_password("shorts-studio-youtube", self.key_name, secret)
