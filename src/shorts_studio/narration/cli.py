import argparse
import json
from pathlib import Path

from shorts_studio.core import MediaError
from .script import KoreanShortsScriptWriter


def main():
    parser = argparse.ArgumentParser(description="영상 분석 JSON에서 한국어 Shorts 대본 초안 생성")
    parser.add_argument("analysis", type=Path, help="AI 분석 JSON 파일")
    parser.add_argument("--duration", type=int, default=30, help="목표 길이(10~60초)")
    parser.add_argument("--tone", choices=["friendly", "review", "informative", "hook"], default="friendly")
    parser.add_argument("--cta", default="", help="마무리 행동 문구")
    parser.add_argument("--output", type=Path, help="저장할 JSON 경로 (생략하면 화면 출력)")
    args = parser.parse_args()
    try:
        analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
        result = KoreanShortsScriptWriter().generate(
            analysis, duration_sec=args.duration, tone=args.tone, call_to_action=args.cta)
        document = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            if args.output.exists():
                raise MediaError("기존 파일을 덮어쓰지 않습니다. 다른 출력 경로를 지정하세요.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(document, encoding="utf-8")
            print(args.output.resolve())
        else:
            print(document, end="")
    except (MediaError, OSError, ValueError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
