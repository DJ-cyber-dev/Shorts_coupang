"""Credential names and Windows Credential Manager access for TikTok Commercial API."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tomllib

from shorts_studio.providers.settings import settings_path


@dataclass(frozen=True)
class TikTokCommercialSettings:
    client_key_name: str = "SHORTS_TIKTOK_CLIENT_KEY"
    client_secret_name: str = "SHORTS_TIKTOK_CLIENT_SECRET"

    def validate(self):
        for name in (self.client_key_name, self.client_secret_name):
            if (not isinstance(name, str) or not name.isidentifier()
                    or name.upper() != name or len(name) > 80):
                raise ValueError("TikTok client credential 환경 변수 이름이 올바르지 않습니다.")
        if self.client_key_name == self.client_secret_name:
            raise ValueError("TikTok client key와 secret 환경 변수는 달라야 합니다.")

    @staticmethod
    def config_path() -> Path:
        return settings_path().with_name("tiktok-commercial.toml")

    @classmethod
    def load(cls, path: Path | None = None):
        path = Path(path) if path else cls.config_path()
        if not path.exists():
            return cls()
        with path.open("rb") as file:
            values = tomllib.load(file).get("tiktok_commercial", {})
        expected = {"client_key_name", "client_secret_name"}
        if values.keys() != expected or not all(isinstance(value, str) for value in values.values()):
            raise ValueError("TikTok Commercial API 설정의 credential 환경 변수 이름이 필요합니다.")
        settings = cls(values["client_key_name"], values["client_secret_name"])
        settings.validate()
        return settings

    def save(self, path: Path | None = None):
        self.validate()
        path = Path(path) if path else self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        content = ("[tiktok_commercial]\n"
                   f"client_key_name = {json.dumps(self.client_key_name)}\n"
                   f"client_secret_name = {json.dumps(self.client_secret_name)}\n")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)

    def get_secret(self, key: bool) -> str | None:
        name = self.client_key_name if key else self.client_secret_name
        value = os.getenv(name)
        if value:
            return value
        if os.name == "nt":
            try:
                from keyring.backends.Windows import WinVaultKeyring
            except ModuleNotFoundError:
                return None
            return WinVaultKeyring().get_password("shorts-studio-tiktok-commercial", name)
        return None

    def store_secrets(self, client_key: str, client_secret: str):
        self.validate()
        if not client_key.strip() or not client_secret.strip():
            raise ValueError("TikTok client key/secret을 모두 입력하세요.")
        if os.name != "nt":
            raise RuntimeError(
                f"Windows 이외 환경에서는 {self.client_key_name} 및 "
                f"{self.client_secret_name} 환경 변수를 설정하세요."
            )
        from keyring.backends.Windows import WinVaultKeyring
        vault = WinVaultKeyring()
        vault.set_password("shorts-studio-tiktok-commercial", self.client_key_name, client_key)
        vault.set_password("shorts-studio-tiktok-commercial", self.client_secret_name, client_secret)
