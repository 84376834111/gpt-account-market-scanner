from __future__ import annotations

import html
import http.cookiejar
import hmac
import ipaddress
import json
import math
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
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


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
LDXP_SCDN_PROXY_POOL_ENABLED = os.getenv(
    "LDXP_SCDN_PROXY_POOL_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}
LDXP_SCDN_PROXY_PAGE_URL = os.getenv(
    "LDXP_SCDN_PROXY_PAGE_URL", "https://proxy.scdn.io/get_proxies.php"
).strip()
LDXP_SCDN_PROXY_PROTOCOL = os.getenv("LDXP_SCDN_PROXY_PROTOCOL", "http").strip().lower()
LDXP_SCDN_PROXY_PAGE_SIZE = max(
    10, min(100, int(os.getenv("LDXP_SCDN_PROXY_PAGE_SIZE", "100")))
)
LDXP_SCDN_PROXY_CANDIDATES_PER_CYCLE = max(
    1, min(30, int(os.getenv("LDXP_SCDN_PROXY_CANDIDATES_PER_CYCLE", "8")))
)
LDXP_SCDN_PROXY_ROUNDS_PER_CYCLE = max(
    1, min(30, int(os.getenv("LDXP_SCDN_PROXY_ROUNDS_PER_CYCLE", "8")))
)
LDXP_SCDN_PROXY_TIMEOUT = max(
    2, min(LDXP_REQUEST_TIMEOUT, int(os.getenv("LDXP_SCDN_PROXY_TIMEOUT", "6")))
)
LDXP_PROXY_SOURCE_INTERVAL = max(
    0.0, float(os.getenv("LDXP_PROXY_SOURCE_INTERVAL", "0.25"))
)
PRICEAI_LATEST_URL = os.getenv("PRICEAI_LATEST_URL", "https://data.priceai.cc/latest.json").strip()
PRICEAI_SNAPSHOT_HOST = "data.priceai.cc"
PRICEAI_SOURCE_TOKEN = "priceai.cc:top5"
PRICEAI_SOURCE_URL = "https://priceai.cc/"
PRICEAI_REQUEST_TIMEOUT = max(2, int(os.getenv("PRICEAI_REQUEST_TIMEOUT", "20")))
LDXP_AI_CLASSIFIER_API_URL = os.getenv("LDXP_AI_CLASSIFIER_API_URL", "").strip().rstrip("/")
LDXP_AI_CLASSIFIER_API_KEY = os.getenv("LDXP_AI_CLASSIFIER_API_KEY", "").strip()
LDXP_AI_CLASSIFIER_MODEL = os.getenv("LDXP_AI_CLASSIFIER_MODEL", "").strip()
LDXP_AI_CLASSIFIER_BATCH_SIZE = max(
    1, min(50, int(os.getenv("LDXP_AI_CLASSIFIER_BATCH_SIZE", "40")))
)
LDXP_AI_CLASSIFIER_DELAY = max(
    0.0, float(os.getenv("LDXP_AI_CLASSIFIER_DELAY", "0.25"))
)
# AI classification is intentionally disabled. Product tagging is deterministic and
# based solely on the title rules below.
AI_CLASSIFICATION_ENABLED = False
PRODUCT_STREAM_DEFAULT_LIMIT = 12
PRODUCT_STREAM_MAX_LIMIT = 500
UNKNOWN_OR_ZERO_REFRESH_INTERVAL = 6 * 60 * 60
LOW_STOCK_REFRESH_INTERVAL = 20 * 60
NORMAL_STOCK_REFRESH_INTERVAL = 45 * 60
HIGH_STOCK_REFRESH_INTERVAL = 90 * 60
OUT_OF_STOCK_REFRESH_INTERVALS = (
    (24 * 60 * 60, 4 * 60 * 60),
    (3 * 24 * 60 * 60, 6 * 60 * 60),
    (7 * 24 * 60 * 60, 12 * 60 * 60),
    (float("inf"), 24 * 60 * 60),
)
BEIJING_TZ = timezone(timedelta(hours=8))


CATEGORY_DEFINITIONS = [
    {"key": "plus", "label": "Plus 全部", "terms": ["plus", "chatgpt plus", "gpt plus"]},
    {"key": "plus_sms", "label": "Plus 已接码", "terms": []},
    {"key": "plus_no_sms", "label": "Plus 未接码", "terms": []},
    {
        "key": "free",
        "label": "非 Plus / Free 全部",
        "terms": ["free", "free号", "free 号", "普通号", "免费号", "非plus", "非 plus"],
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
    {
        "key": "mail",
        "label": "邮箱",
        "terms": [
            "邮箱", "email", "e-mail", "gmail", "hotmail", "outlook",
            "谷歌账号", "微软账号",
        ],
    },
    {
        "key": "sms",
        "label": "接码服务",
        "terms": ["gpt接码", "codex接码", "接码服务", "长效接码", "接验证码", "短信接收", "sms", "手机号验证"],
    },
]

# Additional title terms and exclusions distilled from the current catalog.  The
# base definitions retain the established category vocabulary; these filters make
# ambiguous terms such as "Free" and "Pro" safe to use on their own.
CATEGORY_EXTRA_TERMS: dict[str, tuple[str, ...]] = {
    "plus": ("chatplus", "plus\u6210\u54c1", "plus\u6708\u5361", "plus\u4ee3\u5145", "plus\u76f4\u5145"),
    "free": ("free\u6210\u54c1", "free\u8d26\u53f7", "free\u666e\u53f7", "free\u767d\u53f7"),
    "team": ("business", "team \u5b50\u53f7", "team\u6bcd\u53f7", "team\u5171\u4eab\u8f66"),
    "bugteam": ("team bug", "gpt team bug", "bug\u7684team"),
    "pro": ("pro20x", "pro5x", "20x pro", "5x pro", "x20 pro", "x5 pro"),
    "cursor": ("cursorpro", "cursorultra"),
    "codex": ("claude code", "gptcodex", "openai codex"),
    "gemini": ("google ai pro", "google ai ultra", "geminipro", "\u53cc\u5b50\u661f"),
    "mail": ("googlemail", "icloud\u90ae\u7bb1", "yahoo", "\u96c5\u864e", "edu\u90ae\u7bb1", "\u6559\u80b2\u90ae\u7bb1"),
    "sms": ("\u77ed\u4fe1\u9a8c\u8bc1\u7801", "\u9a8c\u8bc1\u7801\u63a5\u7801", "\u624b\u673a\53f7\u63a5\u7801", "\u5b9e\u4f53\u624b\u673a\53f7\u63a5\u7801", "api\u63a5\u7801"),
}
CATEGORY_EXCLUDE_TERMS: dict[str, tuple[str, ...]] = {
    "plus": ("plus\u53f7\u6c60", "codexplus", "keypal plus", "\u4eac\u4e1cplus\u4f1a\u5458", "snowplus"),
    "free": ("codefree", "free\u53f7\u6c60", "claude free", "kiro free", "grok free", "cursor free"),
    "team": ("bugteam", "bug team", "bug-team", "k12", "gptk12", "gpt_k12"),
    "pro": ("gemini pro", "claude pro", "cursor pro", "kiro pro", "perplexity pro", "capcut pro", "plus pro5"),
    "sms": ("\u5df2\u63a5\u7801", "\u5df2\u7ecf\u63a5\u7801", "\u672a\u63a5\u7801", "\u65e0\u63a5\u7801", "\u6ca1\u63a5\u7801", "\u4e0d\u63a5\u7801", "\u9700\u8981\u81ea\u5df1\u63a5\u7801", "\u9700\u81ea\u884c\u63a5\u7801", "\u63a5\u7801\u6559\u7a0b"),
    "mail": ("\u63a5\u7801\u5e73\u53f0", "\u77ed\u4fe1\u63a5\u7801\u5e73\u53f0"),
}

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
    "需要自己接码",
    "需自己接码",
    "自己接码",
    "需自行接码",
    "自行接码",
)
ACCOUNT_TIER_PRIORITY = ("bugteam", "k12", "free", "plus", "team")
ACCOUNT_TIER_KEYS = frozenset(ACCOUNT_TIER_PRIORITY)
SMS_STATUS_KEYS = frozenset({"plus_sms", "plus_no_sms", "free_sms", "free_no_sms"})

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
PARENTHETICAL_RE = re.compile(r"\([^()]*\)|\uff08[^\uff08\uff09]*\uff09")


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


def proxy_pool_day() -> str:
    return datetime.now(BEIJING_TZ).date().isoformat()


def normalize_proxy_endpoint(value: Any) -> str:
    host, separator, raw_port = str(value or "").strip().partition(":")
    if not separator or not host or not raw_port.isdigit():
        raise ValueError("proxy endpoint must be IPv4:port")
    address = ipaddress.ip_address(host)
    port = int(raw_port)
    if address.version != 4 or not address.is_global or not 1 <= port <= 65535:
        raise ValueError("proxy endpoint is not a public IPv4 address")
    return f"{address.compressed}:{port}"


@dataclass(frozen=True)
class ProxyEndpoint:
    endpoint: str
    protocol: str

    @property
    def proxy_url(self) -> str:
        # SCDN's HTTPS label describes CONNECT support for an HTTPS target.
        # It is not a TLS-wrapped proxy transport.
        scheme = "socks5h" if self.protocol == "socks5" else "http"
        return f"{scheme}://{self.endpoint}"


def remaining_cycle_delay(interval: float, elapsed: float) -> float:
    return max(0.0, interval - elapsed)


def product_refresh_interval(product: dict[str, Any], timestamp: int | None = None) -> int:
    """Return the conservative next-refresh interval for a product snapshot."""
    timestamp = timestamp if timestamp is not None else now_ts()
    price = float(product.get("price") or 0)
    stock = safe_int(product.get("stock_count"), -1)
    if price <= 0 or stock < 0:
        return UNKNOWN_OR_ZERO_REFRESH_INTERVAL
    if stock == 0:
        out_since = safe_int(product.get("out_of_stock_since"), 0)
        age = max(0, timestamp - out_since) if out_since else 0
        for age_limit, interval in OUT_OF_STOCK_REFRESH_INTERVALS:
            if age < age_limit:
                return interval
    if stock <= 2:
        return LOW_STOCK_REFRESH_INTERVAL
    if stock <= 9:
        return NORMAL_STOCK_REFRESH_INTERVAL
    return HIGH_STOCK_REFRESH_INTERVAL


def clean_text(value: Any, limit: int = 240) -> str:
    text = html.unescape(TAG_RE.sub(" ", str(value or "")))
    text = SPACE_RE.sub(" ", text).strip()
    return text[:limit]


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_price_filter(value: str, *, name: str, default: float | None = None) -> float | None:
    """Parse a non-negative, finite URL price filter without silently changing it."""
    text = (value or "").strip()
    if not text:
        return default
    try:
        price = float(text)
    except ValueError as exc:
        raise ValueError(f"{name}必须是非负数字") from exc
    if not math.isfinite(price) or price < 0:
        raise ValueError(f"{name}必须是非负数字")
    return price


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
    # Keep category_name for compatibility, but only the visible title is classified.
    _ = category_name
    title = str(name or "")
    while True:
        without_parentheses = PARENTHETICAL_RE.sub(" ", title)
        if without_parentheses == title:
            break
        title = without_parentheses
    title = f" {SPACE_RE.sub(' ', title).strip()} ".casefold()

    def contains_any(terms: tuple[str, ...] | list[str]) -> bool:
        return any(term.casefold() in title for term in terms)

    def category_matches(category: dict[str, Any]) -> bool:
        key = str(category["key"])
        terms = tuple(category["terms"]) + CATEGORY_EXTRA_TERMS.get(key, ())
        return contains_any(terms) and not contains_any(CATEGORY_EXCLUDE_TERMS.get(key, ()))

    matched = {
        category["key"]: category_matches(category)
        for category in CATEGORY_DEFINITIONS
    }
    tier = next((key for key in ACCOUNT_TIER_PRIORITY if matched[key]), "")
    sms_status = ""
    if any(term.casefold() in title for term in SMS_UNVERIFIED_TERMS):
        sms_status = "unverified"
    elif any(term.casefold() in title for term in SMS_VERIFIED_TERMS):
        sms_status = "verified"
    matched["sms"] = (
        matched["sms"] or ("\u63a5\u7801" in title and not sms_status) or "\u6c38\u4e45\u624b\u673a\u53f7" in title
    ) and not contains_any(CATEGORY_EXCLUDE_TERMS.get("sms", ()))
    matched["pro"] = (
        matched["pro"] or bool(re.search(r"(?<![a-z])pro(?=\d|[^a-z]|$)", title))
    ) and not contains_any(CATEGORY_EXCLUDE_TERMS.get("pro", ()))

    account_signals = (
        "成品号",
        "成品账号",
        "成品帐号",
        "账号",
        "帐号",
        "普通号",
        "free号",
        " json ",
        "反代",
        " rt ",
    )
    looks_like_gpt_account = any(brand in title for brand in ("chatgpt", "gpt", "openai")) and any(
        signal in title for signal in account_signals
    )
    if not tier and looks_like_gpt_account and not matched["pro"]:
        tier = "free"

    tags: list[str] = []
    for category in CATEGORY_DEFINITIONS:
        key = category["key"]
        if key in SMS_STATUS_KEYS:
            continue
        if key in ACCOUNT_TIER_KEYS:
            if key == tier:
                tags.append(key)
        elif matched[key]:
            tags.append(key)

    if sms_status:
        prefix = "plus" if tier == "plus" else "free"
        suffix = "sms" if sms_status == "verified" else "no_sms"
        tags.append(f"{prefix}_{suffix}")
    return tags


AI_TAG_KEYS = tuple(item["key"] for item in CATEGORY_DEFINITIONS)
AI_TAG_KEY_SET = frozenset(AI_TAG_KEYS)


def normalize_ai_tags(raw_tags: Any) -> list[str]:
    """Keep model output inside the dashboard's mutually exclusive account taxonomy."""
    if not isinstance(raw_tags, list):
        return []
    selected = {
        str(tag).strip().casefold()
        for tag in raw_tags
        if str(tag).strip().casefold() in AI_TAG_KEY_SET
    }
    if "plus_sms" in selected or "plus_no_sms" in selected:
        selected.add("plus")
    if "free_sms" in selected or "free_no_sms" in selected:
        selected.add("free")
    tier = next((key for key in ACCOUNT_TIER_PRIORITY if key in selected), "")
    normalized: list[str] = []
    for key in AI_TAG_KEYS:
        if key in ACCOUNT_TIER_KEYS:
            if key == tier:
                normalized.append(key)
            continue
        if key in SMS_STATUS_KEYS:
            prefix = "plus" if tier == "plus" else "free"
            if key.startswith(prefix) and key in selected:
                normalized.append(key)
            continue
        if key in selected:
            normalized.append(key)
    return normalized


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
                    source_kind TEXT NOT NULL DEFAULT 'shop_api',
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
                    out_of_stock_since INTEGER NOT NULL DEFAULT 0,
                    ai_classification_state TEXT NOT NULL DEFAULT 'pending',
                    ai_classified_at INTEGER NOT NULL DEFAULT 0,
                    ai_classification_error TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS catalog_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    revision INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS proxy_daily_pool (
                    pool_day TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    first_success_at INTEGER NOT NULL DEFAULT 0,
                    last_success_at INTEGER NOT NULL DEFAULT 0,
                    last_failure_at INTEGER NOT NULL DEFAULT 0,
                    last_used_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (pool_day, endpoint)
                );

                CREATE TABLE IF NOT EXISTS scan_checkpoints (
                    source_token TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT 'pages',
                    goods_type TEXT NOT NULL DEFAULT '',
                    page INTEGER NOT NULL DEFAULT 1,
                    source_name TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(source_token) REFERENCES sources(token) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS scan_seen (
                    source_token TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    goods_key TEXT NOT NULL,
                    PRIMARY KEY (source_token, cycle_id, goods_key),
                    FOREIGN KEY(source_token) REFERENCES sources(token) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_products_active ON products(active, last_seen DESC);
                CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_token, active);
                CREATE INDEX IF NOT EXISTS idx_products_active_price
                    ON products(active, in_stock, price, goods_key);
                CREATE INDEX IF NOT EXISTS idx_products_active_changed
                    ON products(active, changed_at DESC, price, goods_key);
                CREATE INDEX IF NOT EXISTS idx_products_source_refresh
                    ON products(source_token, active, last_seen);
                CREATE INDEX IF NOT EXISTS idx_history_goods ON price_history(goods_key, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_proxy_daily_pool_success
                    ON proxy_daily_pool(pool_day, success_count, first_success_at);
                CREATE INDEX IF NOT EXISTS idx_scan_seen_source
                    ON scan_seen(source_token, cycle_id);
                """
            )
            source_columns = {row["name"] for row in db.execute("PRAGMA table_info(sources)")}
            if "origin" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")
            if "source_kind" not in source_columns:
                db.execute(
                    "ALTER TABLE sources ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'shop_api'"
                )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sources_kind_enabled "
                "ON sources(source_kind, enabled, last_scan)"
            )
            if "remote_token" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN remote_token TEXT NOT NULL DEFAULT ''")
            if "base_url" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN base_url TEXT NOT NULL DEFAULT ''")
            if "entry_goods_key" not in source_columns:
                db.execute("ALTER TABLE sources ADD COLUMN entry_goods_key TEXT NOT NULL DEFAULT ''")
            product_columns = {row["name"] for row in db.execute("PRAGMA table_info(products)")}
            if "out_of_stock_since" not in product_columns:
                db.execute(
                    "ALTER TABLE products ADD COLUMN out_of_stock_since INTEGER NOT NULL DEFAULT 0"
                )
            if "ai_classification_state" not in product_columns:
                db.execute(
                    "ALTER TABLE products ADD COLUMN ai_classification_state "
                    "TEXT NOT NULL DEFAULT 'pending'"
                )
            if "ai_classified_at" not in product_columns:
                db.execute(
                    "ALTER TABLE products ADD COLUMN ai_classified_at INTEGER NOT NULL DEFAULT 0"
                )
            if "ai_classification_error" not in product_columns:
                db.execute(
                    "ALTER TABLE products ADD COLUMN ai_classification_error "
                    "TEXT NOT NULL DEFAULT ''"
                )
            db.execute(
                """
                UPDATE products SET out_of_stock_since = last_seen
                WHERE stock_count = 0 AND out_of_stock_since = 0
                """
            )
            db.execute(
                "UPDATE sources SET remote_token = token WHERE remote_token = ''"
            )
            db.execute(
                "UPDATE sources SET base_url = ? WHERE base_url = ''", (LDXP_BASE_URL,)
            )
            db.execute("INSERT OR IGNORE INTO catalog_meta (id, revision) VALUES (1, 0)")

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

    @staticmethod
    def _bump_catalog_revision(db: sqlite3.Connection) -> int:
        db.execute("UPDATE catalog_meta SET revision = revision + 1 WHERE id = 1")
        row = db.execute("SELECT revision FROM catalog_meta WHERE id = 1").fetchone()
        return int(row["revision"])

    def catalog_revision(self) -> int:
        with self.session() as db:
            row = db.execute("SELECT revision FROM catalog_meta WHERE id = 1").fetchone()
            return int(row["revision"]) if row is not None else 0

    def record_proxy_result(self, endpoint: str, protocol: str, success: bool) -> None:
        endpoint = normalize_proxy_endpoint(endpoint)
        protocol = protocol.strip().lower()
        if protocol not in {"http", "https", "socks5"}:
            raise ValueError("unsupported proxy protocol")
        timestamp = now_ts()
        successes = int(success)
        failures = int(not success)
        with self.session() as db:
            db.execute(
                """
                INSERT INTO proxy_daily_pool (
                    pool_day, endpoint, protocol, success_count, failure_count,
                    first_success_at, last_success_at, last_failure_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pool_day, endpoint) DO UPDATE SET
                    protocol = excluded.protocol,
                    success_count = proxy_daily_pool.success_count + excluded.success_count,
                    failure_count = proxy_daily_pool.failure_count + excluded.failure_count,
                    first_success_at = CASE
                        WHEN excluded.success_count = 1 AND proxy_daily_pool.first_success_at = 0
                        THEN excluded.first_success_at
                        ELSE proxy_daily_pool.first_success_at
                    END,
                    last_success_at = CASE
                        WHEN excluded.success_count = 1 THEN excluded.last_success_at
                        ELSE proxy_daily_pool.last_success_at
                    END,
                    last_failure_at = CASE
                        WHEN excluded.failure_count = 1 THEN excluded.last_failure_at
                        ELSE proxy_daily_pool.last_failure_at
                    END,
                    last_used_at = excluded.last_used_at
                """,
                (
                    proxy_pool_day(),
                    endpoint,
                    protocol,
                    successes,
                    failures,
                    timestamp if success else 0,
                    timestamp if success else 0,
                    timestamp if not success else 0,
                    timestamp,
                ),
            )

    def daily_proxy_count(self) -> int:
        with self.session() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS total FROM proxy_daily_pool
                WHERE pool_day = ? AND success_count > 0
                """,
                (proxy_pool_day(),),
            ).fetchone()
            return int(row["total"])

    def next_daily_proxy(self, excluded: set[str] | None = None) -> ProxyEndpoint | None:
        excluded = excluded or set()
        day = proxy_pool_day()
        cursor_key = f"scdn_proxy_cursor:{day}"
        with self.session() as db:
            rows = db.execute(
                """
                SELECT endpoint, protocol FROM proxy_daily_pool
                WHERE pool_day = ? AND success_count > 0
                ORDER BY last_used_at ASC, endpoint ASC
                """,
                (day,),
            ).fetchall()
            if not rows:
                return None
            state = db.execute(
                "SELECT value FROM settings WHERE key = ?", (cursor_key,)
            ).fetchone()
            cursor = safe_int(state["value"] if state is not None else 0) % len(rows)
            selected_index: int | None = None
            for offset in range(len(rows)):
                index = (cursor + offset) % len(rows)
                if str(rows[index]["endpoint"]) not in excluded:
                    selected_index = index
                    break
            if selected_index is None:
                return None
            selected = rows[selected_index]
            timestamp = now_ts()
            db.execute(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (cursor_key, str((selected_index + 1) % len(rows)), timestamp),
            )
            db.execute(
                """
                UPDATE proxy_daily_pool SET last_used_at = ?
                WHERE pool_day = ? AND endpoint = ?
                """,
                (timestamp, day, selected["endpoint"]),
            )
            return ProxyEndpoint(str(selected["endpoint"]), str(selected["protocol"]))

    def known_daily_proxy_endpoints(self) -> set[str]:
        with self.session() as db:
            return {
                str(row["endpoint"])
                for row in db.execute(
                    "SELECT endpoint FROM proxy_daily_pool WHERE pool_day = ?", (proxy_pool_day(),)
                )
            }

    def proxy_pool_summary(self) -> dict[str, int | str]:
        with self.session() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS discovered,
                       COALESCE(SUM(CASE WHEN success_count > 0 THEN 1 ELSE 0 END), 0) AS usable,
                       COALESCE(SUM(success_count), 0) AS successes,
                       COALESCE(SUM(failure_count), 0) AS failures
                FROM proxy_daily_pool WHERE pool_day = ?
                """,
                (proxy_pool_day(),),
            ).fetchone()
            return {"day": proxy_pool_day(), **dict(row)}

    def scan_checkpoint_summary(self) -> dict[str, int]:
        with self.session() as db:
            row = db.execute(
                "SELECT COUNT(*) AS pending FROM scan_checkpoints"
            ).fetchone()
            return {"pending": int(row["pending"])}

    def get_or_create_scan_checkpoint(self, source_token: str) -> dict[str, Any]:
        with self.session() as db:
            row = db.execute(
                "SELECT * FROM scan_checkpoints WHERE source_token = ?", (source_token,)
            ).fetchone()
            if row is None:
                timestamp = now_ts()
                cycle_id = uuid.uuid4().hex
                db.execute(
                    """
                    INSERT INTO scan_checkpoints
                        (source_token, cycle_id, phase, goods_type, page, source_name, updated_at)
                    VALUES (?, ?, 'pages', '', 1, '', ?)
                    """,
                    (source_token, cycle_id, timestamp),
                )
                row = db.execute(
                    "SELECT * FROM scan_checkpoints WHERE source_token = ?", (source_token,)
                ).fetchone()
            return dict(row)

    def update_scan_checkpoint(
        self,
        source_token: str,
        cycle_id: str,
        *,
        phase: str,
        goods_type: str = "",
        page: int = 1,
        source_name: str | None = None,
    ) -> None:
        if phase not in {"pages", "entry"} or page < 1:
            raise ValueError("invalid scan checkpoint")
        fields = ["phase = ?", "goods_type = ?", "page = ?", "updated_at = ?"]
        values: list[Any] = [phase, goods_type, page, now_ts()]
        if source_name is not None:
            fields.append("source_name = ?")
            values.append(source_name[:200])
        values.extend([source_token, cycle_id])
        with self.session() as db:
            result = db.execute(
                f"UPDATE scan_checkpoints SET {', '.join(fields)} "
                "WHERE source_token = ? AND cycle_id = ?",
                values,
            )
            if result.rowcount != 1:
                raise RuntimeError("scan checkpoint was replaced")

    def mark_scan_seen(self, source_token: str, cycle_id: str, goods_key: str) -> None:
        with self.session() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO scan_seen (source_token, cycle_id, goods_key)
                VALUES (?, ?, ?)
                """,
                (source_token, cycle_id, goods_key),
            )

    def scan_seen_contains(self, source_token: str, cycle_id: str, goods_key: str) -> bool:
        with self.session() as db:
            return (
                db.execute(
                    """
                    SELECT 1 FROM scan_seen
                    WHERE source_token = ? AND cycle_id = ? AND goods_key = ?
                    """,
                    (source_token, cycle_id, goods_key),
                ).fetchone()
                is not None
            )

    def scan_seen_count(self, source_token: str, cycle_id: str) -> int:
        with self.session() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS total FROM scan_seen
                WHERE source_token = ? AND cycle_id = ?
                """,
                (source_token, cycle_id),
            ).fetchone()
            return int(row["total"])

    def complete_scan_checkpoint(self, source_token: str, cycle_id: str) -> set[str]:
        timestamp = now_ts()
        with self.session() as db:
            checkpoint = db.execute(
                """
                SELECT 1 FROM scan_checkpoints
                WHERE source_token = ? AND cycle_id = ?
                """,
                (source_token, cycle_id),
            ).fetchone()
            if checkpoint is None:
                raise RuntimeError("scan checkpoint was replaced")
            rows = db.execute(
                """
                SELECT goods_key FROM products AS product
                WHERE source_token = ? AND active = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM scan_seen AS seen
                      WHERE seen.source_token = ?
                        AND seen.cycle_id = ?
                        AND seen.goods_key = product.goods_key
                  )
                """,
                (source_token, source_token, cycle_id),
            ).fetchall()
            missing = {str(row["goods_key"]) for row in rows}
            if missing:
                db.executemany(
                    "UPDATE products SET active = 0, changed_at = ? WHERE goods_key = ?",
                    [(timestamp, goods_key) for goods_key in missing],
                )
                self._bump_catalog_revision(db)
            db.execute(
                "DELETE FROM scan_seen WHERE source_token = ? AND cycle_id = ?",
                (source_token, cycle_id),
            )
            db.execute(
                "DELETE FROM scan_checkpoints WHERE source_token = ? AND cycle_id = ?",
                (source_token, cycle_id),
            )
            return missing

    def list_sources(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sources"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at ASC"
        with self.session() as db:
            return [dict(row) for row in db.execute(sql)]

    def list_sources_due_for_scan(self, *, scheduled: bool) -> list[dict[str, Any]]:
        """Order sources by the earliest product refresh deadline they contain."""
        if not scheduled:
            with self.session() as db:
                return [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM sources "
                        "WHERE enabled = 1 AND source_kind = 'shop_api' ORDER BY created_at ASC"
                    )
                ]
        timestamp = now_ts()
        with self.session() as db:
            rows = db.execute(
                """
                SELECT source_token, price, stock_count, last_seen, out_of_stock_since
                FROM products WHERE active = 1
                """
            ).fetchall()
            next_refresh_by_source: dict[str, int] = {}
            for row in rows:
                product = dict(row)
                due_at = int(product["last_seen"]) + product_refresh_interval(product, timestamp)
                token = str(product["source_token"])
                previous = next_refresh_by_source.get(token)
                if previous is None or due_at < previous:
                    next_refresh_by_source[token] = due_at

            sources = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM sources WHERE enabled = 1 AND source_kind = 'shop_api'"
                )
            ]
            for source in sources:
                source["next_refresh_at"] = next_refresh_by_source.get(str(source["token"]), 0)
            sources.sort(
                key=lambda source: (
                    int(source["next_refresh_at"]) > timestamp,
                    int(source["next_refresh_at"]),
                    int(source["last_scan"]),
                )
            )
            return [
                source
                for source in sources
                if int(source["next_refresh_at"]) <= timestamp
            ]

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
        source_kind: str = "shop_api",
        source_url: str = "",
    ) -> dict[str, Any]:
        remote_token = remote_token or token
        base_url = base_url.rstrip("/")
        entry_goods_key = entry_goods_key.strip()
        if source_kind not in {"shop_api", "snapshot"}:
            raise ValueError("invalid source kind")
        source_url = source_url.strip() or f"{base_url}/shop/{remote_token}"
        timestamp = now_ts()
        with self.session() as db:
            db.execute(
                """
                INSERT INTO sources (
                    token, remote_token, base_url, entry_goods_key, name, url, enabled,
                    status, origin, source_kind, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
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
                    source_kind = excluded.source_kind,
                    updated_at = excluded.updated_at
                """,
                (
                    token,
                    remote_token,
                    base_url,
                    entry_goods_key,
                    name,
                    source_url,
                    int(enabled),
                    origin[:200],
                    source_kind,
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
                deactivated = db.execute(
                    "UPDATE products SET active = 0 WHERE source_token = ? AND active = 1", (token,)
                )
                if deactivated.rowcount:
                    self._bump_catalog_revision(db)
            return result.rowcount > 0

    def delete_source(self, token: str) -> bool:
        with self.session() as db:
            result = db.execute("DELETE FROM sources WHERE token = ?", (token,))
            if result.rowcount:
                self._bump_catalog_revision(db)
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
                """
                SELECT name, price, stock_count, tags, active, out_of_stock_since
                FROM products WHERE goods_key = ?
                """,
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
            if int(product["stock_count"]) == 0:
                out_of_stock_since = (
                    int(previous["out_of_stock_since"] or timestamp)
                    if previous is not None and int(previous["stock_count"]) == 0
                    else timestamp
                )
            else:
                out_of_stock_since = 0
            db.execute(
                """
                INSERT INTO products (
                    goods_key, source_token, source_name, name, price, market_price,
                    stock_count, in_stock, tags, category_name, goods_type, link, image,
                    description_excerpt, create_time, first_seen, last_seen, changed_at,
                    out_of_stock_since, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
                    out_of_stock_since = excluded.out_of_stock_since,
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
                    out_of_stock_since,
                    changed_at,
                    changed_at,
                ),
            )
            if change != "unchanged":
                self._bump_catalog_revision(db)
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

    def reclassify_products(self) -> dict[str, int]:
        updated = 0
        deactivated = 0
        with self.session() as db:
            rows = db.execute(
                """
                SELECT goods_key, name, tags
                FROM products
                WHERE active = 1
                """
            ).fetchall()
            for row in rows:
                tags = classify_product(str(row["name"] or ""))
                tags_json = json.dumps(tags, ensure_ascii=False, separators=(",", ":"))
                if not tags:
                    db.execute(
                        """
                        UPDATE products
                        SET active = 0, changed_at = ?, ai_classification_state = 'disabled',
                            ai_classified_at = 0, ai_classification_error = ''
                        WHERE goods_key = ?
                        """,
                        (now_ts(), row["goods_key"]),
                    )
                    deactivated += 1
                else:
                    db.execute(
                        """
                        UPDATE products
                        SET tags = ?, ai_classification_state = 'disabled', ai_classified_at = 0,
                            ai_classification_error = ''
                        WHERE goods_key = ?
                        """,
                        (tags_json, row["goods_key"]),
                    )
                    if row["tags"] != tags_json:
                        updated += 1
            if updated or deactivated:
                self._bump_catalog_revision(db)
        return {"updated": updated, "deactivated": deactivated}

    def reset_ai_classification(self) -> int:
        """Make every active product eligible for one explicit full AI classification pass."""
        with self.session() as db:
            result = db.execute(
                """
                UPDATE products
                SET ai_classification_state = 'pending', ai_classified_at = 0,
                    ai_classification_error = ''
                WHERE active = 1
                """
            )
            return result.rowcount

    def pending_ai_classification_products(self, limit: int) -> list[dict[str, Any]]:
        limit = max(1, min(100, limit))
        with self.session() as db:
            rows = db.execute(
                """
                SELECT * FROM products
                WHERE active = 1 AND ai_classification_state = 'pending'
                ORDER BY first_seen ASC, goods_key ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._product_row(row) for row in rows]

    def pending_ai_classification_count(self) -> int:
        with self.session() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS total FROM products
                WHERE active = 1 AND ai_classification_state = 'pending'
                """
            ).fetchone()
            return int(row["total"])

    def save_ai_classifications(self, classifications: dict[str, list[str]]) -> int:
        timestamp = now_ts()
        updated_tags = 0
        with self.session() as db:
            for goods_key, tags in classifications.items():
                tags_json = json.dumps(tags, ensure_ascii=False, separators=(",", ":"))
                previous = db.execute(
                    "SELECT tags FROM products WHERE goods_key = ? AND active = 1", (goods_key,)
                ).fetchone()
                if previous is None:
                    continue
                if str(previous["tags"]) != tags_json:
                    updated_tags += 1
                db.execute(
                    """
                    UPDATE products
                    SET tags = ?, ai_classification_state = 'done', ai_classified_at = ?,
                        ai_classification_error = ''
                    WHERE goods_key = ? AND active = 1
                    """,
                    (tags_json, timestamp, goods_key),
                )
            if updated_tags:
                self._bump_catalog_revision(db)
        return updated_tags

    def mark_ai_classification_failed(self, goods_keys: list[str], error: str) -> int:
        if not goods_keys:
            return 0
        with self.session() as db:
            db.executemany(
                """
                UPDATE products
                SET ai_classification_state = 'error', ai_classification_error = ?
                WHERE goods_key = ? AND active = 1
                """,
                [(error[:500], goods_key) for goods_key in goods_keys],
            )
        return len(goods_keys)

    def update_product_description_excerpt(self, goods_key: str, description: str) -> None:
        description = clean_text(description, 1000)
        if not description:
            return
        with self.session() as db:
            db.execute(
                "UPDATE products SET description_excerpt = ? WHERE goods_key = ?",
                (description, goods_key),
            )

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
                self._bump_catalog_revision(db)
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

    def list_product_page(
        self,
        *,
        category: str = "all",
        stock_only: bool = True,
        search: str = "",
        sort: str = "price",
        min_price: float = 0,
        max_price: float | None = None,
        include_left: bool = False,
        offset: int = 0,
        limit: int = PRODUCT_STREAM_DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        conditions = ["active = 1"]
        params: list[Any] = []
        if category != "all":
            conditions.append("tags LIKE ?")
            params.append(f'%"{category}"%')
        if stock_only:
            conditions.append("in_stock = 1")
        conditions.append("price >= ?" if include_left else "price > ?")
        params.append(min_price)
        if max_price is not None:
            conditions.append("price <= ?")
            params.append(max_price)
        query = search.strip().lower()
        if query:
            conditions.append(
                "LOWER(name || ' ' || source_name || ' ' || category_name || ' ' || link || ' ' || goods_key) LIKE ?"
            )
            params.append(f"%{query}%")

        order_by = {
            "price": "price ASC, name COLLATE NOCASE ASC, goods_key ASC",
            "stock": "stock_count DESC, price ASC, name COLLATE NOCASE ASC, goods_key ASC",
            "updated": "changed_at DESC, price ASC, goods_key ASC",
        }[sort]
        where = " AND ".join(conditions)
        with self.session() as db:
            total = int(
                db.execute(f"SELECT COUNT(*) AS total FROM products WHERE {where}", params).fetchone()[
                    "total"
                ]
            )
            rows = db.execute(
                f"""
                SELECT * FROM products
                WHERE {where}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
            revision = db.execute("SELECT revision FROM catalog_meta WHERE id = 1").fetchone()
            return {
                "total": total,
                "products": [self._product_row(row) for row in rows],
                "catalog_revision": int(revision["revision"]) if revision is not None else 0,
            }

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
            if result.rowcount:
                self._bump_catalog_revision(db)
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
            if removed:
                self._bump_catalog_revision(db)
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
        category_columns = ",\n                       ".join(
            f"COALESCE(SUM(CASE WHEN tags LIKE '%\"{item['key']}\"%' THEN 1 ELSE 0 END), 0) AS category_{index}"
            for index, item in enumerate(CATEGORY_DEFINITIONS)
        )
        with self.session() as db:
            product = db.execute(
                f"""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END), 0) AS in_stock,
                       COALESCE(MIN(CASE WHEN price > 0 THEN price END), 0) AS lowest_price,
                       COALESCE(MAX(last_seen), 0) AS last_scan,
                       {category_columns}
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
                "category_counts": {
                    item["key"]: product[f"category_{index}"]
                    for index, item in enumerate(CATEGORY_DEFINITIONS)
                },
            }


class LDXPError(RuntimeError):
    pass


class LDXPTransportError(LDXPError):
    pass


class SCDNProxySource:
    def __init__(
        self,
        page_url: str = LDXP_SCDN_PROXY_PAGE_URL,
        protocol: str = LDXP_SCDN_PROXY_PROTOCOL,
        timeout: int = LDXP_REQUEST_TIMEOUT,
        page_size: int = LDXP_SCDN_PROXY_PAGE_SIZE,
    ):
        self.page_url = page_url
        self.protocol = protocol.lower()
        self.timeout = max(1, timeout)
        self.page_size = max(10, min(100, page_size))
        if self.protocol not in {"http", "https", "socks5"}:
            raise ValueError("LDXP_SCDN_PROXY_PROTOCOL must be http, https, or socks5")

    def fetch_page(self, page: int) -> tuple[list[ProxyEndpoint], int]:
        page = max(1, page)
        query = urllib.parse.urlencode(
            {"page": page, "protocol": self.protocol.upper(), "per_page": self.page_size}
        )
        separator = "&" if "?" in self.page_url else "?"
        request = urllib.request.Request(
            f"{self.page_url}{separator}{query}",
            headers={"Accept": "application/json", "User-Agent": "LDXPPriceScanner/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LDXPError(f"SCDN proxy fetch failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise LDXPError("SCDN proxy page returned an invalid response")
        table_html = str(payload.get("table_html") or "")
        total_pages = max(1, safe_int(payload.get("totalPages"), 1))
        endpoints = re.findall(r"data-proxy=[\"']([^\"']+)[\"']", table_html)
        candidates: list[ProxyEndpoint] = []
        seen: set[str] = set()
        for value in endpoints:
            try:
                endpoint = normalize_proxy_endpoint(html.unescape(value))
            except (TypeError, ValueError):
                continue
            if endpoint in seen:
                continue
            seen.add(endpoint)
            candidates.append(ProxyEndpoint(endpoint, self.protocol))
        if not candidates:
            raise LDXPError("SCDN proxy page returned no valid candidates")
        return candidates, total_pages


class LDXPClient:
    def __init__(
        self,
        base_url: str = LDXP_BASE_URL,
        timeout: int = LDXP_REQUEST_TIMEOUT,
        proxy_url: str = LDXP_FAILOVER_PROXY_URL,
        direct_attempts: int = LDXP_DIRECT_ATTEMPTS,
        proxy_attempts: int = LDXP_PROXY_ATTEMPTS,
        retry_delay: float = LDXP_RETRY_DELAY,
        proxy_observer: Callable[[bool], None] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = max(1, timeout)
        self.proxy_url = proxy_url.strip()
        self.direct_attempts = max(0, direct_attempts)
        self.proxy_attempts = max(0, proxy_attempts)
        self.retry_delay = max(0.0, retry_delay)
        self.proxy_observer = proxy_observer
        self.visitor_id = f"ldxp-scanner-{uuid.uuid4().hex[:12]}"

        cookie_jar = http.cookiejar.CookieJar()
        self.direct_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(cookie_jar),
        )
        if self.proxy_url and self.proxy_attempts:
            parsed_proxy = urllib.parse.urlsplit(self.proxy_url)
            if parsed_proxy.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed_proxy.netloc:
                raise ValueError("LDXP proxy URL must be an HTTP(S) or SOCKS5 proxy URL")
        if not self.direct_attempts and not (self.proxy_url and self.proxy_attempts):
            raise ValueError("LDXP client needs a direct or proxy route")

    def _report_proxy_result(self, success: bool) -> None:
        if self.proxy_observer is None:
            return
        try:
            self.proxy_observer(success)
        except Exception as exc:
            print(f"LDXP proxy observer failed: {exc}", flush=True)

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
        ]
        if urllib.parse.urlsplit(self.proxy_url).scheme == "https":
            # This bypasses only the proxy's TLS certificate. curl still verifies
            # the destination site's HTTPS certificate after the CONNECT tunnel.
            command.append("--proxy-insecure")
        command.extend(
            [
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
        )
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
                    if route == "proxy":
                        self._report_proxy_result(False)
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
                    if route == "proxy":
                        self._report_proxy_result(False)
                    raise LDXPError("LDXP returned an invalid response object")
                if payload.get("code") != 1:
                    if route == "proxy":
                        self._report_proxy_result(False)
                    raise LDXPError(payload.get("msg") or "LDXP returned an unknown error")
                if route == "proxy":
                    self._report_proxy_result(True)
                return payload.get("data")

        detail = str(last_error) if last_error is not None else "unknown transport error"
        raise LDXPTransportError(
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
    tags = classify_product(name)
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


def timestamp_from_iso(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def product_from_priceai_offer(
    offer: dict[str, Any], catalog_product: dict[str, Any]
) -> dict[str, Any] | None:
    offer_id = clean_text(offer.get("id"), 160)
    if not offer_id:
        return None
    title = clean_text(offer.get("title"), 500)
    product_name = clean_text(catalog_product.get("name") or catalog_product.get("slug"), 240)
    name = title or product_name or offer_id
    source_name = clean_text(
        offer.get("source_store_name") or offer.get("source_name") or "PriceAI 公开来源", 200
    )
    status = str(offer.get("effective_status") or offer.get("status") or "").lower()
    raw_stock = offer.get("stock_count")
    stock_count = safe_int(raw_stock, -1) if raw_stock is not None else -1
    if status in {"out_of_stock", "unavailable", "expired"}:
        stock_count = 0
    tags = classify_product(f"{product_name} {name}")
    return {
        "goods_key": f"priceai:{offer_id}",
        "source_token": PRICEAI_SOURCE_TOKEN,
        "source_name": source_name,
        "name": name,
        "price": safe_float(offer.get("price")),
        "market_price": 0.0,
        "stock_count": stock_count,
        "in_stock": stock_count != 0
        and status not in {"out_of_stock", "unavailable", "expired"},
        "tags": tags,
        "category_name": product_name,
        "goods_type": "priceai_snapshot",
        "link": clean_text(offer.get("url"), 2000),
        "image": "",
        "description_excerpt": clean_text(catalog_product.get("summary"), 1000),
        "create_time": timestamp_from_iso(
            offer.get("captured_at") or offer.get("last_seen_at")
        ),
    }


@dataclass
class ScanResult:
    source_count: int = 0
    succeeded: int = 0
    failed: int = 0
    paused: int = 0
    proxy_rounds: int = 0
    matched: int = 0
    changed: int = 0


class ProductRefreshBusy(RuntimeError):
    pass


class ProductRefreshInProgress(RuntimeError):
    pass


class LocalScanBusy(RuntimeError):
    pass


class PriceAISyncBusy(RuntimeError):
    pass


class AIClassificationError(RuntimeError):
    pass


class AIProductClassifier:
    """Small OpenAI-compatible client kept behind explicit server-side configuration."""

    SYSTEM_PROMPT = """You classify products for a Chinese price dashboard.
Return only one JSON object: {\"items\":[{\"id\":\"...\",\"tags\":[...],\"needs_description\":true|false}]}.
Allowed tags only: plus, plus_sms, plus_no_sms, free, free_sms, free_no_sms, team,
bugteam, pro, k12, cursor, codex, claude, kiro, gemini, mail, sms.
Use account tier tags only when the product itself is that tier. Add *_sms or *_no_sms only
when the title or description explicitly states its phone/SMS status. Use sms only for an
SMS receiving/verification service, not an account that merely has phone verification.
When the product name alone is ambiguous, return needs_description=true and no guessed tags.
When a description is provided, classify from its concrete offer details. Do not invent tags."""

    def __init__(
        self,
        api_url: str = LDXP_AI_CLASSIFIER_API_URL,
        api_key: str = LDXP_AI_CLASSIFIER_API_KEY,
        model: str = LDXP_AI_CLASSIFIER_MODEL,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        if not self.api_url or not self.api_key or not self.model:
            raise AIClassificationError("AI 分类器未配置 API 地址、密钥或模型")

    @staticmethod
    def _json_content(value: Any) -> dict[str, Any]:
        text = str(value or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIClassificationError("AI 分类响应不是 JSON") from exc
        if not isinstance(payload, dict):
            raise AIClassificationError("AI 分类响应格式不正确")
        return payload

    def classify(self, items: list[dict[str, Any]], *, with_descriptions: bool) -> dict[str, dict[str, Any]]:
        if not items:
            return {}
        request_items = []
        for item in items:
            request_item = {"id": str(item["goods_key"]), "name": clean_text(item.get("name"), 300)}
            if with_descriptions:
                request_item["description"] = clean_text(item.get("description_excerpt"), 1200)
            request_items.append(request_item)
        prompt = (
            "Classify these products. "
            + ("Descriptions are included; do not request them again." if with_descriptions else "Names only; flag ambiguous names for detail lookup.")
            + "\n"
            + json.dumps({"items": request_items}, ensure_ascii=False, separators=(",", ":"))
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.api_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AIClassificationError(f"AI 分类请求失败：{exc}") from exc
        choices = response_payload.get("choices") if isinstance(response_payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise AIClassificationError("AI 分类响应未包含 choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else ""
        result_items = self._json_content(content).get("items")
        if not isinstance(result_items, list):
            raise AIClassificationError("AI 分类响应未包含 items")
        requested_keys = {str(item["goods_key"]) for item in items}
        results: dict[str, dict[str, Any]] = {}
        for result in result_items:
            if not isinstance(result, dict):
                continue
            goods_key = str(result.get("id") or "")
            if goods_key not in requested_keys or goods_key in results:
                continue
            results[goods_key] = {
                "tags": normalize_ai_tags(result.get("tags")),
                "needs_description": bool(result.get("needs_description")),
            }
        if len(results) != len(requested_keys):
            raise AIClassificationError("AI 分类响应未覆盖全部商品")
        return results


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
        self.proxy_source_interval = LDXP_PROXY_SOURCE_INTERVAL
        self._scan_lock = threading.Lock()
        self._scan_state_lock = threading.RLock()
        self._local_ingest_lock = threading.Lock()
        self._local_ingest_idle = threading.Event()
        self._local_ingest_idle.set()
        self._priceai_sync_lock = threading.Lock()
        self._ai_classification_lock = threading.Lock()
        self._ai_status_lock = threading.RLock()
        self._scdn_proxy_page = 1
        self._source_locks_guard = threading.Lock()
        self._source_locks: dict[str, threading.Lock] = {}
        self._submitted_source_scan_lock = threading.Lock()
        self._submitted_source_scan_queue: queue.Queue[str] = queue.Queue()
        self._submitted_source_scan_tokens: set[str] = set()
        self._submitted_source_scan_worker: threading.Thread | None = None
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
        self._scan_reason = ""
        self._active_source_token = ""
        self._pending_scan_sources: set[str] = set()
        self.ai_classifying = False
        self.ai_classification_total = 0
        self.ai_classification_processed = 0
        self.ai_classification_updated = 0
        self.ai_classification_failed = 0
        self.ai_classification_error = ""
        self.ai_auto_classification_enabled = False

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
        # On service restart, resume only the sources whose product deadlines are due.
        delay = 0.0 if self.auto_scan_enabled else float(self.interval)
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

    def scan_task(self) -> dict[str, Any]:
        with self._scan_state_lock:
            return {
                "running": self.scanning,
                "reason": self._scan_reason,
                "started_at": self.last_started,
                "current_source": self._active_source_token,
                "pending_sources": len(self._pending_scan_sources),
            }

    def _begin_scan(self, reason: str) -> None:
        with self._scan_state_lock:
            self.scanning = True
            self._scan_reason = reason
            self._active_source_token = ""
            self._pending_scan_sources.clear()
            self.last_started = now_ts()
        self._publish_status("started", reason=reason)

    def _set_pending_scan_sources(self, sources: list[dict[str, Any]]) -> None:
        with self._scan_state_lock:
            self._pending_scan_sources = {str(source["token"]) for source in sources}

    def _mark_source_started(self, token: str) -> None:
        with self._scan_state_lock:
            self._active_source_token = token

    def _mark_source_idle(self, token: str, *, completed: bool = False) -> None:
        with self._scan_state_lock:
            if completed:
                self._pending_scan_sources.discard(token)
            if self._active_source_token == token:
                self._active_source_token = ""

    def is_server_refreshing_source(self, source_token: str) -> bool:
        with self._scan_state_lock:
            return self.scanning and source_token in self._pending_scan_sources

    def product_refresh_status(self, goods_key: str) -> dict[str, Any]:
        product = self.database.get_product(goods_key)
        if product is None:
            raise KeyError(goods_key)
        source_token = str(product["source_token"])
        return {
            "product": product,
            "goods_key": goods_key,
            "source_token": source_token,
            "refreshing": self.is_server_refreshing_source(source_token),
            "task": self.scan_task(),
        }

    def ai_classification_status(self) -> dict[str, Any]:
        with self._ai_status_lock:
            return {
                "running": self.ai_classifying,
                "total": self.ai_classification_total,
                "processed": self.ai_classification_processed,
                "updated": self.ai_classification_updated,
                "failed": self.ai_classification_failed,
                "error": self.ai_classification_error,
                "pending": self.database.pending_ai_classification_count(),
                "auto_enabled": self.ai_auto_classification_enabled,
            }

    def trigger(self, reason: str = "manual") -> bool:
        if self._local_ingest_lock.locked() or not self._scan_lock.acquire(blocking=False):
            return False
        self._begin_scan(reason)
        try:
            thread = threading.Thread(
                target=self._scan_all_reserved,
                args=(reason,),
                name="scanner-worker",
                daemon=True,
            )
            thread.start()
        except Exception:
            self._finish_scan()
            raise
        return True

    def request_scan(self, reason: str = "manual") -> dict[str, Any]:
        started = self.trigger(reason)
        task = self.scan_task()
        requested_kind = "proxy_only" if reason == "manual_proxy_only" else "full"
        active_kind = "proxy_only" if task["reason"] == "manual_proxy_only" else "full"
        joined = not started and task["running"] and active_kind == requested_kind
        return {
            "started": started,
            "joined": joined,
            "busy": not started and task["running"] and not joined,
            "task": task,
        }

    def request_submitted_source_scan(self, token: str) -> bool:
        """Queue a newly submitted public source for one server-side scan."""
        source = self.database.get_source(token)
        if source is None:
            raise KeyError(token)
        if not source.get("enabled") or source.get("source_kind") != "shop_api":
            return False

        start_worker = False
        with self._submitted_source_scan_lock:
            if token in self._submitted_source_scan_tokens:
                return False
            self._submitted_source_scan_tokens.add(token)
            self._submitted_source_scan_queue.put(token)
            if self._submitted_source_scan_worker is None or not self._submitted_source_scan_worker.is_alive():
                self._submitted_source_scan_worker = threading.Thread(
                    target=self._process_submitted_source_scans,
                    name="submitted-source-scanner",
                    daemon=True,
                )
                start_worker = True

        if start_worker:
            self._submitted_source_scan_worker.start()
        self.events.publish("source_submission", {"phase": "queued", "token": token})
        return True

    def _process_submitted_source_scans(self) -> None:
        while not self._stop.is_set():
            try:
                token = self._submitted_source_scan_queue.get_nowait()
            except queue.Empty:
                with self._submitted_source_scan_lock:
                    if self._submitted_source_scan_queue.empty():
                        self._submitted_source_scan_worker = None
                        return
                continue

            try:
                if not self._wait_for_local_ingest():
                    return
                source = self.database.get_source(token)
                if source is None or not source.get("enabled"):
                    continue
                self.database.update_source_scan(token, status="scanning")
                self.events.publish("source_submission", {"phase": "started", "token": token})
                self._publish_status(
                    "source_started",
                    token=token,
                    source_index=1,
                    source_total=1,
                    reason="user_submission",
                )
                try:
                    matched, changed = self._scan_source(token)
                except Exception as exc:
                    message = str(exc) or exc.__class__.__name__
                    self.database.update_source_scan(token, status="error", error=message, count=0, scanned=True)
                    self._publish_status("source_error", token=token, error=message)
                    self.events.publish(
                        "source_submission", {"phase": "error", "token": token, "error": message}
                    )
                else:
                    self.events.publish(
                        "source_submission",
                        {"phase": "completed", "token": token, "matched": matched, "changed": changed},
                    )
            finally:
                self._submitted_source_scan_queue.task_done()
                with self._submitted_source_scan_lock:
                    self._submitted_source_scan_tokens.discard(token)
                self._publish_snapshot()

    def _source_lock_for(self, token: str) -> threading.Lock:
        with self._source_locks_guard:
            return self._source_locks.setdefault(token, threading.Lock())

    def _wait_for_local_ingest(self) -> bool:
        """Keep background scans at source boundaries while users write refresh data."""
        waiting = False
        while self._local_ingest_lock.locked() and not self._stop.is_set():
            if not waiting:
                waiting = True
                self._publish_status("waiting_for_user")
            self._local_ingest_idle.wait(0.2)
            if self._local_ingest_lock.locked():
                self._stop.wait(0.05)
        return not self._stop.is_set()

    @staticmethod
    def _keep_refresh_metadata(product: dict[str, Any], existing: dict[str, Any]) -> None:
        """A targeted refresh updates observed values without rewriting catalog metadata."""
        for field in (
            "source_token",
            "source_name",
            "name",
            "market_price",
            "tags",
            "category_name",
            "goods_type",
            "link",
            "image",
            "description_excerpt",
            "create_time",
        ):
            product[field] = existing[field]

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
        source_token = str(existing["source_token"])
        if self.is_server_refreshing_source(source_token):
            raise ProductRefreshInProgress(goods_key)
        with self._product_refresh_lock:
            if goods_key in self._refreshing_products:
                raise ProductRefreshBusy(goods_key)
            self._refreshing_products.add(goods_key)
        try:
            with self._source_lock_for(source_token):
                if self.is_server_refreshing_source(source_token):
                    raise ProductRefreshInProgress(goods_key)
                source = self.database.get_source(source_token)
                if source is None:
                    raise KeyError(existing["source_token"])
                if source.get("source_kind") != "shop_api":
                    raise ValueError("该商品由 PriceAI 快照维护，请使用 PriceAI 同步")
                base_url = str(source.get("base_url") or LDXP_BASE_URL)
                remote_token = str(source.get("remote_token") or source["token"])
                item = self._load_single_product(
                    LDXPClient(base_url=base_url), existing, remote_token
                )
                product = product_from_api(
                    item,
                    source_token,
                    str(existing["source_name"] or source_token),
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
                self._keep_refresh_metadata(product, existing)
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
        if source.get("source_kind") != "shop_api":
            raise ValueError("该来源由 PriceAI 快照维护，不能进行本地店铺扫描")
        if not self._local_ingest_lock.acquire(blocking=False):
            raise LocalScanBusy(token)
        self._local_ingest_idle.clear()
        source_lock = self._source_lock_for(token)
        source_lock.acquire()

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
                self._queue_new_ai_classification(change)

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
            source_lock.release()
            self._local_ingest_lock.release()
            self._local_ingest_idle.set()

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
        if source.get("source_kind") != "shop_api":
            raise ValueError("该来源由 PriceAI 快照维护，不能进行本地店铺扫描")
        if not self._local_ingest_lock.acquire(blocking=False):
            raise LocalScanBusy(token)
        self._local_ingest_idle.clear()
        source_lock = self._source_lock_for(token)
        source_lock.acquire()

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
                if existing is not None:
                    self._keep_refresh_metadata(product, existing)
                found.add(goods_key)
                change, saved = self.database.upsert_product(product)
                if change != "unchanged":
                    changed += 1
                self.events.publish("product", {"change": change, "product": saved})
                self._queue_new_ai_classification(change)

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
            source_lock.release()
            self._local_ingest_lock.release()
            self._local_ingest_idle.set()

    @staticmethod
    def _priceai_snapshot_url(latest: Any) -> str:
        if not isinstance(latest, dict):
            raise LDXPError("PriceAI latest.json 格式不正确")
        snapshot_url = str(latest.get("snapshot_url") or "").strip()
        parsed = urllib.parse.urlsplit(snapshot_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != PRICEAI_SNAPSHOT_HOST
            or not parsed.path.startswith("/v1/snapshots/")
        ):
            raise LDXPError("PriceAI 快照地址无效")
        return snapshot_url

    def _publish_snapshot(self) -> None:
        self.events.publish(
            "snapshot",
            {
                "stats": self.database.stats(),
                "catalog_revision": self.database.catalog_revision(),
                "sources": self.database.list_sources(),
                "scanning": self.scanning,
                "last_started": self.last_started,
                "last_completed": self.last_completed,
            },
        )

    def _sync_priceai_snapshot_locked(self) -> dict[str, Any]:
        self.events.publish("priceai_sync", {"phase": "started"})
        source = self.database.upsert_source(
            PRICEAI_SOURCE_TOKEN,
            "PriceAI 公开快照",
            enabled=True,
            origin="PriceAI 公开快照",
            base_url="https://priceai.cc",
            remote_token="top5",
            source_kind="snapshot",
            source_url=PRICEAI_SOURCE_URL,
        )
        try:
            latest = self._read_json_url(PRICEAI_LATEST_URL, timeout=PRICEAI_REQUEST_TIMEOUT)
            snapshot_url = self._priceai_snapshot_url(latest)
            payload = self._read_json_url(snapshot_url, timeout=PRICEAI_REQUEST_TIMEOUT)
            products = payload.get("products") if isinstance(payload, dict) else None
            if not isinstance(products, list):
                raise LDXPError("PriceAI 快照未包含商品列表")

            seen: set[str] = set()
            matched = 0
            changed = 0
            for catalog_product in products[:200]:
                if not isinstance(catalog_product, dict):
                    continue
                offers = catalog_product.get("top_offers")
                if not isinstance(offers, list):
                    continue
                for offer in offers[:20]:
                    if not isinstance(offer, dict):
                        continue
                    product = product_from_priceai_offer(offer, catalog_product)
                    if product is None or product["goods_key"] in seen:
                        continue
                    seen.add(product["goods_key"])
                    matched += 1
                    change, saved = self.database.upsert_product(product)
                    if change != "unchanged":
                        changed += 1
                    self.events.publish("product", {"change": change, "product": saved})
                    self._queue_new_ai_classification(change)

            removed_keys = self.database.deactivate_missing(PRICEAI_SOURCE_TOKEN, seen)
            for goods_key in removed_keys:
                self.events.publish("product_remove", {"goods_key": goods_key})
            self.database.update_source_scan(
                str(source["token"]),
                status="ok",
                name="PriceAI 公开快照",
                error="",
                count=matched,
                scanned=True,
            )
            result = {
                "matched": matched,
                "changed": changed,
                "removed": len(removed_keys),
                "snapshot_id": str(payload.get("snapshot_id") or ""),
            }
            self._publish_snapshot()
            self.events.publish("priceai_sync", {"phase": "completed", **result})
            return result
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self.database.update_source_scan(
                str(source["token"]), status="error", name="PriceAI 公开快照", error=message
            )
            self.events.publish("priceai_sync", {"phase": "error", "error": message})
            raise

    def sync_priceai_snapshot(self) -> dict[str, Any]:
        if not self._priceai_sync_lock.acquire(blocking=False):
            raise PriceAISyncBusy()
        try:
            return self._sync_priceai_snapshot_locked()
        finally:
            self._priceai_sync_lock.release()

    def trigger_priceai_sync(self) -> bool:
        if not self._priceai_sync_lock.acquire(blocking=False):
            return False

        def worker() -> None:
            try:
                self._sync_priceai_snapshot_locked()
            except Exception:
                pass
            finally:
                self._priceai_sync_lock.release()

        threading.Thread(target=worker, name="priceai-sync", daemon=True).start()
        return True

    def _publish_ai_classification(self, phase: str, **extra: Any) -> None:
        self.events.publish(
            "ai_classification",
            {"phase": phase, **self.ai_classification_status(), **extra},
        )

    def _fetch_ai_description(self, product: dict[str, Any]) -> str:
        source = self.database.get_source(str(product.get("source_token") or ""))
        if source is None or source.get("source_kind") != "shop_api":
            return clean_text(product.get("description_excerpt"), 1000)
        goods_key = str(product.get("goods_key") or "")
        if not goods_key or goods_key.startswith("priceai:"):
            return clean_text(product.get("description_excerpt"), 1000)
        base_url = str(source.get("base_url") or LDXP_BASE_URL)
        item = LDXPClient(base_url=base_url).goods_info(goods_key)
        description = clean_text(item.get("description"), 1000)
        if description:
            self.database.update_product_description_excerpt(goods_key, description)
        return description or clean_text(product.get("description_excerpt"), 1000)

    def _set_ai_status(
        self,
        *,
        running: bool | None = None,
        total: int | None = None,
        processed: int | None = None,
        updated: int | None = None,
        failed: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._ai_status_lock:
            if running is not None:
                self.ai_classifying = running
            if total is not None:
                self.ai_classification_total = total
            if processed is not None:
                self.ai_classification_processed = processed
            if updated is not None:
                self.ai_classification_updated = updated
            if failed is not None:
                self.ai_classification_failed = failed
            if error is not None:
                self.ai_classification_error = error[:500]

    def _run_ai_classification(self) -> None:
        classifier = AIProductClassifier()
        self._publish_ai_classification("started")
        try:
            while not self._stop.is_set():
                batch = self.database.pending_ai_classification_products(
                    LDXP_AI_CLASSIFIER_BATCH_SIZE
                )
                if not batch:
                    break
                goods_keys = [str(product["goods_key"]) for product in batch]
                try:
                    first_pass = classifier.classify(batch, with_descriptions=False)
                    ready: dict[str, list[str]] = {}
                    need_details = [
                        product
                        for product in batch
                        if first_pass[str(product["goods_key"])]["needs_description"]
                    ]
                    for product in batch:
                        goods_key = str(product["goods_key"])
                        if not first_pass[goods_key]["needs_description"]:
                            ready[goods_key] = first_pass[goods_key]["tags"]

                    detail_failures: list[str] = []
                    if need_details:
                        enriched: list[dict[str, Any]] = []
                        for product in need_details:
                            try:
                                description = self._fetch_ai_description(product)
                            except Exception:
                                detail_failures.append(str(product["goods_key"]))
                                continue
                            if not description:
                                detail_failures.append(str(product["goods_key"]))
                                continue
                            enriched.append({**product, "description_excerpt": description})
                        if enriched:
                            second_pass = classifier.classify(enriched, with_descriptions=True)
                            ready.update(
                                {
                                    goods_key: result["tags"]
                                    for goods_key, result in second_pass.items()
                                }
                            )
                    updated = self.database.save_ai_classifications(ready)
                    if detail_failures:
                        self.database.mark_ai_classification_failed(
                            detail_failures, "商品详情未返回可用描述"
                        )
                    processed = len(ready) + len(detail_failures)
                    with self._ai_status_lock:
                        self.ai_classification_processed += processed
                        self.ai_classification_updated += updated
                        self.ai_classification_failed += len(detail_failures)
                    self._publish_ai_classification("progress")
                except AIClassificationError as exc:
                    self.database.mark_ai_classification_failed(goods_keys, str(exc))
                    with self._ai_status_lock:
                        self.ai_classification_processed += len(goods_keys)
                        self.ai_classification_failed += len(goods_keys)
                        self.ai_classification_error = str(exc)[:500]
                    self._publish_ai_classification("progress")
                if LDXP_AI_CLASSIFIER_DELAY and self._stop.wait(LDXP_AI_CLASSIFIER_DELAY):
                    break
        except Exception as exc:
            self._set_ai_status(error=str(exc) or exc.__class__.__name__)
            self._publish_ai_classification("error")
        finally:
            self._set_ai_status(running=False)
            self._publish_snapshot()
            self._publish_ai_classification("completed")
            self._ai_classification_lock.release()

    def trigger_ai_classification(self, *, force: bool = False) -> bool:
        if not AI_CLASSIFICATION_ENABLED:
            raise AIClassificationError("AI classification is disabled")
        AIProductClassifier()
        if not self._ai_classification_lock.acquire(blocking=False):
            return False
        try:
            if force:
                self.database.reset_ai_classification()
                self.database.set_settings({"ai_classification_enabled": "true"})
                self.ai_auto_classification_enabled = True
            total = self.database.pending_ai_classification_count()
            self._set_ai_status(
                running=True,
                total=total,
                processed=0,
                updated=0,
                failed=0,
                error="",
            )
            threading.Thread(
                target=self._run_ai_classification,
                name="ai-product-classifier",
                daemon=True,
            ).start()
        except Exception:
            self._ai_classification_lock.release()
            raise
        return True

    def _queue_new_ai_classification(self, change: str) -> None:
        if change != "new" or not self.ai_auto_classification_enabled:
            return
        try:
            self.trigger_ai_classification()
        except AIClassificationError:
            # Keep the product pending so an administrator can correct the configuration.
            pass

    def _publish_status(self, phase: str, **extra: Any) -> None:
        self.events.publish(
            "scan_status",
            {
                "phase": phase,
                "scanning": self.scanning,
                "last_started": self.last_started,
                "last_completed": self.last_completed,
                "task": self.scan_task(),
                **extra,
            },
        )

    @staticmethod
    def _read_json_url(url: str, *, timeout: int = 20) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; LDXPPriceScanner/1.0)",
            },
        )
        with urllib.request.urlopen(request, timeout=max(1, timeout)) as response:
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

    def _fetch_scdn_proxy(self, excluded: set[str]) -> ProxyEndpoint | None:
        page = self._scdn_proxy_page
        try:
            candidates, total_pages = SCDNProxySource().fetch_page(page)
        except LDXPError as exc:
            self.events.publish("proxy_pool", {"phase": "fetch_error", "error": str(exc)})
            return None
        self._scdn_proxy_page = page % total_pages + 1
        known = self.database.known_daily_proxy_endpoints()
        for candidate in candidates:
            if candidate.endpoint not in excluded and candidate.endpoint not in known:
                self.events.publish(
                    "proxy_pool",
                    {"phase": "page_candidate", "page": page, "total_pages": total_pages},
                )
                return candidate
        self.events.publish(
            "proxy_pool", {"phase": "duplicate_page", "page": page, "total_pages": total_pages}
        )
        return None

    def _proxy_client(self, base_url: str, candidate: ProxyEndpoint) -> LDXPClient:
        return LDXPClient(
            base_url=base_url,
            timeout=LDXP_SCDN_PROXY_TIMEOUT,
            proxy_url=candidate.proxy_url,
            direct_attempts=0,
            proxy_attempts=1,
            retry_delay=LDXP_RETRY_DELAY,
            proxy_observer=lambda success: self.database.record_proxy_result(
                candidate.endpoint, candidate.protocol, success
            ),
        )

    def _scan_pending_with_proxy(
        self,
        pending: dict[str, dict[str, Any]],
        candidate: ProxyEndpoint,
        result: ScanResult,
        source_positions: dict[str, int],
        source_total: int,
    ) -> None:
        self.events.publish(
            "proxy_pool",
            {"phase": "proxy_round_started", "summary": self.database.proxy_pool_summary()},
        )
        queued = list(pending.values())
        for position, source in enumerate(queued):
            if self._stop.is_set():
                return
            if not self._wait_for_local_ingest():
                return
            token = str(source["token"])
            source_started = time.monotonic()
            self._mark_source_started(token)
            self.database.update_source_scan(token, status="scanning")
            self._publish_status(
                "source_started",
                token=token,
                source_index=source_positions[token],
                source_total=source_total,
                proxy_mode="scdn",
            )
            try:
                client = self._proxy_client(str(source.get("base_url") or LDXP_BASE_URL), candidate)
                matched, changed = self._scan_source(token, client=client)
            except LDXPTransportError as exc:
                result.paused += 1
                message = str(exc) or exc.__class__.__name__
                self.database.update_source_scan(token, status="paused", error=message, count=None)
                self._publish_status("source_paused", token=token, error=message, proxy_mode="scdn")
                # A connection-level failure cannot help any other source. Move on
                # immediately so the next candidate can resume this checkpoint.
                self._mark_source_idle(token)
                return
            except LDXPError as exc:
                result.paused += 1
                message = str(exc) or exc.__class__.__name__
                self.database.update_source_scan(token, status="paused", error=message, count=None)
                self._publish_status("source_paused", token=token, error=message, proxy_mode="scdn")
                self._mark_source_idle(token)
            except Exception as exc:
                result.failed += 1
                message = str(exc) or exc.__class__.__name__
                self.database.update_source_scan(token, status="error", error=message, count=None)
                self._publish_status("source_error", token=token, error=message)
                pending.pop(token, None)
                self._mark_source_idle(token, completed=True)
            else:
                result.succeeded += 1
                result.matched += matched
                result.changed += changed
                pending.pop(token, None)
                self._mark_source_idle(token, completed=True)
            if position < len(queued) - 1:
                delay = remaining_cycle_delay(
                    self.proxy_source_interval, time.monotonic() - source_started
                )
                if delay and self._stop.wait(delay):
                    return

    def _scan_pending_with_default_route(
        self,
        pending: dict[str, dict[str, Any]],
        result: ScanResult,
        source_positions: dict[str, int],
        source_total: int,
    ) -> None:
        queued = list(pending.values())
        for position, source in enumerate(queued):
            if self._stop.is_set():
                return
            if not self._wait_for_local_ingest():
                return
            token = str(source["token"])
            source_started = time.monotonic()
            self._mark_source_started(token)
            self.database.update_source_scan(token, status="scanning")
            self._publish_status(
                "source_started",
                token=token,
                source_index=source_positions[token],
                source_total=source_total,
                proxy_mode="default",
            )
            try:
                matched, changed = self._scan_source(token)
            except Exception as exc:
                result.failed += 1
                message = str(exc) or exc.__class__.__name__
                self.database.update_source_scan(token, status="error", error=message, count=None)
                self._publish_status("source_error", token=token, error=message)
            else:
                result.succeeded += 1
                result.matched += matched
                result.changed += changed
            pending.pop(token, None)
            self._mark_source_idle(token, completed=True)
            if position < len(queued) - 1:
                delay = remaining_cycle_delay(
                    self.source_interval, time.monotonic() - source_started
                )
                if delay and self._stop.wait(delay):
                    return

    def _scan_all_with_scdn_proxy_pool(
        self,
        sources: list[dict[str, Any]],
        result: ScanResult,
        *,
        allow_direct_fallback: bool = True,
    ) -> None:
        pending = {str(source["token"]): source for source in sources}
        positions = {str(source["token"]): index for index, source in enumerate(sources, start=1)}
        attempted: set[str] = set()

        for _ in range(min(self.database.daily_proxy_count(), LDXP_SCDN_PROXY_ROUNDS_PER_CYCLE)):
            candidate = self.database.next_daily_proxy(attempted)
            if candidate is None:
                break
            attempted.add(candidate.endpoint)
            result.proxy_rounds += 1
            self._scan_pending_with_proxy(pending, candidate, result, positions, len(sources))
            if not pending or self._stop.is_set():
                return

        for _ in range(LDXP_SCDN_PROXY_CANDIDATES_PER_CYCLE):
            candidate = self._fetch_scdn_proxy(attempted)
            if candidate is None:
                continue
            attempted.add(candidate.endpoint)
            result.proxy_rounds += 1
            self._scan_pending_with_proxy(pending, candidate, result, positions, len(sources))
            if not pending or self._stop.is_set():
                return

        if pending and allow_direct_fallback and not self._stop.is_set():
            self.events.publish("proxy_pool", {"phase": "default_fallback"})
            self._scan_pending_with_default_route(pending, result, positions, len(sources))
        elif pending and not self._stop.is_set():
            for token in pending:
                self.database.update_source_scan(
                    token,
                    status="paused",
                    error="代理池没有可用节点，本轮未使用服务器直连",
                    count=None,
                )
                self._publish_status(
                    "source_paused",
                    token=token,
                    error="代理池没有可用节点",
                    proxy_mode="proxy_only",
                )

    def _scan_all(self, reason: str) -> None:
        """Run a scheduled scan in the current thread after reserving its task slot."""
        if reason == "scheduled" and not self.auto_scan_enabled:
            return
        if self._local_ingest_lock.locked() or not self._scan_lock.acquire(blocking=False):
            return
        self._begin_scan(reason)
        self._scan_all_reserved(reason)

    def _scan_all_reserved(self, reason: str) -> None:
        """Run a scan whose lock and visible task state were reserved by trigger()."""
        result = ScanResult()
        proxy_only = reason == "manual_proxy_only"
        try:
            if reason in {"manual", "manual_proxy_only"}:
                # Make an accepted full scan immediately joinable, including while
                # source discovery is still running before the first source starts.
                self._set_pending_scan_sources(
                    self.database.list_sources_due_for_scan(scheduled=False)
                )
            if not proxy_only:
                try:
                    self._discover_sources(force=reason in {"startup", "discovery"})
                except Exception as exc:
                    self.last_discovery = now_ts()
                    self.events.publish(
                        "discovery_status",
                        {"phase": "error", "error": str(exc) or exc.__class__.__name__},
                    )
            sources = self.database.list_sources_due_for_scan(
                scheduled=reason == "scheduled"
            )
            result.source_count = len(sources)
            self._set_pending_scan_sources(sources)
            if LDXP_SCDN_PROXY_POOL_ENABLED or proxy_only:
                self._scan_all_with_scdn_proxy_pool(
                    sources,
                    result,
                    allow_direct_fallback=not proxy_only,
                )
            else:
                for index, source in enumerate(sources, start=1):
                    if self._stop.is_set():
                        break
                    if reason == "scheduled" and not self.auto_scan_enabled:
                        break
                    if not self._wait_for_local_ingest():
                        break
                    source_started = time.monotonic()
                    token = str(source["token"])
                    self._mark_source_started(token)
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
                    finally:
                        self._mark_source_idle(token, completed=True)
                    if index < len(sources):
                        source_elapsed = time.monotonic() - source_started
                        source_delay = remaining_cycle_delay(self.source_interval, source_elapsed)
                        if source_delay and self._stop.wait(source_delay):
                            break
        finally:
            self._finish_scan(result)

    def _finish_scan(self, result: ScanResult | None = None) -> None:
        with self._scan_state_lock:
            self.scanning = False
            self.last_completed = now_ts()
            self._scan_reason = ""
            self._active_source_token = ""
            self._pending_scan_sources.clear()
        if self._scan_lock.locked():
            self._scan_lock.release()
        snapshot = {
            "stats": self.database.stats(),
            "catalog_revision": self.database.catalog_revision(),
            "sources": self.database.list_sources(),
            "scanning": False,
            "scan_task": self.scan_task(),
            "last_started": self.last_started,
            "last_completed": self.last_completed,
        }
        self.events.publish("snapshot", snapshot)
        self._publish_status("completed", result=(result or ScanResult()).__dict__)

    def _scan_source(self, token: str, client: LDXPClient | None = None) -> tuple[int, int]:
        with self._source_lock_for(token):
            return self._scan_source_unlocked(token, client=client)

    def _scan_source_unlocked(
        self, token: str, client: LDXPClient | None = None
    ) -> tuple[int, int]:
        source = self.database.get_source(token)
        if source is None:
            raise KeyError(token)
        if source.get("source_kind") != "shop_api":
            raise ValueError("该来源不是店铺 API 采集源")
        base_url = str(source.get("base_url") or LDXP_BASE_URL)
        remote_token = str(source.get("remote_token") or token)
        checkpoint = self.database.get_or_create_scan_checkpoint(token)
        client = client or LDXPClient(base_url=base_url)
        info = client.shop_info(remote_token)
        source_name = str(info.get("nickname") or remote_token)
        self.database.update_source_scan(token, status="scanning", name=source_name)
        changed_count = 0
        cycle_id = str(checkpoint["cycle_id"])

        available_types = [
            goods_type
            for goods_type in GOODS_TYPES
            if safe_int(info.get(f"{goods_type}_count"), 0) > 0
        ]
        if not available_types:
            available_types = list(GOODS_TYPES)

        phase = str(checkpoint.get("phase") or "pages")
        resume_type = str(checkpoint.get("goods_type") or "")
        if phase == "pages" and not resume_type:
            start_index = 0
        elif phase == "pages" and resume_type in available_types:
            start_index = available_types.index(resume_type)
        elif phase == "pages" and resume_type in GOODS_TYPES:
            resume_position = GOODS_TYPES.index(resume_type)
            start_index = next(
                (
                    index
                    for index, goods_type in enumerate(available_types)
                    if GOODS_TYPES.index(goods_type) >= resume_position
                ),
                len(available_types),
            )
        else:
            start_index = len(available_types)

        for type_index in range(start_index, len(available_types)):
            goods_type = available_types[type_index]
            page = int(checkpoint.get("page") or 1) if goods_type == resume_type else 1
            page_size = LDXP_PAGE_SIZE
            while page <= LDXP_MAX_PAGES:
                payload = client.goods_page(remote_token, goods_type, page, page_size)
                items = payload.get("list") or []
                total = safe_int(payload.get("total"), len(items))
                for item in items:
                    product = product_from_api(item, token, source_name, base_url)
                    if product is None:
                        continue
                    self.database.mark_scan_seen(token, cycle_id, product["goods_key"])
                    change, saved = self.database.upsert_product(product)
                    if change != "unchanged":
                        changed_count += 1
                    self.events.publish("product", {"change": change, "product": saved})
                    self._queue_new_ai_classification(change)
                if not items or page * page_size >= total or len(items) < page_size:
                    if type_index + 1 < len(available_types):
                        self.database.update_scan_checkpoint(
                            token,
                            cycle_id,
                            phase="pages",
                            goods_type=available_types[type_index + 1],
                            page=1,
                            source_name=source_name,
                        )
                    else:
                        self.database.update_scan_checkpoint(
                            token,
                            cycle_id,
                            phase="entry",
                            source_name=source_name,
                        )
                    break
                page += 1
                self.database.update_scan_checkpoint(
                    token,
                    cycle_id,
                    phase="pages",
                    goods_type=goods_type,
                    page=page,
                    source_name=source_name,
                )
                if LDXP_PAGE_DELAY:
                    time.sleep(LDXP_PAGE_DELAY)

        entry_goods_key = str(source.get("entry_goods_key") or "").strip()
        if entry_goods_key and not self.database.scan_seen_contains(token, cycle_id, entry_goods_key):
            item = client.goods_info(entry_goods_key)
            product = product_from_api(item, token, source_name, base_url)
            if product is not None:
                self.database.mark_scan_seen(token, cycle_id, product["goods_key"])
                change, saved = self.database.upsert_product(product)
                if change != "unchanged":
                    changed_count += 1
                self.events.publish("product", {"change": change, "product": saved})
                self._queue_new_ai_classification(change)

        matched_count = self.database.scan_seen_count(token, cycle_id)
        removed_keys = self.database.complete_scan_checkpoint(token, cycle_id)
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

    def snapshot(self, include_products: bool = False) -> dict[str, Any]:
        payload = {
            "stats": self.database.stats(),
            "catalog_revision": self.database.catalog_revision(),
            "sources": self.database.list_sources(),
            "categories": [{"key": item["key"], "label": item["label"]} for item in CATEGORY_DEFINITIONS],
            "scanning": self.scanner.scanning,
            "scan_task": self.scanner.scan_task(),
            "ai_classification": self.scanner.ai_classification_status(),
            "last_started": self.scanner.last_started,
            "last_completed": self.scanner.last_completed,
            "last_discovery": self.scanner.last_discovery,
            "scan_interval": self.scanner.interval,
            "discovery_interval": DISCOVERY_INTERVAL,
            "auto_scan_enabled": self.scanner.auto_scan_enabled,
            "source_interval": self.scanner.source_interval,
            "page_size": LDXP_PAGE_SIZE,
            "failover_proxy_enabled": bool(LDXP_FAILOVER_PROXY_URL),
            "scdn_proxy_pool": {
                "enabled": LDXP_SCDN_PROXY_POOL_ENABLED,
                **self.database.proxy_pool_summary(),
            },
            "scan_checkpoints": self.database.scan_checkpoint_summary(),
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
            self._send_json({"ok": True, **self.app.snapshot(include_products=False)})
        elif path == "/api/products/stream":
            self._serve_product_stream(parsed.query)
        elif path == "/api/events":
            self._serve_events()
        elif path.startswith("/api/products/") and path.endswith("/refresh-status"):
            encoded_key = path[len("/api/products/") : -len("/refresh-status")]
            goods_key = urllib.parse.unquote(encoded_key).strip()
            if not goods_key or "/" in goods_key or len(goods_key) > 200:
                self._error(HTTPStatus.BAD_REQUEST, "商品标识无效")
                return
            try:
                self._send_json({"ok": True, **self.app.scanner.product_refresh_status(goods_key)})
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "商品不存在或已下架")
        elif path.startswith("/api/history/"):
            goods_key = urllib.parse.unquote(path.removeprefix("/api/history/"))
            self._send_json({"ok": True, "history": self.app.database.history(goods_key)})
        elif path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "接口不存在")
        else:
            self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/admin/verify":
            if not self._require_admin():
                return
            self._send_json({"ok": True, "admin": True})
            return
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
            request = self.app.scanner.request_scan("manual")
            self._send_json(
                {
                    "ok": True,
                    **request,
                    "message": (
                        "服务器全量扫描已启动"
                        if request["started"]
                        else "服务器同类扫描正在进行中，已加入实时更新"
                        if request["joined"]
                        else "服务器正在执行另一类扫描，请等待当前任务结束"
                        if request["busy"]
                        else "当前有用户刷新任务，服务器全量扫描暂未启动"
                    ),
                },
                HTTPStatus.ACCEPTED,
            )
            return
        if path == "/api/scan/proxy-only":
            if not self._require_admin():
                return
            request = self.app.scanner.request_scan("manual_proxy_only")
            self._send_json(
                {
                    "ok": True,
                    **request,
                    "message": (
                        "代理池全量扫描已启动，不会使用服务器直连"
                        if request["started"]
                        else "服务器同类扫描正在进行中，已加入实时更新"
                        if request["joined"]
                        else "服务器正在执行另一类扫描，请等待当前任务结束"
                        if request["busy"]
                        else "当前有用户刷新任务，服务器扫描暂未启动"
                    ),
                },
                HTTPStatus.ACCEPTED,
            )
            return
        if path == "/api/import/priceai":
            if not self._require_admin():
                return
            started = self.app.scanner.trigger_priceai_sync()
            self._send_json(
                {
                    "ok": True,
                    "started": started,
                    "message": (
                        "PriceAI 公开快照同步已启动"
                        if started
                        else "PriceAI 快照同步正在进行中"
                    ),
                },
                HTTPStatus.ACCEPTED,
            )
            return
        if path == "/api/classify":
            self._error(HTTPStatus.GONE, "AI classification is disabled")
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
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except ProductRefreshBusy:
                self._error(HTTPStatus.CONFLICT, "该商品正在刷新")
            except ProductRefreshInProgress:
                self._send_json(
                    {
                        "ok": True,
                        "started": False,
                        "joined": True,
                        "refreshing": True,
                        "message": "该商品所在店铺正在由服务器全量扫描，已加入实时更新",
                    },
                    HTTPStatus.ACCEPTED,
                )
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
                scan_queued = self.app.scanner.request_submitted_source_scan(token)
                self._send_json(
                    {"ok": True, "source": source, "scan_queued": scan_queued},
                    HTTPStatus.CREATED,
                )
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
            if not self._require_admin():
                return
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
            if not self._require_admin():
                return
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

    def _serve_product_stream(self, raw_query: str) -> None:
        query = urllib.parse.parse_qs(raw_query, keep_blank_values=True)

        def query_value(key: str, default: str) -> str:
            values = query.get(key)
            return values[-1] if values else default

        category = query_value("category", "all")
        allowed_categories = {"all", *(item["key"] for item in CATEGORY_DEFINITIONS)}
        if category not in allowed_categories:
            self._error(HTTPStatus.BAD_REQUEST, "商品分类无效")
            return

        sort = query_value("sort", "price")
        if sort not in {"price", "stock", "updated"}:
            self._error(HTTPStatus.BAD_REQUEST, "商品排序无效")
            return

        stock_only = query_value("stock_only", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        try:
            min_price = parse_price_filter(
                query_value("min_price", "0"), name="最低价格", default=0
            )
            max_price = parse_price_filter(
                query_value("max_price", ""), name="最高价格", default=None
            )
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if max_price is not None and max_price < min_price:
            self._error(HTTPStatus.BAD_REQUEST, "最高价格不能低于最低价格")
            return
        include_left = query_value("include_min", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        search = clean_text(query_value("search", ""), 120)
        offset = max(0, min(1_000_000, safe_int(query_value("offset", "0"), 0)))
        limit = max(
            1,
            min(
                PRODUCT_STREAM_MAX_LIMIT,
                safe_int(query_value("limit", str(PRODUCT_STREAM_DEFAULT_LIMIT)), PRODUCT_STREAM_DEFAULT_LIMIT),
            ),
        )
        page = self.app.database.list_product_page(
            category=category,
            stock_only=stock_only,
            search=search,
            sort=sort,
            min_price=min_price,
            max_price=max_price,
            include_left=include_left,
            offset=offset,
            limit=limit,
        )
        products = page["products"]
        next_offset = offset + len(products)
        metadata = {
            "type": "meta",
            "total": page["total"],
            "catalog_revision": page["catalog_revision"],
            "offset": offset,
            "next_offset": next_offset,
            "has_more": next_offset < page["total"],
        }

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            def write_record(record: dict[str, Any]) -> None:
                self.wfile.write(
                    (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                )
                self.wfile.flush()

            write_record(metadata)
            for product in products:
                write_record({"type": "product", "product": product})
            write_record({"type": "end"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.close_connection = True

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
                {
                    "connected": True,
                    "scanning": self.app.scanner.scanning,
                    "task": self.app.scanner.scan_task(),
                },
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
    database.reclassify_products()
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
