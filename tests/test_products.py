import unittest
import json
from pathlib import Path
import tempfile

from shorts_studio.products import Product, ProductMatch, attach_product_match, rank_products, read_product_candidates


class ProductRankingTests(unittest.TestCase):
    def test_ranks_title_match_and_deduplicates_ids(self):
        items = [
            Product("1", "무선 청소기 초경량", "https://www.coupang.com/item/1", 10000),
            Product("2", "무선 선풍기", "https://www.coupang.com/item/2"),
            Product("1", "무선 청소기 중복", "https://www.coupang.com/item/1-dup"),
        ]
        result = rank_products("무선 청소기", items)
        self.assertEqual([row.product.id for row in result], ["1", "2"])
        self.assertEqual(result[0].matched_terms, ("무선", "청소기"))
        self.assertGreater(result[0].score, result[1].score)

    def test_english_text_not_crash(self):
        result = rank_products("wireless mouse", [Product("x", "Wireless Mouse Silent", "https://example.test/x")])
        self.assertEqual(result[0].score, 1.0)

    def test_empty_and_invalid_limit_rejected(self):
        with self.assertRaises(ValueError):
            rank_products("   ", [])
        with self.assertRaises(ValueError):
            rank_products("선풍기", [], limit=100)

    def test_reads_candidate_json_and_converts_price(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            path.write_text(json.dumps([{
                "id": 1, "title": "무선 청소기", "url": "https://example.test/p/1",
                "price": "12000", "affiliate_url": "https://link.coupang.com/a/test",
            }]), encoding="utf-8")
            products = read_product_candidates(path)
        self.assertEqual(products[0].id, "1")
        self.assertEqual(products[0].price, 12000)
        self.assertEqual(products[0].affiliate_url, "https://link.coupang.com/a/test")

    def test_rejects_invalid_candidate_shape_and_price(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            path.write_text('{"items": []}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_product_candidates(path)

    def test_attaches_selected_product_to_script_without_mutating_source(self):
        script = {"title": "대본", "segments": [{"narration": "정리 팁"}], "cta": "끝"}
        product = Product("p-1", "주방 정리함", "https://shop.test/p-1", 12000,
                          affiliate_url="https://affiliate.test/p-1")
        linked = attach_product_match(script, ProductMatch(product, .8, ("정리함",)))
        self.assertNotIn("product", script)
        self.assertEqual(linked["product"]["affiliate_url"], "https://affiliate.test/p-1")
        self.assertEqual(linked["product_match"]["matched_terms"], ["정리함"])

    def test_product_metadata_is_attached_without_fabricating_missing_counts(self):
        script = {"title": "대본", "segments": [{"narration": "정리 팁"}]}
        product = Product("p-1", "주방 정리함", "https://shop.test/p-1", review_count=23)
        linked = attach_product_match(script, ProductMatch(product, .8, ("정리함",)))
        self.assertEqual(linked["product"]["review_count"], 23)
        self.assertIsNone(linked["product"]["sales_count"])

    def test_product_attach_requires_script_segments(self):
        product = Product("p-1", "주방 정리함", "https://shop.test/p-1")
        with self.assertRaises(ValueError):
            attach_product_match({}, ProductMatch(product, .5, ()))
            path.write_text('[{"id":"1","title":"상품","price":"무료"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_product_candidates(path)


if __name__ == "__main__":
    unittest.main()
