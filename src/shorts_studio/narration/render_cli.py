import argparse
import json
from pathlib import Path

from shorts_studio.core import MediaError
from .render import NarrationRenderer


def main():
    parser = argparse.ArgumentParser(description="필수 문자 제거를 거친 영상에 한국어 TTS와 자막을 합성")
    parser.add_argument("cleaned_video", type=Path, help="문자 제거 output MP4")
    parser.add_argument("script", type=Path, help="한국어 대본 JSON")
    parser.add_argument("output", type=Path, help="최종 MP4 (audio·burn-in 자막 포함)")
    args = parser.parse_args()
    try:
        script = json.loads(args.script.read_text(encoding="utf-8"))
        output = NarrationRenderer().render(args.cleaned_video, script, args.output)
        print(output.resolve())
    except (MediaError, OSError, ValueError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
