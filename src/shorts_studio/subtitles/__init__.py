"""Caption contract; transcription, timing and burn-in are phase 3 work."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


class CaptionProvider(Protocol):
    def align(self, text: str, audio_path: str) -> list[Caption]: ...
