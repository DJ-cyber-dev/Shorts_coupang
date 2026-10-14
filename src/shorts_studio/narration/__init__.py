"""Korean narration, TTS, subtitle alignment and rendering."""
from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, text: str, output: Path) -> Path: ...
