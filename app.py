from __future__ import annotations

import html
import http.cookiejar
import hmac
import json
import mimetypes
import os
import queue
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DB_PATH = Path(os.getenv("LDXP_DB_PATH", str(ROOT / "data" / "ldxp.db")))
HOST = os.getenv("LDXP_HOST", "127.0.0.1")
PORT = int(os.getenv("LDXP_PORT", "8765"))
SCAN_INTERVAL = max(30, int(os.getenv("LDXP_SCAN_INTERVAL", "900")))
DISCOVERY_INTERVAL = max(300, int(os.getenv("LDXP_DISCOVERY_INTERVAL", "21600")))
AUTO_SCAN_ENABLED = os.getenv("LDXP_AUTO_SCAN_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DISCOVERY_URL = os.getenv(
    "LDXP_DISCOVERY_URL", "https://www.aibijia.org/api/community/threads"
)
LDXP_BASE_URL = os.getenv("LDXP_BASE_URL", "https://pay.ldxp.cn").rstrip("/")
CATFK_BASE_URL = os.getenv("CATFK_BASE_URL", "https://catfk.com").rstrip("/")
LDXP_PAGE_SIZE = max(1, min(1000, int(os.getenv("LDXP_PAGE_SIZE", "300"))))
LDXP_MAX_PAGES = max(1, int(os.getenv("LDXP_MAX_PAGES", "20")))
LDXP_PAGE_DELAY = max(0.0, float(os.getenv("LDXP_PAGE_DELAY", "0.05")))
LDXP_REQUEST_TIMEOUT = max(1, int(os.getenv("LDXP_REQUEST_TIMEOUT", "20")))
LDXP_FAILOVER_PROXY_URL = os.getenv("LDXP_FAILOVER_PROXY_URL", "").strip()
LDXP_DIRECT_ATTEMPTS = max(1, int(os.getenv("LDXP_DIRECT_ATTEMPTS", "1")))
LDXP_PROXY_ATTEMPTS = max(0, int(os.getenv("LDXP_PROXY_ATTEMPTS", "3")))
LDXP_RETRY_DELAY = max(0.0, float(os.getenv("LDXP_RETRY_DELAY", "0.4")))
LDXP_LOCAL_UPLOAD_MAX_ITEMS = max(
    1, int(os.getenv("LDXP_LOCAL_UPLOAD_MAX_ITEMS", "6000"))
)
LDXP_SOURCE_INTERVAL = max(0.0, float(os.getenv("LDXP_SOURCE_INTERVAL", "15")))
LDXP_ADMIN_KEY = os.getenv("LDXP_ADMIN_KEY", "").strip()


CATEGORY_DEFINITIONS = [
    {"key": "plus", "label": "Plus 全部", "terms": ["plus", "chatgpt plus", "gpt plus"]},
    {"key": "plus_sms", "label": "Plus 已接码", "terms": []},
    {"key": "plus_no_sms", "label": "Plus 未接码", "terms": []},
    {
        "key": "free",
        "label": "非 Plus / Free 全部",
        "terms": ["gpt free", "chatgpt free", "free号", "free 号", "普通号", "免费号", "非plus", "非 plus"],
    },
    {"key": "free_sms", "label": "非 Plus 已接码", "terms": []},
    {"key": "free_no_sms", "label": "非 Plus 未接码", "terms": []},
    {"key": "team", "label": "Team", "terms": ["team", "团队版", "团队账号", "团队号"]},
    {"key": "bugteam", "label": "BugTeam", "terms": ["bugteam", "bug team", "bug-team"]},
    {"key": "pro", "label": "Pro", "terms": [" pro ", "pro版", "pro账号", "pro会员", "专业版"]},
    {"key": "k12", "label": "K12", "terms": ["k12", "教育版", "学生版"]},
    {"key": "cursor", "label": "Cursor", "terms": ["cursor"]},
    {"key": "codex", "label": "Codex", "terms": ["codex"]},
    {"key": "claude", "label": "Claude", "terms": ["claude", "克劳德"]},
    {"key": "kiro", "label": "Kiro", "terms": ["kiro"]},
    {"key": "gemini", "label": "Gemini", "terms": ["gemini", "谷歌ai"]},
    {"key": "mail", "label": "邮箱", "terms": ["邮箱", "email", "e-mail", "gmail", "outlook"]},
    {
        "key": "sms",
        "label": "接码服务",
        "terms": ["gpt接码", "codex接码", "接码服务", "长效接码", "接验证码", "短信接收", "sms", "手机号验证"],
    },
]

SMS_VERIFIED_TERMS = (
    "已接码",
    "已绑手机",
    "已绑定手机",
    "带接码",
    "含接码",
    "接码完成",
    "双接码",
    "双方接码",
    "接码free号",
    "接码 free号",
)
SMS_UNVERIFIED_TERMS = (
    "未接码",
    "未绑手机",
    "未绑定手机",
    "无接码",
    "不含接码",
    "不带接码",
    "没有接码",
    "需要接码",
    "需接码",
    "需自行接码",
    "自行接码",
)

SEED_SOURCES = {
    "CodexBro": "公开索引：urlquery",
    "xdstore": "公开索引：Apifox",
    "OAGQN77Z": "公开索引：商家官网",
    "doge": "公开索引：商家官网",
    "echo_dream": "公开索引：爱比价社区",
    "E0AJV9HG": "公开索引：Bilibili",
    "6YQL25Q0": "公开索引：商家官网",
    "aiaiai001": "公开索引：商家官网",
    "caitou": "公开索引：Bilibili",
    "RRR5L2O6": "公开索引：Bilibili",
    "12sheep": "公开索引：Bilibili",
    "282D9KDL": "公开索引：V2EX",
    "88vip": "公开索引：知乎",
    "JBJJWNA5": "公开索引：社交媒体",
    "MCZ4G8UT": "公开索引：新浪",
    "zhaoyang": "自动发现：爱比价社区",
    "D92VW084": "自动发现：爱比价社区",
}
GOODS_TYPES = ("card", "article", "resource", "equity")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")
SOURCE_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]{2,64}$")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SHOP_REF_RE = re.compile(
    r"(?:https?://)?(?:pay|www)\.ldxp\.cn/shop/([A-Za-z0-9_-]{2,64})", re.IGNORECASE
)
ITEM_REF_RE = re.compile(
    r"(?:https?://)?(?:pay|www)\.ldxp\.cn/item/([A-Za-z0-9_-]{2,64})", re.IGNORECASE
)


@dataclass(frozen=True)
class SourceReference:
    base_url: str
    remote_token: str = ""
    goods_key: str = ""

    @property
    def key(self) -> str:
        if not self.remote_token:
            return ""
        if self.base_url == LDXP_BASE_URL:
            return self.remote_token
        host = urllib.parse.urlsplit(self.base_url).hostname or "source"
        return f"{host}:{self.remote_token}"


def supported_platforms() -> dict[str, str]:
    platforms = {
        "pay.ldxp.cn": LDXP_BASE_URL,
        "www.ldxp.cn": LDXP_BASE_URL,
        "catfk.com": CATFK_BASE_URL,
        "www.catfk.com": CATFK_BASE_URL,
    }
    for base_url in (LDXP_BASE_URL, CATFK_BASE_URL):
        host = (urllib.parse.urlsplit(base_url).hostname or "").casefold()
        if host:
            platforms[host] = base_url
    return platforms


def parse_source_reference(value: str, *, allow_item: bool = False) -> SourceReference:
    value = (value or "").strip()
    if not value:
        raise ValueError("请输入店铺链接、商品链接或 token")

    if "://" not in value:
        if SOURCE_KEY_RE.fullmatch(value):
            host, remote_token = value.split(":", 1)
            base_url = supported_platforms().get(host.casefold())
            if base_url is None:
                raise ValueError("采集站点不受支持")
            return SourceReference(base_url, remote_token=remote_token)
        if not TOKEN_RE.fullmatch(value.strip("/ ")):
            raise ValueError("店铺 token 格式不正确")
        return SourceReference(LDXP_BASE_URL, remote_token=value.strip("/ "))

    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").casefold()
    base_url = supported_platforms().get(host)
    if parsed.scheme.casefold() not in {"http", "https"} or base_url is None:
        raise ValueError("只支持 pay.ldxp.cn 和 catfk.com 的公开链接")
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2].casefold() not in {"shop", "item"}:
        raise ValueError("只支持公开店铺 /shop/xxx 或商品 /item/xxx 链接")
    kind = parts[-2].casefold()
    identifier = parts[-1].strip()
    if not TOKEN_RE.fullmatch(identifier):
        raise ValueError(f"{'商品标识' if kind == 'item' else '店铺 token'}格式不正确")
    if kind == "item":
        if not allow_item:
            raise ValueError("请输入店铺链接或 token")
        return SourceReference(base_url, goods_key=identifier)
    return SourceReference(base_url, remote_token=identifier)


def now_ts() -> int:
    return int(time.time())


def remaining_cycle_delay(interval: float, elapsed: float) -> float:
    return max(0.0, interval - elapsed)


def clean_text(value: Any, limit: int = 240) -> str:
    text = html.unescape(TAG_RE.sub(" ", str(value or "")))
    text = SPACE_RE.sub(" ", text).strip()
    return text[:limit]


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_source(value: str) -> str:
    return parse_source_reference(value).key


def extract_ldxp_refs(value: Any) -> tuple[set[str], set[str]]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return set(SHOP_REF_RE.findall(text)), set(ITEM_REF_RE.findall(text))


def classify_product(name: str, category_name: str = "") -> list[str]:
    # 商品详情常包含店铺通用广告词，会制造大量误报；分类只使用标题和店铺分类名。
    haystack = f" {name or ''} {category_name or ''} ".casefold()
    tags: list[str] = []
    for category in CATEGORY_DEFINITIONS:
        if any(term.casefold() in haystack for term in category["terms"]):
            tags.append(category["key"])
    title = f" {name or ''} ".casefold()
    premium_tags = {"plus", "team", "pro", "k12"}
    account_signals = (
        "成品号",
        "成品账号",
        "成品帐号",
        "普通号",
        "free号",
        " json ",
        "反代",
        " rt ",
    )
    looks_like_gpt_account = any(brand in title for brand in ("chatgpt", "gpt", "openai")) and any(
        signal in title for signal in account_signals
    )
    if looks_like_gpt_account and not premium_tags.intersection(tags) and "free" not in tags:
        tags.append("free")
    sms_status = ""
    if any(term.casefold() in title for term in SMS_UNVERIFIED_TERMS):
        sms_status = "unverified"
    elif any(term.casefold() in title for term in SMS_VERIFIED_TERMS):
        sms_status = "verified"

    if "plus" in tags:
        if sms_status == "verified":
            tags.append("plus_sms")
        elif sms_status == "unverified":
            tags.append("plus_no_sms")
    if "free" in tags:
        if sms_status == "verified":
            tags.append("free_sms")
        elif sms_status == "unverified":
            tags.append("free_no_sms")
    return tags


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    token TEXT PRIMARY KEY,
                    remote_token TEXT NOT NULL DEFAULT '',
                    base_url TEXT NOT NULL DEFAULT '',
                    entry_goods_key TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NOT NULL DEFAULT '',
                    last_scan INTEGER NOT NULL DEFAULT 0,
                    product_count INTEGER NOT NULL DEFAULT 0,
                    origin TEXT NOT NULL DEFAULT 'manual',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS products (
                    goods_key TEXT PRIMARY KEY,
                    source_token TEXT NOT NULL,
                    source_name TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    price REAL NOT NULL DEFAULT 0,
                    market_price REAL NOT NULL DEFAULT 0,
                    stock_count INTEGER NOT NULL DEFAULT -1,
                    in_stock INTEGER NOT NULL DEFAULT 1,
                    tags TEXT NOT NULL DEFAULT '[]',
                    category_name TEXT NOT NULL DEFAULT '',
                    goods_type TEXT NOT NULL DEFAULT '',
                    link TEXT NOT NULL DEFAULT '',
                    image TEXT NOT NULL DEFAULT '',
                    description_excerpt TEXT NOT NULL DEFAULT '',
                    create_time INTEGER NOT NULL DEFAULT 0,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    changed_at INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(source_token) REFERENCES sources(token) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goods_key TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock_count INTEGER NOT NULL,
                    recorded_at INTEGER NOT NULL,
                    FOREIGN KEY(goods_key) REFERENCES products(goods_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_products_active ON products(active, last_seen DESC);
                CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_token, active);
                CREATE INDEX IF NOT EXISTS idx_history_goods ON price_history(goods_key, recorded_at DESC);
                """
            )
            source_columns = {row["name"] for row in db.execute("PRAGMA table_info(sources)")}
            if "origin" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")
            if "remote_token" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN remote_token TEXT NOT NULL DEFAULT ''")
            if "base_url" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN base_url TEXT NOT NULL DEFAULT ''")
            if "entry_goods_key" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN entry_goods_key TEXT NOT NULL DEFAULT ''")
            db.execute(
                "UPDATE sources SET remote_token = token WHERE remote_token = ''"
            )
            db.execute(
                "UPDATE sources SET base_url = ? WHERE base_url = ''", (LDXP_BASE_URL,)
            )

    def seed_sources(self) -> None:
        timestamp = now_ts()
        with self.session() as db:
            db.executemany(
                """
                INSERT OR IGNORE INTO sources
                    (token, remote_token, base_url, name, url, enabled, status, origin, created_at, updated_at)
                VALUES (?, ?, ?, '', ?, 1, 'pending', ?, ?, ?)
                """,
                [
                    (token, token, LDXP_BASE_URL, f"{LDXP_BASE_URL}/shop/{token}", origin, timestamp, timestamp)
                    for token, origin in SEED_SOURCES.items()
                ],
            )
            db.executemany(
                """
                UPDATE sources SET origin = ?
                WHERE token = ? AND (origin = '' OR origin = 'manual')
                """,
                [(origin, token) for token, origin in SEED_SOURCES.items()],
            )

    def get_setting(self, key: str) -> str | None:
        with self.session() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row is not None else None

    def set_settings(self, settings: dict[str, str]) -> None:
        timestamp = now_ts()
        with self.session() as db:
            db.executemany(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                [(key, value, timestamp) for key, value in settings.items()],
            )

    def list_sources(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sources"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at ASC"
        with self.session() as db:
            return [dict(row) for row in db.execute(sql)]

    def get_source(self, token: str) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute("SELECT * FROM sources WHERE token = ?", (token,)).fetchone()
            return dict(row) if row is not None else None

    def upsert_source(
        self,
        token: str,
        name: str = "",
        enabled: bool = True,
        origin: str = "manual",
        *,
        base_url: str = LDXP_BASE_URL,
        remote_token: str | None = None,
        entry_goods_key: str = "",
    ) -> dict[str, Any]:
        remote_token = remote_token or token
        base_url = base_url.rstrip("/")
        entry_goods_key = entry_goods_key.strip()
        timestamp = now_ts()
        with self.session() as db:
            db.execute(
                """
                INSERT INTO sources (
                    token, remote_token, base_url, entry_goods_key, name, url, enabled,
                    status, origin, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET
                    remote_token = excluded.remote_token,
                    base_url = excluded.base_url,
                    entry_goods_key = CASE
                        WHEN excluded.entry_goods_key != '' THEN excluded.entry_goods_key
                        ELSE sources.entry_goods_key
                    END,
                    url = excluded.url,
                    name = CASE WHEN excluded.name != '' THEN excluded.name ELSE sources.name END,
                    enabled = excluded.enabled,
                    origin = CASE
                        WHEN sources.origin = '' OR sources.origin = 'manual' THEN excluded.origin
                        ELSE sources.origin
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    token,
                    remote_token,
                    base_url,
                    entry_goods_key,
                    name,
                    f"{base_url}/shop/{remote_token}",
                    int(enabled),
                    origin[:200],
                    timestamp,
                    timestamp,
                ),
            )
            row = db.execute("SELECT * FROM sources WHERE token = ?", (token,)).fetchone()
            return dict(row)

    def set_source_enabled(self, token: str, enabled: bool) -> bool:
        with self.session() as db:
            result = db.execute(
                "UPDATE sources SET enabled = ?, updated_at = ? WHERE token = ?",
                (int(enabled), now_ts(), token),
            )
            if not enabled:
                db.execute("UPDATE products SET active = 0 WHERE source_token = ?", (token,))
            return result.rowcount > 0

    def delete_source(self, token: str) -> bool:
        with self.session() as db:
            result = db.execute("DELETE FROM sources WHERE token = ?", (token,))
            return result.rowcount > 0

    def update_source_scan(
        self,
        token: str,
        *,
        status: str,
        name: str | None = None,
        error: str = "",
        count: int | None = None,
        scanned: bool = False,
    ) -> None:
        fields = ["status = ?", "last_error = ?", "updated_at = ?"]
        values: list[Any] = [status, error[:500], now_ts()]
        if name is not None:
            fields.append("name = ?")
            values.append(name[:200])
        if count is not None:
            fields.append("product_count = ?")
            values.append(count)
        if scanned:
            fields.append("last_scan = ?")
            values.append(now_ts())
        values.append(token)
        with self.session() as db:
            db.execute(f"UPDATE sources SET {', '.join(fields)} WHERE token = ?", values)

    def upsert_product(self, product: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        timestamp = now_ts()
        tags_json = json.dumps(product["tags"], ensure_ascii=False, separators=(",", ":"))
        with self.session() as db:
            previous = db.execute(
                "SELECT name, price, stock_count, tags, active FROM products WHERE goods_key = ?",
                (product["goods_key"],),
            ).fetchone()
            if previous is None:
                change = "new"
            elif (
                previous["name"] != product["name"]
                or float(previous["price"]) != float(product["price"])
                or int(previous["stock_count"]) != int(product["stock_count"])
                or previous["tags"] != tags_json
                or int(previous["active"]) == 0
            ):
                change = "changed"
            else:
                change = "unchanged"

            changed_at = timestamp if change != "unchanged" else None
            db.execute(
                """
                INSERT INTO products (
                    goods_key, source_token, source_name, name, price, market_price,
                    stock_count, in_stock, tags, category_name, goods_type, link, image,
                    description_excerpt, create_time, first_seen, last_seen, changed_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(goods_key) DO UPDATE SET
                    source_token = excluded.source_token,
                    source_name = excluded.source_name,
                    name = excluded.name,
                    price = excluded.price,
                    market_price = excluded.market_price,
                    stock_count = excluded.stock_count,
                    in_stock = excluded.in_stock,
                    tags = excluded.tags,
                    category_name = excluded.category_name,
                    goods_type = excluded.goods_type,
                    link = excluded.link,
                    image = excluded.image,
                    description_excerpt = excluded.description_excerpt,
                    create_time = excluded.create_time,
                    last_seen = excluded.last_seen,
                    changed_at = CASE WHEN ? IS NULL THEN products.changed_at ELSE ? END,
                    active = 1
                """,
                (
                    product["goods_key"],
                    product["source_token"],
                    product["source_name"],
                    product["name"],
                    product["price"],
                    product["market_price"],
                    product["stock_count"],
                    int(product["in_stock"]),
                    tags_json,
                    product["category_name"],
                    product["goods_type"],
                    product["link"],
                    product["image"],
                    product["description_excerpt"],
                    product["create_time"],
                    timestamp,
                    timestamp,
                    timestamp,
                    changed_at,
                    changed_at,
                ),
            )
            db.execute(
                """
                INSERT INTO price_history (goods_key, price, stock_count, recorded_at)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM price_history
                    WHERE goods_key = ? AND recorded_at = ? AND price = ? AND stock_count = ?
                )
                """,
                (
                    product["goods_key"],
                    product["price"],
                    product["stock_count"],
                    timestamp,
                    product["goods_key"],
                    timestamp,
                    product["price"],
                    product["stock_count"],
                ),
            )
            row = db.execute("SELECT * FROM products WHERE goods_key = ?", (product["goods_key"],)).fetchone()
            return change, self._product_row(row)

    def deactivate_missing(self, source_token: str, seen: set[str]) -> set[str]:
        with self.session() as db:
            active = {
                row["goods_key"]
                for row in db.execute(
                    "SELECT goods_key FROM products WHERE source_token = ? AND active = 1", (source_token,)
                )
            }
            missing = active - seen
            if missing:
                db.executemany(
                    "UPDATE products SET active = 0, changed_at = ? WHERE goods_key = ?",
                    [(now_ts(), key) for key in missing],
                )
            return missing

    @staticmethod
    def _product_row(row: sqlite3.Row) -> dict[str, Any]:
        product = dict(row)
        product["tags"] = json.loads(product.get("tags") or "[]")
        product["in_stock"] = bool(product["in_stock"])
        product["active"] = bool(product["active"])
        return product

    def list_products(self) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = db.execute(
                "SELECT * FROM products WHERE active = 1 ORDER BY changed_at DESC, price ASC"
            ).fetchall()
            return [self._product_row(row) for row in rows]

    def get_product(self, goods_key: str) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute(
                "SELECT * FROM products WHERE goods_key = ? AND active = 1", (goods_key,)
            ).fetchone()
            return self._product_row(row) if row is not None else None

    def deactivate_product(self, goods_key: str) -> bool:
        with self.session() as db:
            result = db.execute(
                "UPDATE products SET active = 0, changed_at = ? WHERE goods_key = ? AND active = 1",
                (now_ts(), goods_key),
            )
            return result.rowcount > 0

    def deactivate_source_products(self, source_token: str, goods_keys: set[str]) -> set[str]:
        if not goods_keys:
            return set()
        removed: set[str] = set()
        keys = sorted(goods_keys)
        with self.session() as db:
            for start in range(0, len(keys), 500):
                chunk = keys[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = db.execute(
                    f"""
                    SELECT goods_key FROM products
                    WHERE source_token = ? AND active = 1
                      AND goods_key IN ({placeholders})
                    """,
                    [source_token, *chunk],
                ).fetchall()
                active_keys = {str(row["goods_key"]) for row in rows}
                if not active_keys:
                    continue
                active_placeholders = ",".join("?" for _ in active_keys)
                db.execute(
                    f"""
                    UPDATE products SET active = 0, changed_at = ?
                    WHERE source_token = ? AND goods_key IN ({active_placeholders})
                    """,
                    [now_ts(), source_token, *sorted(active_keys)],
                )
                removed.update(active_keys)
        return removed

    def history(self, goods_key: str) -> list[dict[str, Any]]:
        with self.session() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT price, stock_count, recorded_at FROM price_history WHERE goods_key = ? ORDER BY recorded_at DESC LIMIT 100",
                    (goods_key,),
                )
            ]

    def stats(self) -> dict[str, Any]:
        with self.session() as db:
            product = db.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END), 0) AS in_stock,
                       COALESCE(MIN(CASE WHEN price > 0 THEN price END), 0) AS lowest_price,
                       COALESCE(MAX(last_seen), 0) AS last_scan
                FROM products WHERE active = 1
                """
            ).fetchone()
            source = db.execute(
                "SELECT COUNT(*) AS total, COALESCE(SUM(enabled), 0) AS enabled FROM sources"
            ).fetchone()
            return {
                "total": product["total"],
                "in_stock": product["in_stock"],
                "lowest_price": product["lowest_price"],
                "last_scan": product["last_scan"],
                "sources": source["total"],
                "enabled_sources": source["enabled"],
            }


class LDXPError(RuntimeError):
    pass


class LDXPClient:
    def __init__(
        self,
        base_url: str = LDXP_BASE_URL,
        timeout: int = LDXP_REQUEST_TIMEOUT,
        proxy_url: str = LDXP_FAILOVER_PROXY_URL,
        direct_attempts: int = LDXP_DIRECT_ATTEMPTS,
        proxy_attempts: int = LDXP_PROXY_ATTEMPTS,
        retry_delay: float = LDXP_RETRY_DELAY,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = max(1, timeout)
        self.proxy_url = proxy_url.strip()
        self.direct_attempts = max(1, direct_attempts)
        self.proxy_attempts = max(0, proxy_attempts)
        self.retry_delay = max(0.0, retry_delay)
        self.visitor_id = f"ldxp-scanner-{uuid.uuid4().hex[:12]}"

        cookie_jar = http.cookiejar.CookieJar()
        self.direct_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(cookie_jar),
        )
        if self.proxy_url and self.proxy_attempts:
            parsed_proxy = urllib.parse.urlsplit(self.proxy_url)
            if parsed_proxy.scheme not in {"http", "https"} or not parsed_proxy.netloc:
                raise ValueError("LDXP_FAILOVER_PROXY_URL must be an HTTP(S) proxy URL")

    def _request(self, path: str, body: bytes) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (compatible; LDXPPriceScanner/1.0)",
                "Visitorid": self.visitor_id,
            },
            method="POST",
        )

    def _post_via_proxy(self, path: str, body: bytes) -> Any:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--http1.1",
            "--compressed",
            "--connect-timeout",
            str(self.timeout),
            "--max-time",
            str(self.timeout),
            "--proxy",
            self.proxy_url,
            "--header",
            "Accept: application/json, text/plain, */*",
            "--header",
            "Content-Type: application/x-www-form-urlencoded; charset=UTF-8",
            "--header",
            "User-Agent: Mozilla/5.0 (compatible; LDXPPriceScanner/1.0)",
            "--header",
            f"Visitorid: {self.visitor_id}",
            "--data-binary",
            "@-",
            f"{self.base_url}{path}",
        ]
        try:
            completed = subprocess.run(
                command,
                input=body,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout + 3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise urllib.error.URLError(f"curl proxy request failed: {exc}") from exc
        if completed.returncode:
            error = completed.stderr.decode("utf-8", errors="replace").strip()[:240]
            raise urllib.error.URLError(
                f"curl proxy request failed ({completed.returncode}): {error}"
            )
        return json.loads(completed.stdout.decode("utf-8"))

    def post(self, path: str, fields: dict[str, Any]) -> Any:
        body = urllib.parse.urlencode(
            {key: "" if value is None else value for key, value in fields.items()}
        ).encode()
        routes: list[tuple[str, Any | None, int]] = [
            ("direct", self.direct_opener, self.direct_attempts)
        ]
        if self.proxy_url and self.proxy_attempts:
            routes.append(("proxy", None, self.proxy_attempts))

        total_attempts = sum(attempts for _, _, attempts in routes)
        failed_attempts = 0
        last_route = "direct"
        last_error: BaseException | None = None
        failover_announced = False
        for route, opener, attempts in routes:
            for _ in range(attempts):
                try:
                    if route == "proxy":
                        payload = self._post_via_proxy(path, body)
                    else:
                        request = self._request(path, body)
                        with opener.open(request, timeout=self.timeout) as response:
                            payload = json.loads(response.read().decode("utf-8"))
                except (
                    urllib.error.URLError,
                    OSError,
                    TimeoutError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ) as exc:
                    failed_attempts += 1
                    last_route = route
                    last_error = exc
                    if route == "direct" and self.proxy_url and not failover_announced:
                        print(
                            f"LDXP direct request failed for {path}; retrying via rotating proxy",
                            flush=True,
                        )
                        failover_announced = True
                    if failed_attempts < total_attempts and self.retry_delay:
                        time.sleep(self.retry_delay)
                    continue

                if not isinstance(payload, dict):
                    raise LDXPError("LDXP returned an invalid response object")
                if payload.get("code") != 1:
                    raise LDXPError(payload.get("msg") or "LDXP returned an unknown error")
                return payload.get("data")

        detail = str(last_error) if last_error is not None else "unknown transport error"
        raise LDXPError(
            f"LDXP request failed after {failed_attempts} attempts; "
            f"last route={last_route}: {detail}"
        ) from last_error

    def shop_info(self, token: str) -> dict[str, Any]:
        data = self.post("/shopApi/Shop/info", {"token": token})
        if not isinstance(data, dict):
            raise LDXPError("店铺信息格式不正确")
        return data

    def goods_page(self, token: str, goods_type: str, page: int, page_size: int = 100) -> dict[str, Any]:
        data = self.post(
            "/shopApi/Shop/goodsList",
            {
                "token": token,
                "keywords": "",
                "category_id": 0,
                "goods_type": goods_type,
                "current": page,
                "pageSize": page_size,
            },
        )
        if not isinstance(data, dict):
            raise LDXPError("商品列表格式不正确")
        return data

    def goods_info(self, goods_key: str) -> dict[str, Any]:
        data = self.post("/shopApi/Shop/goodsInfo", {"goods_key": goods_key})
        if not isinstance(data, dict):
            raise LDXPError("商品信息格式不正确")
        return data


def resolve_source_reference(value: str) -> tuple[SourceReference, str]:
    reference = parse_source_reference(value, allow_item=True)
    if not reference.goods_key:
        return reference, ""
    goods = LDXPClient(base_url=reference.base_url).goods_info(reference.goods_key)
    user = goods.get("user") or {}
    remote_token = str(user.get("token") or "").strip()
    if not TOKEN_RE.fullmatch(remote_token):
        user_link = str(user.get("link") or "")
        try:
            remote_token = parse_source_reference(user_link).remote_token
        except ValueError:
            remote_token = ""
    if not TOKEN_RE.fullmatch(remote_token):
        raise LDXPError("商品详情中没有可用的店铺 token")
    return (
        SourceReference(
            reference.base_url,
            remote_token=remote_token,
            goods_key=reference.goods_key,
        ),
        clean_text(user.get("nickname"), 200),
    )


class EventHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._clients: set[queue.Queue[dict[str, Any]]] = set()
        self._sequence = 0

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        client: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=500)
        with self._lock:
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.discard(client)

    def publish(self, event: str, data: Any) -> None:
        with self._lock:
            self._sequence += 1
            envelope = {"id": self._sequence, "event": event, "data": data}
            stale: list[queue.Queue[dict[str, Any]]] = []
            for client in self._clients:
                try:
                    client.put_nowait(envelope)
                except queue.Full:
                    try:
                        client.get_nowait()
                        client.put_nowait(envelope)
                    except (queue.Empty, queue.Full):
                        stale.append(client)
            for client in stale:
                self._clients.discard(client)


def product_from_api(
    item: dict[str, Any],
    token: str,
    source_name: str,
    base_url: str = LDXP_BASE_URL,
) -> dict[str, Any] | None:
    category = item.get("category") or {}
    category_name = str(category.get("name") or "")
    name = str(item.get("name") or "").strip()
    tags = classify_product(name, category_name)
    if not tags:
        return None
    extend = item.get("extend") or {}
    raw_stock = extend.get("stock_count")
    stock_count = safe_int(raw_stock, -1) if raw_stock is not None else -1
    goods_key = str(item.get("goods_key") or "").strip()
    if not goods_key:
        return None
    return {
        "goods_key": goods_key,
        "source_token": token,
        "source_name": source_name,
        "name": name or goods_key,
        "price": safe_float(item.get("price")),
        "market_price": safe_float(item.get("market_price")),
        "stock_count": stock_count,
        "in_stock": stock_count != 0,
        "tags": tags,
        "category_name": category_name,
        "goods_type": str(item.get("goods_type") or ""),
        "link": str(item.get("link") or f"{base_url.rstrip('/')}/item/{goods_key}"),
        "image": str(item.get("image") or ""),
        "description_excerpt": clean_text(item.get("description")),
        "create_time": safe_int(item.get("create_time")),
    }


@dataclass
class ScanResult:
    source_count: int = 0
    succeeded: int = 0
    failed: int = 0
    matched: int = 0
    changed: int = 0


class ProductRefreshBusy(RuntimeError):
    pass


class LocalScanBusy(RuntimeError):
    pass


class ScannerService:
    def __init__(
        self,
        database: Database,
        events: EventHub,
        interval: int = SCAN_INTERVAL,
        auto_scan_enabled: bool = AUTO_SCAN_ENABLED,
    ):
        self.database = database
        self.events = events
        self.interval = interval
        self.auto_scan_enabled = auto_scan_enabled
        self.source_interval = LDXP_SOURCE_INTERVAL
        self._scan_lock = threading.Lock()
        self._local_ingest_lock = threading.Lock()
        self._product_refresh_lock = threading.Lock()
        self._refreshing_products: set[str] = set()
        self._stop = threading.Event()
        self._schedule_wakeup = threading.Event()
        self._schedule_state_lock = threading.Lock()
        self._scheduler_thread: threading.Thread | None = None
        self.scanning = False
        self.last_started = 0
        self.last_completed = 0
        self.last_discovery = 0

    def start(self) -> None:
        self._scheduler_thread = threading.Thread(target=self._schedule_loop, name="scanner-scheduler", daemon=True)
        self._scheduler_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._schedule_wakeup.set()

    def configure_schedule(self, *, enabled: bool, interval: int) -> None:
        with self._schedule_state_lock:
            self.auto_scan_enabled = enabled
            self.interval = max(60, interval)
        self._schedule_wakeup.set()
        self.events.publish(
            "schedule_status",
            {
                "enabled": self.auto_scan_enabled,
                "interval": self.interval,
                "source_interval": self.source_interval,
            },
        )

    def _schedule_loop(self) -> None:
        delay = float(self.interval)
        while not self._stop.is_set():
            with self._schedule_state_lock:
                enabled = self.auto_scan_enabled
                interval = self.interval
            if not enabled:
                self._schedule_wakeup.wait()
                self._schedule_wakeup.clear()
                with self._schedule_state_lock:
                    delay = float(self.interval)
                continue
            if self._schedule_wakeup.wait(delay):
                self._schedule_wakeup.clear()
                with self._schedule_state_lock:
                    delay = float(self.interval)
                continue
            if self._stop.is_set():
                break
            cycle_started = time.monotonic()
            self._scan_all("scheduled")
            elapsed = time.monotonic() - cycle_started
            with self._schedule_state_lock:
                interval = self.interval
            delay = remaining_cycle_delay(float(interval), elapsed)

    def trigger(self, reason: str = "manual") -> bool:
        if self.scanning or self._scan_lock.locked() or self._local_ingest_lock.locked():
            return False
        thread = threading.Thread(target=self._scan_all, args=(reason,), name="scanner-worker", daemon=True)
        thread.start()
        return True

    @staticmethod
    def _load_single_product(
        client: LDXPClient, existing: dict[str, Any], remote_token: str
    ) -> dict[str, Any]:
        goods_key = str(existing["goods_key"])
        goods_type = str(existing.get("goods_type") or "")
        if goods_type:
            try:
                page = 1
                page_size = LDXP_PAGE_SIZE
                while page <= LDXP_MAX_PAGES:
                    payload = client.goods_page(remote_token, goods_type, page, page_size)
                    items = payload.get("list") or []
                    for item in items:
                        if str(item.get("goods_key") or "") == goods_key:
                            return item
                    total = safe_int(payload.get("total"), len(items))
                    if not items or page * page_size >= total or len(items) < page_size:
                        break
                    page += 1
            except LDXPError:
                pass
        return client.goods_info(goods_key)

    def refresh_product(self, goods_key: str) -> tuple[str, dict[str, Any] | None]:
        existing = self.database.get_product(goods_key)
        if existing is None:
            raise KeyError(goods_key)
        with self._product_refresh_lock:
            if goods_key in self._refreshing_products:
                raise ProductRefreshBusy(goods_key)
            self._refreshing_products.add(goods_key)
        try:
            source = self.database.get_source(str(existing["source_token"]))
            if source is None:
                raise KeyError(existing["source_token"])
            base_url = str(source.get("base_url") or LDXP_BASE_URL)
            remote_token = str(source.get("remote_token") or source["token"])
            item = self._load_single_product(
                LDXPClient(base_url=base_url), existing, remote_token
            )
            product = product_from_api(
                item,
                str(existing["source_token"]),
                str(existing["source_name"] or existing["source_token"]),
                base_url,
            )
            if product is None:
                self.database.deactivate_product(goods_key)
                self.events.publish("product_refresh_remove", {"goods_key": goods_key})
                return "removed", None
            raw_stock = (item.get("extend") or {}).get("stock_count")
            if raw_stock is None:
                product["stock_count"] = int(existing["stock_count"])
                product["in_stock"] = bool(existing["in_stock"])
            change, saved = self.database.upsert_product(product)
            self.events.publish(
                "product_refresh", {"change": change, "product": saved}
            )
            return change, saved
        finally:
            with self._product_refresh_lock:
                self._refreshing_products.discard(goods_key)

    def ingest_local_source(
        self, token: str, source_name: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        source = self.database.get_source(token)
        if source is None:
            raise KeyError(token)
        if not source.get("enabled"):
            raise ValueError("采集源已停用")
        if self.scanning or self._scan_lock.locked():
            raise LocalScanBusy(token)
        if not self._local_ingest_lock.acquire(blocking=False):
            raise LocalScanBusy(token)

        try:
            clean_source_name = clean_text(source_name or source.get("name") or token, 200)
            seen: set[str] = set()
            matched = 0
            changed = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                product = product_from_api(
                    item, token, clean_source_name, str(source.get("base_url") or LDXP_BASE_URL)
                )
                if product is None:
                    continue
                matched += 1
                seen.add(product["goods_key"])
                change, saved = self.database.upsert_product(product)
                if change != "unchanged":
                    changed += 1
                self.events.publish("product", {"change": change, "product": saved})

            removed_keys = self.database.deactivate_missing(token, seen)
            for goods_key in removed_keys:
                self.events.publish("product_remove", {"goods_key": goods_key})
            self.database.update_source_scan(
                token,
                status="ok",
                name=clean_source_name,
                error="",
                count=matched,
                scanned=True,
            )
            result = {
                "token": token,
                "name": clean_source_name,
                "matched": matched,
                "changed": changed,
                "removed": len(removed_keys),
            }
            self.events.publish("local_scan_status", {"phase": "source_completed", **result})
            return result
        finally:
            self._local_ingest_lock.release()

    def ingest_local_products(
        self,
        token: str,
        source_name: str,
        items: list[dict[str, Any]],
        requested_keys: set[str],
    ) -> dict[str, Any]:
        source = self.database.get_source(token)
        if source is None:
            raise KeyError(token)
        if not source.get("enabled"):
            raise ValueError("采集源已停用")
        if self.scanning or self._scan_lock.locked():
            raise LocalScanBusy(token)
        if not self._local_ingest_lock.acquire(blocking=False):
            raise LocalScanBusy(token)

        try:
            valid_requested: set[str] = set()
            for goods_key in requested_keys:
                existing = self.database.get_product(goods_key)
                if existing is not None and str(existing.get("source_token")) == token:
                    valid_requested.add(goods_key)
            if not valid_requested:
                raise ValueError("当前筛选中没有属于该采集源的有效商品")
            requested_keys = valid_requested
            clean_source_name = clean_text(source_name or source.get("name") or token, 200)
            found: set[str] = set()
            changed = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                goods_key = clean_text(item.get("goods_key"), 200)
                if not goods_key or goods_key not in requested_keys:
                    continue
                existing = self.database.get_product(goods_key)
                product = product_from_api(
                    item, token, clean_source_name, str(source.get("base_url") or LDXP_BASE_URL)
                )
                if product is None:
                    continue
                raw_stock = (item.get("extend") or {}).get("stock_count")
                if (
                    raw_stock is None
                    and existing is not None
                    and str(existing.get("source_token")) == token
                ):
                    product["stock_count"] = int(existing["stock_count"])
                    product["in_stock"] = bool(existing["in_stock"])
                found.add(goods_key)
                change, saved = self.database.upsert_product(product)
                if change != "unchanged":
                    changed += 1
                self.events.publish("product", {"change": change, "product": saved})

            removed_keys = self.database.deactivate_source_products(token, requested_keys - found)
            for goods_key in removed_keys:
                self.events.publish("product_remove", {"goods_key": goods_key})
            self.database.update_source_scan(
                token,
                status="ok",
                name=clean_source_name,
                error="",
                scanned=True,
            )
            return {
                "token": token,
                "matched": len(found),
                "changed": changed,
                "removed": len(removed_keys),
            }
        finally:
            self._local_ingest_lock.release()

    def _publish_status(self, phase: str, **extra: Any) -> None:
        self.events.publish(
            "scan_status",
            {
                "phase": phase,
                "scanning": self.scanning,
                "last_started": self.last_started,
                "last_completed": self.last_completed,
                **extra,
            },
        )

    @staticmethod
    def _read_json_url(url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; LDXPPriceScanner/1.0)",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _discover_sources(self, force: bool = False) -> tuple[int, int]:
        timestamp = now_ts()
        if not force and timestamp - self.last_discovery < DISCOVERY_INTERVAL:
            return 0, 0
        self.events.publish(
            "discovery_status", {"phase": "started", "url": DISCOVERY_URL, "at": timestamp}
        )
        existing = {source["token"] for source in self.database.list_sources()}
        documents: list[Any] = []
        payload = self._read_json_url(DISCOVERY_URL)
        documents.append(payload)
        threads = payload.get("threads") if isinstance(payload, dict) else []
        for thread in (threads or [])[:60]:
            thread_id = str((thread or {}).get("id") or "")
            if not thread_id:
                continue
            try:
                documents.append(
                    self._read_json_url(f"{DISCOVERY_URL}/{urllib.parse.quote(thread_id, safe='')}")
                )
            except Exception:
                continue

        tokens: set[str] = set()
        item_keys: set[str] = set()
        for document in documents:
            found_tokens, found_items = extract_ldxp_refs(document)
            tokens.update(found_tokens)
            item_keys.update(found_items)

        client = LDXPClient()
        for goods_key in sorted(item_keys)[:100]:
            try:
                goods = client.goods_info(goods_key)
                token = str((goods.get("user") or {}).get("token") or "")
                if TOKEN_RE.fullmatch(token):
                    tokens.add(token)
            except Exception:
                continue

        added = 0
        valid = 0
        for token in sorted(tokens)[:100]:
            try:
                info = client.shop_info(token)
                valid += 1
                if token not in existing:
                    self.database.upsert_source(
                        token,
                        str(info.get("nickname") or token),
                        enabled=True,
                        origin="自动发现：爱比价社区",
                    )
                    added += 1
            except Exception:
                continue
        self.last_discovery = timestamp
        self.events.publish(
            "discovery_status",
            {
                "phase": "completed",
                "found": len(tokens),
                "valid": valid,
                "added": added,
                "at": timestamp,
            },
        )
        return valid, added

    def _scan_all(self, reason: str) -> None:
        if reason == "scheduled" and not self.auto_scan_enabled:
            return
        if self._local_ingest_lock.locked():
            return
        if not self._scan_lock.acquire(blocking=False):
            return
        result = ScanResult()
        self.scanning = True
        self.last_started = now_ts()
        self._publish_status("started", reason=reason)
        try:
            try:
                self._discover_sources(force=reason in {"startup", "discovery"})
            except Exception as exc:
                self.last_discovery = now_ts()
                self.events.publish(
                    "discovery_status",
                    {"phase": "error", "error": str(exc) or exc.__class__.__name__},
                )
            sources = self.database.list_sources(enabled_only=True)
            result.source_count = len(sources)
            for index, source in enumerate(sources, start=1):
                if self._stop.is_set():
                    break
                if reason == "scheduled" and not self.auto_scan_enabled:
                    break
                source_started = time.monotonic()
                token = source["token"]
                self.database.update_source_scan(token, status="scanning")
                self._publish_status(
                    "source_started", token=token, source_index=index, source_total=len(sources)
                )
                try:
                    matched, changed = self._scan_source(token)
                    result.succeeded += 1
                    result.matched += matched
                    result.changed += changed
                except Exception as exc:  # one bad shop must not stop the full sweep
                    result.failed += 1
                    message = str(exc) or exc.__class__.__name__
                    self.database.update_source_scan(
                        token, status="error", error=message, count=0, scanned=True
                    )
                    self._publish_status("source_error", token=token, error=message)
                if index < len(sources):
                    source_elapsed = time.monotonic() - source_started
                    source_delay = remaining_cycle_delay(self.source_interval, source_elapsed)
                    if source_delay and self._stop.wait(source_delay):
                        break
        finally:
            self.scanning = False
            self.last_completed = now_ts()
            self._scan_lock.release()
            snapshot = {
                "stats": self.database.stats(),
                "sources": self.database.list_sources(),
                "scanning": False,
                "last_started": self.last_started,
                "last_completed": self.last_completed,
            }
            self.events.publish("snapshot", snapshot)
            self._publish_status("completed", result=result.__dict__)

    def _scan_source(self, token: str) -> tuple[int, int]:
        source = self.database.get_source(token)
        if source is None:
            raise KeyError(token)
        base_url = str(source.get("base_url") or LDXP_BASE_URL)
        remote_token = str(source.get("remote_token") or token)
        client = LDXPClient(base_url=base_url)
        info = client.shop_info(remote_token)
        source_name = str(info.get("nickname") or remote_token)
        self.database.update_source_scan(token, status="scanning", name=source_name)
        seen: set[str] = set()
        changed_count = 0
        matched_count = 0

        available_types = [
            goods_type
            for goods_type in GOODS_TYPES
            if safe_int(info.get(f"{goods_type}_count"), 0) > 0
        ]
        if not available_types:
            available_types = list(GOODS_TYPES)

        for goods_type in available_types:
            page = 1
            page_size = LDXP_PAGE_SIZE
            while page <= LDXP_MAX_PAGES:
                payload = client.goods_page(remote_token, goods_type, page, page_size)
                items = payload.get("list") or []
                total = safe_int(payload.get("total"), len(items))
                for item in items:
                    product = product_from_api(item, token, source_name, base_url)
                    if product is None:
                        continue
                    matched_count += 1
                    seen.add(product["goods_key"])
                    change, saved = self.database.upsert_product(product)
                    if change != "unchanged":
                        changed_count += 1
                    self.events.publish("product", {"change": change, "product": saved})
                if not items or page * page_size >= total or len(items) < page_size:
                    break
                page += 1
                if LDXP_PAGE_DELAY:
                    time.sleep(LDXP_PAGE_DELAY)

        entry_goods_key = str(source.get("entry_goods_key") or "").strip()
        if entry_goods_key and entry_goods_key not in seen:
            item = client.goods_info(entry_goods_key)
            product = product_from_api(item, token, source_name, base_url)
            if product is not None:
                matched_count += 1
                seen.add(product["goods_key"])
                change, saved = self.database.upsert_product(product)
                if change != "unchanged":
                    changed_count += 1
                self.events.publish("product", {"change": change, "product": saved})

        removed_keys = self.database.deactivate_missing(token, seen)
        for goods_key in removed_keys:
            self.events.publish("product_remove", {"goods_key": goods_key})
        self.database.update_source_scan(
            token,
            status="ok",
            name=source_name,
            error="",
            count=matched_count,
            scanned=True,
        )
        self._publish_status(
            "source_completed",
            token=token,
            name=source_name,
            matched=matched_count,
            changed=changed_count,
            removed=len(removed_keys),
        )
        return matched_count, changed_count


class AppState:
    def __init__(self, database: Database, events: EventHub, scanner: ScannerService):
        self.database = database
        self.events = events
        self.scanner = scanner

    def snapshot(self, include_products: bool = True) -> dict[str, Any]:
        payload = {
            "stats": self.database.stats(),
            "sources": self.database.list_sources(),
            "categories": [{"key": item["key"], "label": item["label"]} for item in CATEGORY_DEFINITIONS],
            "scanning": self.scanner.scanning,
            "last_started": self.scanner.last_started,
            "last_completed": self.scanner.last_completed,
            "last_discovery": self.scanner.last_discovery,
            "scan_interval": self.scanner.interval,
            "discovery_interval": DISCOVERY_INTERVAL,
            "auto_scan_enabled": self.scanner.auto_scan_enabled,
            "source_interval": self.scanner.source_interval,
            "page_size": LDXP_PAGE_SIZE,
            "failover_proxy_enabled": bool(LDXP_FAILOVER_PROXY_URL),
        }
        if include_products:
            payload["products"] = self.database.list_products()
        return payload


APP_STATE: AppState | None = None


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "LDXPScanner/1.0"

    @property
    def app(self) -> AppState:
        assert APP_STATE is not None
        return APP_STATE

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}\n")
        sys.stdout.flush()

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _require_admin(self) -> bool:
        supplied = self.headers.get("X-LDXP-Admin-Key", "")
        if not LDXP_ADMIN_KEY or not hmac.compare_digest(supplied, LDXP_ADMIN_KEY):
            self._error(HTTPStatus.FORBIDDEN, "该操作仅允许服务器后台执行")
            return False
        return True

    def _read_json(self, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
        length = safe_int(self.headers.get("Content-Length"), 0)
        if length <= 0:
            return {}
        if length > max_bytes:
            raise ValueError("请求体过大")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON 格式不正确") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是对象")
        return payload

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._send_json({"ok": True, **self.app.snapshot(include_products=False)})
        elif path == "/api/state":
            self._send_json({"ok": True, **self.app.snapshot()})
        elif path == "/api/events":
            self._serve_events()
        elif path.startswith("/api/history/"):
            goods_key = urllib.parse.unquote(path.removeprefix("/api/history/"))
            self._send_json({"ok": True, "history": self.app.database.history(goods_key)})
        elif path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "接口不存在")
        else:
            self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/discover":
            if not self._require_admin():
                return
            started = self.app.scanner.trigger("discovery")
            self._send_json(
                {
                    "ok": True,
                    "started": started,
                    "message": "源发现与扫描已启动" if started else "扫描正在进行中",
                },
                HTTPStatus.ACCEPTED,
            )
            return
        if path == "/api/scan":
            if not self._require_admin():
                return
            started = self.app.scanner.trigger("manual")
            self._send_json(
                {"ok": True, "started": started, "message": "扫描已启动" if started else "扫描正在进行中"},
                HTTPStatus.ACCEPTED,
            )
            return
        if path == "/api/local-scan/source":
            try:
                payload = self._read_json(max_bytes=8 * 1024 * 1024)
                token = normalize_source(str(payload.get("token") or ""))
                if payload.get("complete") is not True:
                    raise ValueError("本地扫描未完成，拒绝覆盖服务器数据")
                items = payload.get("items")
                if not isinstance(items, list):
                    raise ValueError("商品列表格式不正确")
                if len(items) > LDXP_LOCAL_UPLOAD_MAX_ITEMS:
                    raise ValueError("单店商品数超过本地扫描上限")
                result = self.app.scanner.ingest_local_source(
                    token,
                    str(payload.get("source_name") or token),
                    items,
                )
                self._send_json({"ok": True, **result})
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "采集源不存在")
            except LocalScanBusy:
                self._error(HTTPStatus.CONFLICT, "服务器正在处理其他扫描")
            return
        if path == "/api/local-scan/products":
            try:
                payload = self._read_json(max_bytes=8 * 1024 * 1024)
                token = normalize_source(str(payload.get("token") or ""))
                items = payload.get("items")
                requested = payload.get("requested_keys")
                if not isinstance(items, list) or not isinstance(requested, list):
                    raise ValueError("当前筛选刷新格式不正确")
                if len(items) > LDXP_LOCAL_UPLOAD_MAX_ITEMS or len(requested) > LDXP_LOCAL_UPLOAD_MAX_ITEMS:
                    raise ValueError("当前筛选商品数超过上限")
                requested_keys = {
                    clean_text(value, 200)
                    for value in requested
                    if clean_text(value, 200)
                }
                result = self.app.scanner.ingest_local_products(
                    token,
                    str(payload.get("source_name") or token),
                    items,
                    requested_keys,
                )
                self._send_json({"ok": True, **result})
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "采集源不存在")
            except LocalScanBusy:
                self._error(HTTPStatus.CONFLICT, "服务器正在处理其他扫描")
            return
        product_prefix = "/api/products/"
        product_suffix = "/refresh"
        if path.startswith(product_prefix) and path.endswith(product_suffix):
            if not self._require_admin():
                return
            encoded_key = path[len(product_prefix) : -len(product_suffix)]
            goods_key = urllib.parse.unquote(encoded_key).strip()
            if not goods_key or "/" in goods_key or len(goods_key) > 200:
                self._error(HTTPStatus.BAD_REQUEST, "商品标识无效")
                return
            try:
                change, product = self.app.scanner.refresh_product(goods_key)
                self._send_json(
                    {
                        "ok": True,
                        "change": change,
                        "product": product,
                        "removed": product is None,
                        "message": "该商品已单独刷新",
                    }
                )
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "商品不存在或已下架")
            except ProductRefreshBusy:
                self._error(HTTPStatus.CONFLICT, "该商品正在刷新")
            except LDXPError as exc:
                self._error(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        if path == "/api/sources":
            try:
                payload = self._read_json()
                reference, source_name = resolve_source_reference(
                    str(payload.get("source") or payload.get("token") or "")
                )
                token = reference.key
                source = self.app.database.upsert_source(
                    token,
                    source_name,
                    enabled=True,
                    origin="网页手动添加",
                    base_url=reference.base_url,
                    remote_token=reference.remote_token,
                    entry_goods_key=reference.goods_key,
                )
                self._send_json({"ok": True, "source": source}, HTTPStatus.CREATED)
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except LDXPError as exc:
                self._error(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        self._error(HTTPStatus.NOT_FOUND, "接口不存在")

    def do_PUT(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/settings/scan":
            if not self._require_admin():
                return
            try:
                payload = self._read_json()
                enabled = payload.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("自动扫描开关必须是布尔值")
                interval_minutes = safe_int(payload.get("interval_minutes"), 0)
                if interval_minutes < 1 or interval_minutes > 1440:
                    raise ValueError("刷新周期必须在 1 到 1440 分钟之间")
                interval = interval_minutes * 60
                self.app.database.set_settings(
                    {
                        "auto_scan_enabled": "true" if enabled else "false",
                        "scan_interval": str(interval),
                    }
                )
                self.app.scanner.configure_schedule(enabled=enabled, interval=interval)
                self._send_json(
                    {
                        "ok": True,
                        "auto_scan_enabled": enabled,
                        "scan_interval": interval,
                        "source_interval": self.app.scanner.source_interval,
                    }
                )
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path.startswith("/api/sources/"):
            token = urllib.parse.unquote(path.removeprefix("/api/sources/"))
            try:
                token = normalize_source(token)
                payload = self._read_json()
                enabled = bool(payload.get("enabled"))
                if not self.app.database.set_source_enabled(token, enabled):
                    self._error(HTTPStatus.NOT_FOUND, "采集源不存在")
                    return
                self._send_json({"ok": True, "token": token, "enabled": enabled})
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._error(HTTPStatus.NOT_FOUND, "接口不存在")

    def do_DELETE(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/sources/"):
            try:
                token = normalize_source(urllib.parse.unquote(path.removeprefix("/api/sources/")))
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if not self.app.database.delete_source(token):
                self._error(HTTPStatus.NOT_FOUND, "采集源不存在")
                return
            self._send_json({"ok": True, "token": token})
            return
        self._error(HTTPStatus.NOT_FOUND, "接口不存在")

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        static_root = STATIC_DIR.resolve()
        if static_root not in candidate.parents and candidate != static_root:
            self._error(HTTPStatus.FORBIDDEN, "路径不允许")
            return
        if not candidate.is_file():
            candidate = STATIC_DIR / "index.html"
        try:
            body = candidate.read_bytes()
        except OSError:
            self._error(HTTPStatus.NOT_FOUND, "页面不存在")
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_events(self) -> None:
        client = self.app.events.subscribe()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            ready = json.dumps(
                {"connected": True, "scanning": self.app.scanner.scanning},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.wfile.write(f"event: ready\ndata: {ready}\n\n".encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    envelope = client.get(timeout=15)
                    data = json.dumps(envelope["data"], ensure_ascii=False, separators=(",", ":"))
                    message = f"id: {envelope['id']}\nevent: {envelope['event']}\ndata: {data}\n\n"
                except queue.Empty:
                    message = f": heartbeat {now_ts()}\n\n"
                self.wfile.write(message.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.app.events.unsubscribe(client)


class ScannerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_app(db_path: Path | str = DB_PATH, seed: bool = True) -> AppState:
    database = Database(db_path)
    if seed:
        database.seed_sources()
    events = EventHub()
    saved_enabled = database.get_setting("auto_scan_enabled")
    saved_interval = database.get_setting("scan_interval")
    auto_scan_enabled = (
        saved_enabled.strip().lower() in {"1", "true", "yes", "on"}
        if saved_enabled is not None
        else AUTO_SCAN_ENABLED
    )
    interval = max(60, safe_int(saved_interval, SCAN_INTERVAL))
    scanner = ScannerService(
        database,
        events,
        interval=interval,
        auto_scan_enabled=auto_scan_enabled,
    )
    return AppState(database, events, scanner)


def main() -> None:
    global APP_STATE
    APP_STATE = create_app()
    server = ScannerHTTPServer((HOST, PORT), RequestHandler)

    def stop_server(signum: int, frame: Any) -> None:
        del signum, frame
        APP_STATE.scanner.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_server)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, stop_server)

    APP_STATE.scanner.start()
    print(f"LDXP 扫货台启动：http://{HOST}:{PORT}，扫描间隔 {SCAN_INTERVAL} 秒", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        APP_STATE.scanner.stop()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
