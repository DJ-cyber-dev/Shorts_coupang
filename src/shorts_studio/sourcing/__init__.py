"""Local source now; licensed remote source adapters in a later phase."""
from pathlib import Path
from typing import Protocol


class VideoSource(Protocol):
    def acquire(self, reference: str) -> Path: ...


class LocalSource:
    def acquire(self, reference: str) -> Path:
        path = Path(reference).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
