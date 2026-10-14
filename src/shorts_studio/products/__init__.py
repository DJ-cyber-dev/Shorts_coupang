"""Product candidate data and local relevance ranking."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Protocol


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    url: str
    price: int | None = None
    image_url: str = ""
    affiliate_url: str = ""
    rank: int | None = None
    sales_count: int | None = None
    review_count: int | None = None
    rating: float | None = None
    is_rocket: bool | None = None
    is_free_shipping: bool | None = None


class ProductMatcher(Protocol):
    def search(self, keywords: list[str]) -> list[Product]: ...


@dataclass(frozen=True)
class ProductMatch:
    product: Product
    score: float
    matched_terms: tuple[str, ...]


def attach_product_match(script: dict, match: ProductMatch) -> dict:
    """Return a copy of a Shorts script with the selected product and match evidence attached."""
    if not isinstance(script, dict) or not isinstance(script.get("segments"), list):
        raise ValueError("상품을 연결할 대본 JSON에 segments 배열이 필요합니다.")
    if not isinstance(match, ProductMatch) or not match.product.id or not match.product.title:
        raise ValueError("유효한 상품 후보를 선택하세요.")
    result = dict(script)
    result["product"] = {
        "id": match.product.id,
        "title": match.product.title,
        "url": match.product.url,
        "affiliate_url": match.product.affiliate_url,
        "price": match.product.price,
        "image_url": match.product.image_url,
        "rank": match.product.rank,
        "sales_count": match.product.sales_count,
        "review_count": match.product.review_count,
        "rating": match.product.rating,
        "is_rocket": match.product.is_rocket,
        "is_free_shipping": match.product.is_free_shipping,
    }
    result["product_match"] = {
        "score": match.score,
        "matched_terms": list(match.matched_terms),
    }
    return result


def read_product_candidates(path: str | Path) -> list[Product]:
    """Read a provider-exported or manually prepared JSON candidate list."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"상품 후보 JSON을 읽지 못했습니다: {exc}") from exc
    if not isinstance(raw, list):
        raise ValueError("상품 후보 JSON 최상위 값은 배열이어야 합니다.")
    products = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        price = row.get("price")
        if price is not None:
            try:
                price = int(price)
            except (TypeError, ValueError) as exc:
                raise ValueError("상품 후보 price는 숫자여야 합니다.") from exc
        products.append(Product(
            id=str(row.get("id", "")), title=str(row.get("title", "")),
            url=str(row.get("url", "")), price=price,
            image_url=str(row.get("image_url", "")),
            affiliate_url=str(row.get("affiliate_url", "")),
            rank=_optional_int(row.get("rank")),
            sales_count=_optional_int(row.get("sales_count")),
            review_count=_optional_int(row.get("review_count")),
            rating=_optional_float(row.get("rating")),
            is_rocket=_optional_bool(row.get("is_rocket")),
            is_free_shipping=_optional_bool(row.get("is_free_shipping")),
        ))
    return products


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[가-힣]{2,}|[a-zA-Z0-9]+", value)}


def _optional_int(value):
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _optional_float(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _optional_bool(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def rank_products(query: str, products: list[Product], *, limit: int = 10,
                  include_unmatched: bool = False) -> list[ProductMatch]:
    """Rank provider-supplied products by title overlap; never invent products or links."""
    if not query.strip() or len(query) > 300:
        raise ValueError("상품 검색어는 1~300자로 입력하세요.")
    if not 1 <= limit <= 50:
        raise ValueError("상품 후보 표시 개수는 1~50이어야 합니다.")
    query_terms = _tokens(query)
    if not query_terms:
        raise ValueError("검색어에 한글, 영문 또는 숫자가 필요합니다.")
    ranked = []
    seen = set()
    normalized_query = re.sub(r"\s+", "", query).casefold()
    for product in products:
        if not product.id or not product.title.strip() or product.id in seen:
            continue
        seen.add(product.id)
        title_terms = _tokens(product.title)
        matched = tuple(sorted(query_terms & title_terms))
        overlap = len(matched) / len(query_terms)
        title_key = re.sub(r"\s+", "", product.title).casefold()
        phrase_bonus = 0.2 if normalized_query in title_key else 0.0
        score = min(1.0, overlap * 0.8 + phrase_bonus)
        if score or include_unmatched:
            ranked.append(ProductMatch(product, round(score, 4), matched))
    ranked.sort(key=lambda item: (-item.score, item.product.title.casefold(), item.product.id))
    return ranked[:limit]
