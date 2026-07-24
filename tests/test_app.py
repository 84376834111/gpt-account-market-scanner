import json
import sqlite3
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from app import (
    CATFK_BASE_URL,
    Database,
    EventHub,
    LDXPClient,
    LDXP_PAGE_SIZE,
    ScannerService,
    classify_product,
    create_app,
    extract_ldxp_refs,
    normalize_source,
    parse_source_reference,
    product_from_api,
    remaining_cycle_delay,
    resolve_source_reference,
)


class ClassificationTests(unittest.TestCase):
    def test_classifies_requested_keywords(self):
        self.assertEqual(classify_product("ChatGPT Plus 独享账号"), ["plus"])
        self.assertIn("cursor", classify_product("Cursor Pro 年付"))
        self.assertIn("pro", classify_product("Cursor Pro 年付"))
        self.assertEqual(classify_product("谷歌老邮箱 Gmail"), ["mail"])
        self.assertEqual(
            classify_product("GPT BUG TEAM 账号"),
            ["team", "bugteam"],
        )

    def test_splits_plus_and_free_by_sms_status(self):
        self.assertEqual(
            classify_product("GPT Plus 成品号 未接码"),
            ["plus", "plus_no_sms"],
        )
        self.assertEqual(
            classify_product("ChatGPT Plus 已接码成品号"),
            ["plus", "plus_sms"],
        )
        self.assertEqual(
            classify_product("Gpt Free（已接码 | 可刷新RT）"),
            ["free", "free_sms"],
        )
        self.assertEqual(
            classify_product("GPT Free 普通号 未绑定手机"),
            ["free", "free_no_sms"],
        )
        self.assertEqual(
            classify_product("chatgpt成品号-高权重谷歌邮箱-未接码"),
            ["mail", "free", "free_no_sms"],
        )
        self.assertEqual(
            classify_product("Gpt Free（双接码 | 反代 | Codex）"),
            ["free", "codex", "free_sms"],
        )

    def test_keeps_sms_services_separate_from_unverified_accounts(self):
        self.assertNotIn("sms", classify_product("GPT Plus 成品号 未接码"))
        self.assertIn("sms", classify_product("Codex长效接码美国实体卡"))

    def test_ignores_generic_description(self):
        item = {
            "goods_key": "abc123",
            "name": "普通 API 额度卡",
            "description": "支持 Claude、Gemini 和 Plus",
            "category": {"name": "接口额度"},
        }
        self.assertIsNone(product_from_api(item, "demo", "演示店"))


class SourceTests(unittest.TestCase):
    def test_normalizes_url_and_token(self):
        self.assertEqual(normalize_source("https://pay.ldxp.cn/shop/CodexBro"), "CodexBro")
        self.assertEqual(normalize_source("doge"), "doge")
        self.assertEqual(normalize_source("https://pay.ldxp.cn/shop/paofumiao.ai"), "paofumiao.ai")
        with self.assertRaises(ValueError):
            normalize_source("https://pay.ldxp.cn/item/abc123")

    def test_normalizes_catfk_shop_and_recognizes_item_reference(self):
        self.assertEqual(
            normalize_source("https://catfk.com/shop/agi"),
            "catfk.com:agi",
        )
        reference = parse_source_reference(
            "https://catfk.com/item/83xvh8", allow_item=True
        )
        self.assertEqual(reference.base_url, CATFK_BASE_URL)
        self.assertEqual(reference.goods_key, "83xvh8")
        self.assertEqual(reference.key, "")
        self.assertEqual(normalize_source("catfk.com:agi"), "catfk.com:agi")

    def test_extracts_shop_and_item_references(self):
        shops, items = extract_ldxp_refs(
            {
                "excerpt": "店铺 https://pay.ldxp.cn/shop/D92VW084",
                "reply": "商品 https://pay.ldxp.cn/item/9khwcj",
            }
        )
        self.assertEqual(shops, {"D92VW084"})
        self.assertEqual(items, {"9khwcj"})

    def test_resolves_catfk_item_to_its_shop(self):
        client = Mock()
        client.goods_info.return_value = {
            "goods_key": "83xvh8",
            "user": {"token": "agi", "nickname": "AGI 小店"},
        }
        with patch("app.LDXPClient", return_value=client) as client_class:
            reference, name = resolve_source_reference(
                "https://catfk.com/item/83xvh8"
            )

        client_class.assert_called_once_with(base_url=CATFK_BASE_URL)
        client.goods_info.assert_called_once_with("83xvh8")
        self.assertEqual(reference.key, "catfk.com:agi")
        self.assertEqual(reference.goods_key, "83xvh8")
        self.assertEqual(name, "AGI 小店")


class LDXPClientTests(unittest.TestCase):
    @staticmethod
    def response(data):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"code": 1, "data": data}).encode()
        return response

    def test_uses_direct_connection_without_touching_proxy_when_available(self):
        direct = Mock()
        direct.open.return_value = self.response({"ok": True})
        with (
            patch("app.urllib.request.build_opener", return_value=direct),
            patch("app.subprocess.run") as proxy,
        ):
            client = LDXPClient(
                proxy_url="http://127.0.0.1:7891",
                direct_attempts=1,
                proxy_attempts=3,
                retry_delay=0,
            )
            result = client.post("/test", {"value": 1})

        self.assertEqual(result, {"ok": True})
        direct.open.assert_called_once()
        proxy.assert_not_called()

    def test_retries_through_rotating_proxy_after_direct_failure(self):
        direct = Mock()
        direct.open.side_effect = urllib.error.URLError("direct unavailable")
        proxy_results = [
            Mock(returncode=7, stdout=b"", stderr=b"first proxy node unavailable"),
            Mock(
                returncode=0,
                stdout=json.dumps({"code": 1, "data": {"ok": True}}).encode(),
                stderr=b"",
            ),
        ]
        with (
            patch("app.urllib.request.build_opener", return_value=direct),
            patch("app.subprocess.run", side_effect=proxy_results) as proxy,
            patch("app.time.sleep"),
            patch("builtins.print") as log,
        ):
            client = LDXPClient(
                proxy_url="http://127.0.0.1:7891",
                direct_attempts=1,
                proxy_attempts=3,
                retry_delay=0.1,
            )
            result = client.post("/test", {"value": 1})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(direct.open.call_count, 1)
        self.assertEqual(proxy.call_count, 2)
        log.assert_called_once()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parent / "_test.db"
        self._remove_database_files()
        self.db = Database(self.path)
        self.db.upsert_source("demo", "演示店", origin="unit-test")

    def tearDown(self):
        self._remove_database_files()

    def _remove_database_files(self):
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                candidate.unlink()

    def product(self, price=9.9, stock=3):
        return {
            "goods_key": "goods1",
            "source_token": "demo",
            "source_name": "演示店",
            "name": "Claude Pro",
            "price": price,
            "market_price": 20,
            "stock_count": stock,
            "in_stock": stock != 0,
            "tags": ["pro", "claude"],
            "category_name": "AI",
            "goods_type": "card",
            "link": "https://pay.ldxp.cn/item/goods1",
            "image": "",
            "description_excerpt": "",
            "create_time": 1,
        }

    def test_tracks_price_and_stock_changes(self):
        self.assertEqual(self.db.list_sources()[0]["origin"], "unit-test")
        with patch("app.now_ts", return_value=100):
            change, saved = self.db.upsert_product(self.product())
            self.assertEqual(change, "new")
            self.assertTrue(saved["in_stock"])
            change, _ = self.db.upsert_product(self.product())
            self.assertEqual(change, "unchanged")
            change, saved = self.db.upsert_product(self.product(price=8.8, stock=0))
            self.assertEqual(change, "changed")
            self.assertFalse(saved["in_stock"])
        self.assertEqual(len(self.db.history("goods1")), 2)
        self.assertEqual(self.db.deactivate_missing("demo", set()), {"goods1"})
        self.assertEqual(self.db.list_products(), [])

    def test_persists_catfk_platform_and_remote_shop_token(self):
        source = self.db.upsert_source(
            "catfk.com:agi",
            "AGI",
            base_url=CATFK_BASE_URL,
            remote_token="agi",
            entry_goods_key="83xvh8",
        )
        self.assertEqual(source["base_url"], CATFK_BASE_URL)
        self.assertEqual(source["remote_token"], "agi")
        self.assertEqual(source["entry_goods_key"], "83xvh8")
        self.assertEqual(source["url"], "https://catfk.com/shop/agi")

    def test_records_a_price_node_for_each_refresh_time(self):
        with patch("app.now_ts", return_value=100):
            self.db.upsert_product(self.product())
        with patch("app.now_ts", return_value=101):
            change, _ = self.db.upsert_product(self.product())
        self.assertEqual(change, "unchanged")
        self.assertEqual(
            [point["recorded_at"] for point in self.db.history("goods1")],
            [101, 100],
        )

    def test_ingests_complete_browser_local_source_and_removes_missing_products(self):
        self.db.upsert_product(self.product())
        events = EventHub()
        service = ScannerService(self.db, events, auto_scan_enabled=False)
        result = service.ingest_local_source(
            "demo",
            "浏览器本地店铺",
            [
                {
                    "goods_key": "goods2",
                    "name": "Claude Pro 本地扫描",
                    "price": 6.6,
                    "market_price": 20,
                    "extend": {"stock_count": 5},
                    "category": {"name": "AI"},
                    "goods_type": "card",
                    "link": "https://pay.ldxp.cn/item/goods2",
                    "image": "",
                    "description": "",
                    "create_time": 2,
                }
            ],
        )

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["removed"], 1)
        self.assertIsNone(self.db.get_product("goods1"))
        self.assertEqual(self.db.get_product("goods2")["stock_count"], 5)
        source = self.db.get_source("demo")
        self.assertEqual(source["name"], "浏览器本地店铺")
        self.assertEqual(source["status"], "ok")
        self.assertEqual(source["product_count"], 1)

    def test_ingests_only_requested_browser_products_and_preserves_the_rest(self):
        first = self.product()
        second = {**self.product(), "goods_key": "goods2", "name": "Claude Pro 2"}
        self.db.upsert_product(first)
        self.db.upsert_product(second)
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)

        result = service.ingest_local_products(
            "demo",
            "演示店",
            [
                {
                    "goods_key": "goods1",
                    "name": "Claude Pro 新价格",
                    "price": 7.7,
                    "market_price": 20,
                    "extend": {"stock_count": 2},
                    "category": {"name": "AI"},
                    "goods_type": "card",
                    "link": "https://pay.ldxp.cn/item/goods1",
                }
            ],
            {"goods1"},
        )

        self.assertEqual(result["matched"], 1)
        self.assertEqual(self.db.get_product("goods1")["price"], 7.7)
        self.assertIsNotNone(self.db.get_product("goods2"))

        removed = service.ingest_local_products("demo", "演示店", [], {"goods1"})
        self.assertEqual(removed["removed"], 1)
        self.assertIsNone(self.db.get_product("goods1"))
        self.assertIsNotNone(self.db.get_product("goods2"))

    def test_disabled_auto_scan_starts_control_thread_for_runtime_enable(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        with patch("app.threading.Thread") as thread:
            service.start()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_persists_runtime_scan_schedule(self):
        self.db.set_settings({"auto_scan_enabled": "true", "scan_interval": "1320"})
        state = create_app(self.path, seed=False)
        self.assertTrue(state.scanner.auto_scan_enabled)
        self.assertEqual(state.scanner.interval, 1320)

    def test_cycle_window_keeps_idle_time_but_never_overlaps(self):
        self.assertEqual(remaining_cycle_delay(900, 480), 420)
        self.assertEqual(remaining_cycle_delay(900, 960), 0)

    def test_server_scan_paces_source_starts_to_fifteen_seconds(self):
        self.db.upsert_source("demo-two", "第二家店", origin="unit-test")
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        with (
            patch.object(service, "_discover_sources", return_value=(0, 0)),
            patch.object(service, "_scan_source", return_value=(0, 0)),
            patch.object(service._stop, "is_set", return_value=False),
            patch.object(service._stop, "wait", return_value=False) as wait,
            patch("app.time.monotonic", side_effect=[100.0, 104.0, 119.0]),
        ):
            service._scan_all("manual")
        wait.assert_called_once_with(11.0)

    def test_scans_catfk_source_with_its_own_base_url_and_remote_token(self):
        self.db.upsert_source(
            "catfk.com:agi",
            "AGI",
            base_url=CATFK_BASE_URL,
            remote_token="agi",
            entry_goods_key="83xvh8",
        )
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        client = Mock()
        client.shop_info.return_value = {
            "nickname": "AGI",
            "card_count": 0,
        }
        client.goods_page.return_value = {
            "list": [],
            "total": 0,
        }
        client.goods_info.return_value = {
            "goods_key": "83xvh8",
            "name": "K12速刷 反代专用",
            "price": 2,
            "extend": {"limit_count": 1},
            "category": {"name": "GPT"},
            "goods_type": "card",
        }
        with patch("app.LDXPClient", return_value=client) as client_class:
            matched, _ = service._scan_source("catfk.com:agi")

        self.assertEqual(matched, 1)
        client_class.assert_called_once_with(base_url=CATFK_BASE_URL)
        client.shop_info.assert_called_once_with("agi")
        self.assertEqual(client.goods_page.call_count, 4)
        client.goods_info.assert_called_once_with("83xvh8")
        product = self.db.get_product("83xvh8")
        self.assertEqual(product["source_token"], "catfk.com:agi")
        self.assertEqual(product["link"], "https://catfk.com/item/83xvh8")

    def test_refreshes_one_product_without_scanning_others(self):
        self.db.upsert_product(self.product())
        events = EventHub()
        client = events.subscribe()
        service = ScannerService(self.db, events)
        ldxp = Mock()
        refreshed_item = {
            "goods_key": "goods1",
            "name": "Claude Pro",
            "price": 7.7,
            "market_price": 20,
            "extend": {"stock_count": 2},
            "category": {"name": "AI"},
            "goods_type": "card",
            "link": "https://pay.ldxp.cn/item/goods1",
            "image": "",
            "description": "",
            "create_time": 1,
        }
        ldxp.goods_page.return_value = {"list": [refreshed_item], "total": 1}
        with patch("app.LDXPClient", return_value=ldxp):
            change, product = service.refresh_product("goods1")

        self.assertEqual(change, "changed")
        self.assertEqual(product["price"], 7.7)
        self.assertEqual(self.db.get_product("goods1")["stock_count"], 2)
        ldxp.goods_page.assert_called_once_with("demo", "card", 1, LDXP_PAGE_SIZE)
        ldxp.goods_info.assert_not_called()
        event = client.get_nowait()
        self.assertEqual(event["event"], "product_refresh")
        self.assertEqual(event["data"]["product"]["goods_key"], "goods1")

    def test_single_product_detail_without_stock_preserves_known_stock(self):
        self.db.upsert_product(self.product(stock=3))
        service = ScannerService(self.db, EventHub())
        ldxp = Mock()
        ldxp.goods_page.return_value = {"list": [], "total": 0}
        ldxp.goods_info.return_value = {
            "goods_key": "goods1",
            "name": "Claude Pro",
            "price": 8.5,
            "market_price": 20,
            "extend": {"limit_count": 1},
            "category": {"name": "AI"},
            "goods_type": "card",
            "link": "https://pay.ldxp.cn/item/goods1",
            "image": "",
            "description": "",
            "create_time": 1,
        }
        with patch("app.LDXPClient", return_value=ldxp):
            _, product = service.refresh_product("goods1")

        self.assertEqual(product["price"], 8.5)
        self.assertEqual(product["stock_count"], 3)
        self.assertTrue(product["in_stock"])


class MigrationTests(unittest.TestCase):
    def test_adds_origin_to_existing_source_table(self):
        path = Path(__file__).resolve().parent / "_migration.db"
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{path}{suffix}")
            if candidate.exists():
                candidate.unlink()
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                """
                CREATE TABLE sources (
                    token TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NOT NULL DEFAULT '', last_scan INTEGER NOT NULL DEFAULT 0,
                    product_count INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()
        database = Database(path)
        connection = database.connect()
        try:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(sources)")}
        finally:
            connection.close()
        self.assertIn("origin", columns)
        self.assertIn("base_url", columns)
        self.assertIn("remote_token", columns)
        self.assertIn("entry_goods_key", columns)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{path}{suffix}")
            if candidate.exists():
                candidate.unlink()


if __name__ == "__main__":
    unittest.main()
