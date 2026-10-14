"""Search the TikTok Commercial Content API's EEA advertising library."""
import argparse
from dataclasses import asdict
import json

from shorts_studio.core import MediaError
from .tiktok_commercial import EEA_COUNTRIES, TikTokCommercialSearch


def main():
    parser = argparse.ArgumentParser(description="TikTok EEA Commercial Content 광고 참고 후보 검색")
    parser.add_argument("keyword", help="광고 검색어 (최대 50자)")
    parser.add_argument("--country", choices=sorted(EEA_COUNTRIES), default="FR")
    parser.add_argument("--days", type=int, default=30, help="최근 날짜 범위 1~365일")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        result = TikTokCommercialSearch().search(
            args.keyword, country=args.country, lookback_days=args.days, limit=args.limit
        )
        print(json.dumps([asdict(item) for item in result], ensure_ascii=False, indent=2))
    except (MediaError, OSError, ValueError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
