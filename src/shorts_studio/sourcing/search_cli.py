import argparse
import json
from dataclasses import asdict

from shorts_studio.core import MediaError
from .youtube_search import YouTubeSourceSearch


def main():
    parser = argparse.ArgumentParser(description="Creative Commons Shorts source candidates 검색")
    parser.add_argument("keyword", help="검색 키워드")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        results = YouTubeSourceSearch().search(args.keyword, limit=args.limit)
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    except (MediaError, OSError, ValueError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
