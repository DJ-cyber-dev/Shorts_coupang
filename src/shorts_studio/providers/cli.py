import argparse
import json
from pathlib import Path

from shorts_studio.core import MediaError
from .settings import ProviderSettings
from .vision import OpenAICompatibleVisionAnalyzer


def main():
    parser = argparse.ArgumentParser(description="영상 frame 샘플을 설정된 AI Provider로 분석")
    parser.add_argument("video", type=Path, help="분석할 로컬 영상")
    args = parser.parse_args()
    try:
        settings = ProviderSettings.load()
        result = OpenAICompatibleVisionAnalyzer(settings).analyze(args.video)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (MediaError, OSError, ValueError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
