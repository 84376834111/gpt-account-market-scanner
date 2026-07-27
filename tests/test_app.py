import json
import sqlite3
import threading
import unittest
import urllib.error
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import app

from app import (
    CATFK_BASE_URL,
    Database,
    EventHub,
    LDXPClient,
    LDXPError,
    LDXPTransportError,
    LDXP_PAGE_SIZE,
    HIGH_STOCK_REFRESH_INTERVAL,
    LOW_STOCK_REFRESH_INTERVAL,
    NORMAL_STOCK_REFRESH_INTERVAL,
    PRICEAI_SOURCE_TOKEN,
    ProductRefreshInProgress,
    UNKNOWN_OR_ZERO_REFRESH_INTERVAL,
    ProxyEndpoint,
    SCDNProxySource,
    ScanResult,
    ScannerService,
    ScannerHTTPServer,
    RequestHandler,
    classify_product,
    create_app,
    extract_ldxp_refs,
    normalize_source,
    parse_source_reference,
    product_from_api,
    product_refresh_interval,
    remaining_cycle_delay,
    resolve_source_reference,
    source_reference_from_link_search,
)


class ClassificationTests(unittest.TestCase):
    def test_classifies_requested_keywords(self):
        self.assertEqual(classify_product("ChatGPT Plus 独享账号"), ["plus"])
        self.assertIn("cursor", classify_product("Cursor Pro 年付"))
        self.assertNotIn("pro", classify_product("Cursor Pro 年付"))
        self.assertEqual(classify_product("谷歌老邮箱 Gmail"), ["mail"])
        self.assertEqual(
            classify_product("GPT BUG TEAM 账号"),
            ["bugteam"],
        )

    def test_uses_only_title_and_prefers_specific_account_tiers(self):
        self.assertEqual(classify_product("普通 API 额度卡", "Plus Team K12"), ["relay"])
        self.assertEqual(classify_product("GPT Free 可开 Plus 已接码"), ["free", "free_sms"])
        self.assertEqual(classify_product("GPT Team K12 成品"), ["k12"])
        self.assertEqual(classify_product("GPT BUGTEAM Team 账号"), ["bugteam"])
        self.assertEqual(
            classify_product("GPT Plus Codex 未接码 已接码"),
            ["plus", "codex", "plus_no_sms"],
        )
        self.assertEqual(
            classify_product("Plus 半成品需自己接码"),
            ["plus", "plus_no_sms"],
        )
        self.assertEqual(classify_product("Outlook 邮箱未接码"), ["mail", "free_no_sms"])
        self.assertEqual(classify_product("Codex 接码 美国实体卡"), ["codex", "sms"])
        self.assertEqual(classify_product("微软长效 Hotmail OAuth2"), ["mail"])
        self.assertEqual(classify_product("GPT PRO20X 菲区卡充"), ["pro"])
        self.assertEqual(classify_product("英国永久手机号"), ["sms"])

    def test_ignores_parenthetical_title_content_and_filters_false_positive_terms(self):
        self.assertEqual(classify_product("GPT Plus (BUGTEAM K12)"), ["plus"])
        self.assertEqual(classify_product("Cursor Pro (ChatGPT Plus)"), ["cursor"])
        self.assertEqual(classify_product("Claude Free 账号"), ["claude"])

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
            ["free"],
        )
        self.assertEqual(
            classify_product("GPT Free 普通号 未绑定手机"),
            ["free", "free_no_sms"],
        )
        self.assertEqual(
            classify_product("chatgpt成品号-高权重谷歌邮箱-未接码"),
            ["free", "mail", "free_no_sms"],
        )
        self.assertEqual(
            classify_product("Gpt Free（双接码 | 反代 | Codex）"),
            ["free"],
        )

    def test_keeps_sms_services_separate_from_unverified_accounts(self):
        self.assertNotIn("sms", classify_product("GPT Plus 成品号 未接码"))
        self.assertIn("sms", classify_product("Codex长效接码美国实体卡"))

    def test_classifies_relay_services_without_account_mail_or_sms_false_positives(self):
        self.assertIn("relay", classify_product("Codex 官方中转 API 50刀额度"))
        self.assertIn("relay", classify_product("Claude 1000刀额度兑换码"))
        self.assertIn("relay", classify_product("老徐 Codex 中转站 10刀额度"))
        self.assertNotIn("relay", classify_product("Outlook OAuth2 API 令牌号"))
        self.assertNotIn("relay", classify_product("Codex 接码美国实卡 API 长效"))
        self.assertNotIn("relay", classify_product("GPT Plus 成品账号可导入中转站"))
        self.assertNotIn("relay", classify_product("K12 JSON 仅支持 Sub2API"))

    def test_ignores_generic_description(self):
        item = {
            "goods_key": "abc123",
            "name": "普通 API 额度卡",
            "description": "支持 Claude、Gemini 和 Plus",
            "category": {"name": "Plus Team K12"},
        }
        product = product_from_api(item, "demo", "BugTeam Free 店")
        self.assertEqual(product["tags"], ["relay"])


class SourceTests(unittest.TestCase):
    def test_reads_scdn_http_proxy_page(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "totalPages": 166,
                "table_html": (
                    '<button data-proxy="18.162.158.218:80">复制</button>'
                    '<button data-proxy="16.162.88.123:8080">复制</button>'
                    '<button data-proxy="18.162.158.218:80">复制</button>'
                ),
            }
        ).encode()
        with patch("app.urllib.request.urlopen", return_value=response) as open_url:
            candidates, total_pages = SCDNProxySource(
                page_url="https://proxy.scdn.io/get_proxies.php",
                protocol="http",
                page_size=100,
            ).fetch_page(7)

        self.assertEqual(total_pages, 166)
        self.assertEqual([candidate.endpoint for candidate in candidates], [
            "18.162.158.218:80",
            "16.162.88.123:8080",
        ])
        self.assertTrue(all(candidate.protocol == "http" for candidate in candidates))
        self.assertIn("page=7", open_url.call_args.args[0].full_url)
        self.assertIn("protocol=HTTP", open_url.call_args.args[0].full_url)

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

    def test_recognizes_public_urls_for_exact_search(self):
        self.assertEqual(
            source_reference_from_link_search("https://pay.ldxp.cn/shop/CodexBro").key, "CodexBro"
        )
        self.assertEqual(
            source_reference_from_link_search("https://catfk.com/shop/agi").key, "catfk.com:agi"
        )
        self.assertEqual(
            source_reference_from_link_search("https://pay.ldxp.cn/item/abc123").goods_key, "abc123"
        )
        self.assertIsNone(source_reference_from_link_search("CodexBro"))

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

    def test_reports_each_successful_direct_proxy_request(self):
        observer = Mock()
        completed = Mock(
            returncode=0,
            stdout=json.dumps({"code": 1, "data": {"ok": True}}).encode(),
            stderr=b"",
        )
        with patch("app.subprocess.run", return_value=completed):
            client = LDXPClient(
                proxy_url="http://8.8.8.8:8080",
                direct_attempts=0,
                proxy_attempts=1,
                retry_delay=0,
                proxy_observer=observer,
            )
            self.assertEqual(client.post("/test", {"value": 1}), {"ok": True})

        observer.assert_called_once_with(True)

    def test_uses_proxy_insecure_only_for_https_proxy_certificates(self):
        completed = Mock(
            returncode=0,
            stdout=json.dumps({"code": 1, "data": {"ok": True}}).encode(),
            stderr=b"",
        )
        with patch("app.subprocess.run", return_value=completed) as run:
            client = LDXPClient(
                proxy_url="https://8.8.8.8:8443",
                direct_attempts=0,
                proxy_attempts=1,
                retry_delay=0,
            )
            self.assertEqual(client.post("/test", {"value": 1}), {"ok": True})

        command = run.call_args.args[0]
        self.assertIn("--proxy-insecure", command)
        self.assertEqual(command[command.index("--proxy") + 1], "https://8.8.8.8:8443")


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

    def test_pages_products_with_server_side_filters_and_category_counts(self):
        self.db.upsert_product(
            {
                **self.product(price=30),
                "name": "Claude Pro",
                "tags": ["pro", "claude"],
            }
        )
        self.db.upsert_product(
            {
                **self.product(price=10),
                "goods_key": "goods2",
                "name": "GPT Plus 已接码",
                "tags": ["plus", "plus_sms"],
            }
        )
        self.db.upsert_product(
            {
                **self.product(price=5, stock=0),
                "goods_key": "goods3",
                "name": "GPT Plus 未接码",
                "tags": ["plus", "plus_no_sms"],
            }
        )
        self.db.upsert_product(
            {
                **self.product(price=12),
                "goods_key": "goods4",
                "name": "GPT Plus 搜索项",
                "tags": ["plus"],
            }
        )

        page = self.db.list_product_page(
            category="plus", stock_only=True, search="plus", sort="price", limit=1
        )
        self.assertEqual(page["total"], 2)
        self.assertEqual([product["goods_key"] for product in page["products"]], ["goods2"])
        second_page = self.db.list_product_page(
            category="plus", stock_only=True, search="plus", sort="price", offset=1, limit=1
        )
        self.assertEqual([product["goods_key"] for product in second_page["products"]], ["goods4"])

        stats = self.db.stats()
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["in_stock"], 3)
        self.assertEqual(stats["category_counts"]["plus"], 3)
        self.assertEqual(stats["category_counts"]["pro"], 1)

    def test_pages_products_by_price_range_and_left_boundary_choice(self):
        self.db.upsert_product({**self.product(price=0), "goods_key": "zero"})
        self.db.upsert_product({**self.product(price=10), "goods_key": "ten"})
        self.db.upsert_product({**self.product(price=20), "goods_key": "twenty"})

        default_page = self.db.list_product_page(stock_only=False, sort="price", limit=10)
        self.assertEqual([item["goods_key"] for item in default_page["products"]], ["ten", "twenty"])
        bounded = self.db.list_product_page(
            stock_only=False, sort="price", min_price=10, max_price=10, limit=10
        )
        self.assertEqual(bounded["products"], [])
        including_left = self.db.list_product_page(
            stock_only=False, sort="price", min_price=10, max_price=10, include_left=True, limit=10
        )
        self.assertEqual([item["goods_key"] for item in including_left["products"]], ["ten"])
        including_left_zero = self.db.list_product_page(
            stock_only=False, sort="price", include_left=True, limit=10
        )
        self.assertEqual(
            [item["goods_key"] for item in including_left_zero["products"]], ["zero", "ten", "twenty"]
        )

    def test_tracks_out_of_stock_start_and_uses_lazy_refresh_intervals(self):
        with patch("app.now_ts", return_value=100):
            self.db.upsert_product(self.product(stock=0))
        first = self.db.get_product("goods1")
        self.assertEqual(first["out_of_stock_since"], 100)
        self.assertFalse(app.is_lazy_out_of_stock(first, 100))
        self.assertEqual(product_refresh_interval(first, 100), 2 * 60 * 60)
        self.assertTrue(app.is_lazy_out_of_stock(first, 100 + 24 * 60 * 60))
        self.assertEqual(product_refresh_interval(first, 100 + 8 * 24 * 60 * 60), 24 * 60 * 60)
        self.assertEqual(app.lazy_refresh_due_at(first["last_seen"], 100), first["last_seen"] + 24 * 60 * 60)

        with patch("app.now_ts", return_value=200):
            self.db.upsert_product(self.product(stock=4))
        restocked = self.db.get_product("goods1")
        self.assertEqual(restocked["out_of_stock_since"], 0)
        self.assertEqual(product_refresh_interval(restocked, 200), NORMAL_STOCK_REFRESH_INTERVAL)
        self.assertEqual(product_refresh_interval(self.product(stock=2), 200), LOW_STOCK_REFRESH_INTERVAL)
        self.assertEqual(product_refresh_interval(self.product(stock=20), 200), HIGH_STOCK_REFRESH_INTERVAL)
        self.assertEqual(
            product_refresh_interval({**self.product(), "price": 8, "stock_count": -1}, 200),
            UNKNOWN_OR_ZERO_REFRESH_INTERVAL,
        )
        self.assertEqual(
            product_refresh_interval({**self.product(), "price": 0, "stock_count": 8}, 200),
            UNKNOWN_OR_ZERO_REFRESH_INTERVAL,
        )

    def test_scheduled_scan_selects_only_due_sources_and_link_search(self):
        self.db.upsert_source("second", "第二家", origin="unit-test")
        with patch("app.now_ts", return_value=1_000):
            self.db.upsert_product(self.product(stock=2))
            self.db.upsert_product(
                {
                    **self.product(stock=20),
                    "goods_key": "goods2",
                    "source_token": "second",
                    "link": "https://pay.ldxp.cn/item/link-search-key",
                }
            )

        with patch("app.now_ts", return_value=1_000 + LOW_STOCK_REFRESH_INTERVAL):
            due = self.db.list_sources_due_for_scan(scheduled=True)
        self.assertEqual([source["token"] for source in due], ["demo"])
        self.assertEqual(
            [product["goods_key"] for product in self.db.list_product_page(search="link-search-key")["products"]],
            ["goods2"],
        )

    def test_successfully_scanned_empty_source_uses_last_scan_as_watermark(self):
        self.db.upsert_source("empty", "Empty shop", origin="unit-test")
        with self.db.session() as db:
            db.execute(
                "UPDATE sources SET status = 'ok', last_scan = ?, updated_at = ? WHERE token = 'empty'",
                (1_000, 1_000),
            )

        with patch("app.now_ts", return_value=1_000 + app.SCAN_INTERVAL - 1):
            due_before = self.db.list_sources_due_for_scan(scheduled=True)
        with patch("app.now_ts", return_value=1_000 + app.SCAN_INTERVAL):
            due_at = self.db.list_sources_due_for_scan(scheduled=True)

        self.assertNotIn("empty", [source["token"] for source in due_before])
        self.assertIn("empty", [source["token"] for source in due_at])

    def test_pages_products_by_shop_link_with_exact_source_lookup(self):
        self.db.upsert_source("second", "Second shop", origin="unit-test")
        self.db.upsert_source(
            "catfk.com:agi",
            "AGI shop",
            origin="unit-test",
            base_url=CATFK_BASE_URL,
            remote_token="agi",
        )
        self.db.upsert_product({**self.product(), "goods_key": "first"})
        self.db.upsert_product(
            {**self.product(), "goods_key": "second-item", "source_token": "second"}
        )
        self.db.upsert_product(
            {**self.product(), "goods_key": "catfk-item", "source_token": "catfk.com:agi"}
        )

        self.assertEqual(
            [item["goods_key"] for item in self.db.list_product_page(
                search="https://pay.ldxp.cn/shop/second", stock_only=False
            )["products"]],
            ["second-item"],
        )
        self.assertEqual(
            [item["goods_key"] for item in self.db.list_product_page(
                search="https://catfk.com/shop/agi", stock_only=False
            )["products"]],
            ["catfk-item"],
        )
        self.assertEqual(
            [item["goods_key"] for item in self.db.list_product_page(
                search="https://pay.ldxp.cn/item/second-item", stock_only=False
            )["products"]],
            ["second-item"],
        )

    def test_reads_only_requested_visible_products(self):
        self.db.upsert_product(self.product())
        self.db.upsert_product({**self.product(), "goods_key": "second"})
        self.assertEqual(
            [item["goods_key"] for item in self.db.get_visible_products(["second", "missing", "second"])],
            ["second"],
        )

    def test_off_shelf_products_are_exclusive_to_the_off_shelf_category(self):
        self.db.upsert_product(self.product())
        self.db.upsert_product({**self.product(), "goods_key": "removed", "name": "Claude Pro removed"})
        self.db.mark_product_off_shelf("removed", "item not found")

        normal = self.db.list_product_page(stock_only=False)
        off_shelf = self.db.list_product_page(category="off_shelf", stock_only=True)
        stats = self.db.stats()

        self.assertEqual([item["goods_key"] for item in normal["products"]], ["goods1"])
        self.assertEqual([item["goods_key"] for item in off_shelf["products"]], ["removed"])
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["category_counts"]["off_shelf"], 1)
        self.assertEqual(stats["category_counts"]["claude"], 1)

    def test_all_off_shelf_source_is_excluded_from_manual_and_scheduled_scans(self):
        self.db.upsert_product(self.product())
        self.db.mark_product_off_shelf("goods1", "item not found")

        manual_tokens = [source["token"] for source in self.db.list_sources_due_for_scan(scheduled=False)]
        scheduled_tokens = [source["token"] for source in self.db.list_sources_due_for_scan(scheduled=True)]

        self.assertNotIn("demo", manual_tokens)
        self.assertNotIn("demo", scheduled_tokens)

    def test_state_snapshot_omits_products_by_default(self):
        self.db.upsert_product(self.product())
        state = create_app(self.path, seed=False)
        snapshot = state.snapshot()

        self.assertNotIn("products", snapshot)
        self.assertEqual(snapshot["stats"]["total"], 1)
        self.assertEqual(snapshot["catalog_revision"], state.database.catalog_revision())

    def test_catalog_revision_changes_only_when_filter_mapping_changes(self):
        self.assertEqual(self.db.catalog_revision(), 0)
        self.db.upsert_product(self.product())
        first_revision = self.db.catalog_revision()
        self.assertGreater(first_revision, 0)
        self.db.upsert_product(self.product())
        self.assertEqual(self.db.catalog_revision(), first_revision)
        self.db.upsert_product(self.product(price=8.8))
        self.assertGreater(self.db.catalog_revision(), first_revision)

        page = self.db.list_product_page()
        self.assertEqual(page["catalog_revision"], self.db.catalog_revision())

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

    def test_keeps_successful_daily_proxies_and_rotates_them(self):
        with patch("app.proxy_pool_day", return_value="2026-07-25"):
            self.db.record_proxy_result("8.8.8.8:8080", "https", True)
            self.db.record_proxy_result("1.1.1.1:3128", "https", True)
            self.db.record_proxy_result("8.8.8.8:8080", "https", False)

            first = self.db.next_daily_proxy()
            second = self.db.next_daily_proxy()
            third = self.db.next_daily_proxy()
            summary = self.db.proxy_pool_summary()

        self.assertEqual(first.endpoint, "1.1.1.1:3128")
        self.assertEqual(second.endpoint, "8.8.8.8:8080")
        self.assertEqual(third.endpoint, "1.1.1.1:3128")
        self.assertEqual(summary["usable"], 2)
        self.assertEqual(summary["successes"], 2)
        self.assertEqual(summary["failures"], 1)

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

    def test_reclassifies_existing_products_from_title_only(self):
        free_product = {
            **self.product(),
            "name": "GPT Free 可开 Plus",
            "tags": ["plus"],
            "category_name": "Plus",
        }
        unrelated = {
            **self.product(),
            "goods_key": "goods2",
            "name": "普通 API 额度卡",
            "tags": ["plus"],
            "category_name": "Plus",
        }
        self.db.upsert_product(free_product)
        self.db.upsert_product(unrelated)
        with self.db.session() as db:
            db.execute(
                "UPDATE products SET ai_classification_state = 'done' WHERE goods_key = ?",
                ("goods1",),
            )

        result = self.db.reclassify_products()

        self.assertEqual(result, {"updated": 2, "deactivated": 0})
        self.assertEqual(self.db.get_product("goods1")["tags"], ["free"])
        self.assertEqual(self.db.get_product("goods2")["tags"], ["relay"])

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
        self.assertTrue(self.db.get_product("goods1")["off_shelf"])
        self.assertEqual(self.db.get_product("goods1")["stock_count"], 0)
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
        self.assertEqual(self.db.get_product("goods1")["name"], "Claude Pro")
        self.assertIsNotNone(self.db.get_product("goods2"))

        removed = service.ingest_local_products("demo", "演示店", [], {"goods1"})
        self.assertEqual(removed["removed"], 1)
        self.assertTrue(self.db.get_product("goods1")["off_shelf"])
        self.assertEqual(self.db.get_product("goods1")["stock_count"], 0)
        self.assertIsNotNone(self.db.get_product("goods2"))

    def test_user_refresh_claim_prioritizes_products_not_scanned_recently(self):
        old = self.product()
        recent = {**self.product(), "goods_key": "goods2", "name": "Claude Pro 2"}
        self.db.upsert_product(old)
        self.db.upsert_product(recent)
        with self.db.session() as db:
            db.execute("UPDATE products SET last_seen = 10 WHERE goods_key = 'goods1'")
            db.execute("UPDATE products SET last_seen = 20 WHERE goods_key = 'goods2'")
        state = app.AppState(
            self.db, EventHub(), ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        )

        batch = state.claim_user_refresh_batch({"stock_only": False})

        self.assertEqual([item["goods_key"] for item in batch["products"]], ["goods1", "goods2"])
        self.assertEqual(batch["offset"], 0)

    def test_browser_factory_claims_pending_sources_without_duplicates(self):
        self.db.upsert_source("second", "Second", origin="unit-test")
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        service._set_pending_scan_sources([self.db.get_source("demo"), self.db.get_source("second")])

        first = service.claim_browser_factory_batch(multiplier=99)
        second = service.claim_browser_factory_batch()

        self.assertEqual({source["token"] for source in first["sources"]}, {"demo", "second"})
        self.assertEqual(first["multiplier"], 5)
        self.assertEqual(first["limit"], 120)
        self.assertEqual(second["sources"], [])
        service.complete_browser_factory_lease("demo", first["lease_id"])
        self.assertFalse(service._browser_factory_leased("demo"))
        self.assertNotIn("demo", service._pending_scan_sources)

    def test_ingests_browser_products_while_server_scan_is_active(self):
        self.db.upsert_product(self.product())
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        service.scanning = True
        service._scan_lock.acquire()
        try:
            result = service.ingest_local_products(
                "demo",
                "演示店",
                [
                    {
                        "goods_key": "goods1",
                        "name": "Claude Pro 本地刷新",
                        "price": 6.5,
                        "market_price": 20,
                        "extend": {"stock_count": 4},
                        "category": {"name": "AI"},
                        "goods_type": "card",
                        "link": "https://pay.ldxp.cn/item/goods1",
                    }
                ],
                {"goods1"},
            )
        finally:
            service._scan_lock.release()

        self.assertEqual(result["matched"], 1)
        self.assertEqual(self.db.get_product("goods1")["price"], 6.5)

    def test_product_refresh_joins_its_existing_server_scan(self):
        self.db.upsert_product(self.product())
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        service._scan_lock.acquire()
        try:
            service._begin_scan("manual")
            service._set_pending_scan_sources([self.db.get_source("demo")])
            status = service.product_refresh_status("goods1")
            self.assertTrue(status["refreshing"])
            self.assertEqual(status["task"]["reason"], "manual")
            with self.assertRaises(ProductRefreshInProgress):
                service.refresh_product("goods1")
        finally:
            service._finish_scan()

    def test_scan_request_reserves_one_shared_task_before_starting_worker(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        with patch("app.threading.Thread") as thread:
            first = service.request_scan("manual")
            second = service.request_scan("manual")
            different_kind = service.request_scan("manual_proxy_only")

        self.assertTrue(first["started"])
        self.assertFalse(first["joined"])
        self.assertTrue(second["joined"])
        self.assertEqual(second["task"]["reason"], "manual")
        self.assertTrue(different_kind["busy"])
        self.assertFalse(different_kind["joined"])
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        service._finish_scan()

    def test_queues_one_server_scan_for_a_newly_submitted_source(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        with patch("app.threading.Thread") as thread:
            self.assertTrue(service.request_submitted_source_scan("demo"))
            self.assertFalse(service.request_submitted_source_scan("demo"))

        self.assertEqual(service._submitted_source_scan_queue.qsize(), 1)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_submitted_source_scan_uses_the_server_scanner(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        service._submitted_source_scan_queue.put("demo")
        service._submitted_source_scan_tokens.add("demo")
        with (
            patch.object(service, "_scan_source", return_value=(3, 2)) as scan_source,
            patch.object(service, "_publish_snapshot") as publish_snapshot,
        ):
            service._process_submitted_source_scans()

        scan_source.assert_called_once_with("demo")
        publish_snapshot.assert_called_once()
        self.assertFalse(service._submitted_source_scan_tokens)

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

    def test_resumes_a_source_from_the_saved_page_after_proxy_failure(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        first_item = {
            "goods_key": "goods1",
            "name": "Claude Pro",
            "price": 5,
            "extend": {"stock_count": 1},
            "category": {"name": "AI"},
            "goods_type": "card",
        }
        second_item = {**first_item, "goods_key": "goods2", "name": "Claude Pro 2"}
        first_client = Mock()
        first_client.shop_info.return_value = {"nickname": "Demo", "card_count": 2}
        first_client.goods_page.side_effect = [
            {"list": [first_item], "total": 2},
            LDXPError("proxy denied this source"),
        ]
        with patch("app.LDXP_PAGE_SIZE", 1), patch("app.LDXP_MAX_PAGES", 2):
            with self.assertRaises(LDXPError):
                service._scan_source("demo", client=first_client)
            checkpoint = self.db.get_or_create_scan_checkpoint("demo")
            self.assertEqual(checkpoint["goods_type"], "card")
            self.assertEqual(checkpoint["page"], 2)

            second_client = Mock()
            second_client.shop_info.return_value = {"nickname": "Demo", "card_count": 2}
            second_client.goods_page.return_value = {"list": [second_item], "total": 2}
            matched, _ = service._scan_source("demo", client=second_client)

        self.assertEqual(matched, 2)
        self.assertEqual(
            {product["goods_key"] for product in self.db.list_products()}, {"goods1", "goods2"}
        )
        with self.db.session() as db:
            self.assertIsNone(
                db.execute(
                    "SELECT 1 FROM scan_checkpoints WHERE source_token = ?", ("demo",)
                ).fetchone()
            )

    def test_uses_one_proxy_for_other_sources_before_retrying_the_paused_one(self):
        self.db.upsert_source("demo-two", "Demo two", origin="unit-test")
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        first = ProxyEndpoint("8.8.8.8:8080", "https")
        second = ProxyEndpoint("1.1.1.1:3128", "https")
        calls = []

        def scan(token, client=None):
            assert client is not None
            calls.append((token, client.proxy_url))
            if token == "demo" and client.proxy_url == first.proxy_url:
                raise LDXPError("blocked")
            return 1, 0

        result = ScanResult(source_count=2)
        with (
            patch.object(service, "_fetch_scdn_proxy", side_effect=[first, second]),
            patch.object(service, "_scan_source", side_effect=scan),
            patch.object(service._stop, "wait", return_value=False),
            patch("app.LDXP_SCDN_PROXY_CANDIDATES_PER_CYCLE", 2),
        ):
            service._scan_all_with_scdn_proxy_pool(
                self.db.list_sources(enabled_only=True), result
            )

        self.assertEqual(
            calls,
            [
                ("demo", first.proxy_url),
                ("demo-two", first.proxy_url),
                ("demo", second.proxy_url),
            ],
        )
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(result.failed, 0)

    def test_replaces_a_dead_proxy_before_trying_other_sources(self):
        self.db.upsert_source("demo-two", "Demo two", origin="unit-test")
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        first = ProxyEndpoint("8.8.8.8:8080", "https")
        second = ProxyEndpoint("1.1.1.1:3128", "https")
        calls = []

        def scan(token, client=None):
            assert client is not None
            calls.append((token, client.proxy_url))
            if client.proxy_url == first.proxy_url:
                raise LDXPTransportError("proxy connection failed")
            return 1, 0

        result = ScanResult(source_count=2)
        with (
            patch.object(service, "_fetch_scdn_proxy", side_effect=[first, second]),
            patch.object(service, "_scan_source", side_effect=scan),
            patch.object(service._stop, "wait", return_value=False),
            patch("app.LDXP_SCDN_PROXY_CANDIDATES_PER_CYCLE", 2),
        ):
            service._scan_all_with_scdn_proxy_pool(
                self.db.list_sources(enabled_only=True), result
            )

        self.assertEqual(
            calls,
            [
                ("demo", first.proxy_url),
                ("demo", second.proxy_url),
                ("demo-two", second.proxy_url),
            ],
        )
        self.assertEqual(result.succeeded, 2)

    def test_rotates_scdn_proxy_pages_after_each_candidate(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        first = ProxyEndpoint("8.8.8.8:8080", "http")
        second = ProxyEndpoint("1.1.1.1:3128", "http")
        source = Mock()
        source.fetch_page.side_effect = [([first], 3), ([second], 3)]
        with patch("app.SCDNProxySource", return_value=source):
            self.assertEqual(service._fetch_scdn_proxy(set()), first)
            self.assertEqual(service._fetch_scdn_proxy({first.endpoint}), second)

        self.assertEqual(source.fetch_page.call_args_list, [call(1), call(2)])

    def test_proxy_only_pool_scan_never_falls_back_to_server_direct_route(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        result = ScanResult(source_count=1)
        source = self.db.get_source("demo")
        self.assertIsNotNone(source)
        with (
            patch.object(self.db, "daily_proxy_count", return_value=0),
            patch.object(service, "_fetch_scdn_proxy", return_value=None),
            patch.object(service, "_scan_pending_with_default_route") as direct_scan,
            patch("app.LDXP_SCDN_PROXY_CANDIDATES_PER_CYCLE", 1),
        ):
            service._scan_all_with_scdn_proxy_pool(
                [source], result, allow_direct_fallback=False
            )

        direct_scan.assert_not_called()
        self.assertEqual(self.db.get_source("demo")["status"], "paused")

    def test_proxy_only_manual_scan_skips_direct_source_discovery(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        with (
            patch.object(service, "_discover_sources") as discover,
            patch.object(service, "_scan_all_with_scdn_proxy_pool") as proxy_scan,
        ):
            service._scan_all("manual_proxy_only")

        discover.assert_not_called()
        self.assertEqual(proxy_scan.call_args.kwargs["allow_direct_fallback"], False)

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

    def test_single_product_detail_without_stock_keeps_stock_unknown(self):
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
        self.assertEqual(product["stock_count"], -1)
        self.assertTrue(product["in_stock"])

    def test_syncs_priceai_public_snapshot_without_entering_shop_scan_queue(self):
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        latest = {"snapshot_url": "https://data.priceai.cc/v1/snapshots/demo.json"}
        snapshot = {
            "snapshot_id": "demo-snapshot",
            "products": [
                {
                    "name": "ChatGPT Plus",
                    "summary": "官方订阅",
                    "top_offers": [
                        {
                            "id": "priceai-offer-1",
                            "source_name": "公开店铺",
                            "title": "ChatGPT Plus 已接码",
                            "price": 49,
                            "status": "in_stock",
                            "stock_count": 3,
                            "url": "https://pay.ldxp.cn/item/demo-priceai",
                            "captured_at": "2026-07-25T02:00:00Z",
                        }
                    ],
                }
            ],
        }
        with patch.object(service, "_read_json_url", side_effect=[latest, snapshot]):
            result = service.sync_priceai_snapshot()

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["changed"], 1)
        source = self.db.get_source(PRICEAI_SOURCE_TOKEN)
        self.assertIsNotNone(source)
        self.assertEqual(source["source_kind"], "snapshot")
        self.assertEqual(source["url"], "https://priceai.cc/")
        product = self.db.get_product("priceai:priceai-offer-1")
        self.assertEqual(product["source_name"], "公开店铺")
        self.assertEqual(product["stock_count"], 3)
        self.assertIn("plus", product["tags"])
        self.assertEqual(
            [source["token"] for source in self.db.list_sources_due_for_scan(scheduled=False)],
            ["demo", PRICEAI_SOURCE_TOKEN],
        )
        with patch.object(service, "_read_json_url", side_effect=[latest, {"products": []}]):
            removed = service.sync_priceai_snapshot()
        self.assertEqual(removed["removed"], 1)
        self.assertIsNone(self.db.get_product("priceai:priceai-offer-1"))

    def test_snapshot_link_scan_marks_a_missing_listing_off_shelf(self):
        self.db.upsert_source(
            "snapshot-demo", "Directory snapshot", origin="unit-test", source_kind="snapshot"
        )
        self.db.upsert_product(
            {
                **self.product(stock=999),
                "source_token": "snapshot-demo",
                "source_name": "Directory snapshot",
                "link": "https://pay.ldxp.cn/item/goods1",
            }
        )
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        client = Mock()
        client.base_url = app.LDXP_BASE_URL
        client.goods_info.side_effect = LDXPError("goods not found")

        matched, changed = service._scan_source("snapshot-demo", client=client)

        product = self.db.get_product("goods1")
        self.assertEqual((matched, changed), (1, 1))
        self.assertTrue(product["off_shelf"])
        self.assertFalse(product["in_stock"])
        self.assertEqual(product["stock_count"], 0)

    def test_snapshot_link_scan_keeps_live_listing_but_clears_directory_stock_placeholder(self):
        self.db.upsert_source(
            "snapshot-demo", "Directory snapshot", origin="unit-test", source_kind="snapshot"
        )
        self.db.upsert_product(
            {
                **self.product(stock=999),
                "source_token": "snapshot-demo",
                "source_name": "Directory snapshot",
                "link": "https://pay.ldxp.cn/item/goods1",
            }
        )
        service = ScannerService(self.db, EventHub(), auto_scan_enabled=False)
        client = Mock()
        client.base_url = app.LDXP_BASE_URL
        client.goods_info.return_value = {"goods_key": "goods1", "name": "Claude Pro"}

        matched, changed = service._scan_source("snapshot-demo", client=client)

        product = self.db.get_product("goods1")
        self.assertEqual((matched, changed), (1, 1))
        self.assertFalse(product["off_shelf"])
        self.assertTrue(product["in_stock"])
        self.assertEqual(product["stock_count"], -1)

class SourcePermissionApiTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parent / "_source_permission_api.db"
        self._remove_database_files()
        self.state = create_app(self.path, seed=False)
        self.state.database.upsert_source("demo", "Demo source", origin="unit-test")
        self.app_state_patch = patch.object(app, "APP_STATE", self.state)
        self.admin_key_patch = patch.object(app, "LDXP_ADMIN_KEY", "test-admin-key")
        self.app_state_patch.start()
        self.admin_key_patch.start()
        self.server = ScannerHTTPServer(("127.0.0.1", 0), RequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.admin_key_patch.stop()
        self.app_state_patch.stop()
        self.state.scanner.stop()
        self._remove_database_files()

    def _remove_database_files(self):
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                candidate.unlink()

    def request(self, method, path, payload=None, *, admin=False):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        if admin:
            headers["X-LDXP-Admin-Key"] = "test-admin-key"
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_source_toggle_and_delete_require_admin_key(self):
        status, payload = self.request("PUT", "/api/sources/demo", {"enabled": False})
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])
        self.assertTrue(self.state.database.get_source("demo")["enabled"])

        status, payload = self.request("DELETE", "/api/sources/demo")
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])
        self.assertIsNotNone(self.state.database.get_source("demo"))

    def test_admin_can_toggle_and_delete_source(self):
        status, payload = self.request(
            "PUT", "/api/sources/demo", {"enabled": False}, admin=True
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["enabled"])
        self.assertFalse(self.state.database.get_source("demo")["enabled"])

        status, payload = self.request("DELETE", "/api/sources/demo", admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(payload["token"], "demo")
        self.assertIsNone(self.state.database.get_source("demo"))


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
        self.assertIn("source_kind", columns)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{path}{suffix}")
            if candidate.exists():
                candidate.unlink()


if __name__ == "__main__":
    unittest.main()
