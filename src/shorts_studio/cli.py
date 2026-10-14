import argparse
from pathlib import Path
from .core import MediaError
from .pipeline import convert_source


def main():
    parser = argparse.ArgumentParser(description="9:16 무음 MP4 변환")
    parser.add_argument("source", help="로컬 파일 또는 영상 URL")
    parser.add_argument("--url", action="store_true", help="URL에서 다운로드 후 변환")
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["pad", "crop"], default="pad")
    parser.add_argument("--hd", action="store_true", help="1080x1920 출력")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    try:
        result = convert_source(args.source, args.output, is_url=args.url, mode=args.mode,
                                      width=1080 if args.hd else 720,
                                      height=1920 if args.hd else 1280, threads=args.threads)
        print(result.resolve())
    except (MediaError, OSError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
