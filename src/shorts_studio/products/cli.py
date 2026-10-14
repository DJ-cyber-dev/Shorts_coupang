"""Rank Coupang candidate JSON exported by a provider or manually prepared."""
import argparse
import json
from pathlib import Path

from . import rank_products, read_product_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("products", type=Path, help="JSON list: id, title, url, optional price/image_url/affiliate_url")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    candidates = read_product_candidates(args.products)
    matches = rank_products(args.query, candidates, limit=args.limit)
    print(json.dumps([{
        "id": row.product.id, "title": row.product.title, "url": row.product.url,
        "affiliate_url": row.product.affiliate_url, "price": row.product.price,
        "score": row.score, "matched_terms": row.matched_terms,
    } for row in matches], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
