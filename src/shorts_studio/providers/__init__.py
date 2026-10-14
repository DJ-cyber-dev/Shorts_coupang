"""Contracts and adapters for configurable remote AI providers."""
from typing import Protocol
from pathlib import Path


class VideoAnalyzer(Protocol):
    def analyze(self, video: Path) -> dict: ...
