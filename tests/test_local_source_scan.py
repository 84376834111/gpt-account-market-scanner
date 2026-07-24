import unittest
from unittest.mock import Mock, patch

from app import CATFK_BASE_URL
from tools.local_source_scan import scan_source


class LocalSourceScanTests(unittest.TestCase):
    def test_scans_catfk_with_remote_token_and_entry_item_fallback(self):
        client = Mock()
        client.shop_info.return_value = {"nickname": "AGI", "card_count": 0}
        client.goods_page.return_value = {"list": [], "total": 0}
        client.goods_info.return_value = {
            "goods_key": "83xvh8",
            "name": "K12 速刷",
            "price": 2,
            "category": {"name": "GPT"},
            "goods_type": "card",
        }
        source = {
            "token": "catfk.com:agi",
            "remote_token": "agi",
            "base_url": CATFK_BASE_URL,
            "entry_goods_key": "83xvh8",
        }

        with patch("tools.local_source_scan.LDXPClient", return_value=client) as client_class:
            result = scan_source(source)

        self.assertTrue(result["complete"])
        self.assertEqual([item["goods_key"] for item in result["products"]], ["83xvh8"])
        self.assertEqual(result["products"][0]["link"], "https://catfk.com/item/83xvh8")
        client_class.assert_called_once_with(base_url=CATFK_BASE_URL)
        client.shop_info.assert_called_once_with("agi")
        self.assertEqual(client.goods_page.call_count, 4)
        client.goods_info.assert_called_once_with("83xvh8")


if __name__ == "__main__":
    unittest.main()
