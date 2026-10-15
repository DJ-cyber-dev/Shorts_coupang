"""Local resource limits for text-removal processing."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path

from shorts_studio.providers.settings import settings_path


def available_cpu_threads() -> int:
    return max(1, int(os.cpu_count() or 1))


@dataclass(frozen=True)
class ResourceSettings:
    cpu_threads: int = field(default_factory=lambda: min(2, available_cpu_threads()))
    background_priority: bool = True

    def validate(self) -> None:
        if (isinstance(self.cpu_threads, bool) or not isinstance(self.cpu_threads, int)
                or not 1 <= self.cpu_threads <= available_cpu_threads()):
            raise ValueError(f"CPU thread 상한은 1~{available_cpu_threads()} 범위여야 합니다.")
        if not isinstance(self.background_priority, bool):
            raise ValueError("백그라운드 우선순위 설정이 올바르지 않습니다.")

    @staticmethod
    def config_path() -> Path:
        return settings_path().parent / "resources.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "ResourceSettings":
        path = Path(path) if path else cls.config_path()
        if not path.exists():
            settings = cls()
            settings.validate()
            return settings
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("성능 설정 파일을 읽을 수 없습니다.") from exc
        if not isinstance(values, dict) or values.keys() - {"cpu_threads", "background_priority"}:
            raise ValueError("성능 설정 항목이 올바르지 않습니다.")
        settings = cls(**values)
        # A per-user config may be copied to a PC with fewer logical processors.
        if isinstance(settings.cpu_threads, int) and not isinstance(settings.cpu_threads, bool):
            settings = cls(min(settings.cpu_threads, available_cpu_threads()), settings.background_priority)
        settings.validate()
        return settings

    def save(self, path: Path | None = None) -> None:
        self.validate()
        path = Path(path) if path else self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps({
            "cpu_threads": self.cpu_threads,
            "background_priority": self.background_priority,
        }, indent=2), encoding="utf-8")
        os.replace(temporary, path)
