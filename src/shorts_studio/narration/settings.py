from dataclasses import dataclass
import json
import os
from pathlib import Path
import tomllib

from shorts_studio.providers.settings import settings_path


@dataclass(frozen=True)
class TTSSettings:
    provider: str = "windows-local"
    voice: str = "Microsoft Heami Desktop - Korean"
    speed: float = 1.0

    def validate(self):
        if any(not isinstance(value, str) or len(value) > 500 for value in (self.provider, self.voice)):
            raise ValueError("TTS 설정 값이 올바르지 않습니다.")
        if self.provider not in {"disabled", "windows-local"}:
            raise ValueError("지원하지 않는 TTS 방식입니다. Windows 로컬 음성만 지원합니다.")
        if not self.voice.strip():
            raise ValueError("Windows 음성 이름이 필요합니다.")
        if not isinstance(self.speed, (int, float)) or not 0.25 <= self.speed <= 4.0:
            raise ValueError("TTS speed는 0.25~4.0이어야 합니다.")

    @staticmethod
    def config_path() -> Path:
        return settings_path().with_name("tts.toml")

    @classmethod
    def load(cls, path: Path | None = None):
        path = Path(path) if path else cls.config_path()
        if not path.exists():
            return cls()
        with path.open("rb") as file:
            values = tomllib.load(file).get("tts", {})
        allowed = {"provider", "model", "base_url", "key_name", "voice", "speed"}
        if values.keys() - allowed:
            raise ValueError("TTS 설정 필드가 올바르지 않습니다.")
        # Migrate older API-backed TTS settings to the new offline Windows voice.
        if values.get("provider") == "openai-compatible":
            values = {"provider": "windows-local", "voice": "Microsoft Heami Desktop - Korean"}
        else:
            values = {name: value for name, value in values.items() if name in {"provider", "voice", "speed"}}
        settings = cls(**values)
        settings.validate()
        return settings

    def save(self, path: Path | None = None):
        self.validate()
        path = Path(path) if path else self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = (("provider", self.provider), ("voice", self.voice), ("speed", self.speed))
        content = "[tts]\n" + "".join(f"{name} = {json.dumps(value, ensure_ascii=False)}\n" for name, value in rows)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
