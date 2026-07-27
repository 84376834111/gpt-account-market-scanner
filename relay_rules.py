from __future__ import annotations

import re


EXCLUDED_TITLE_TERMS = (
    "邮箱", "outlook", "hotmail", "gmail", "icloud", "接码", "手机号", "手机卡",
    "短信", "imap", "pop3", "oauth", "graph令牌", "令牌号", "账号", "成品号",
    "free号", "plus号", "team子号", "k12", "sub2api", "cpa", "json",
    "参考", "教程", "脚本", "远程安装",
)
MODEL_TERMS = ("gpt", "chatgpt", "codex", "claude", "grok", "gemini", "deepseek", "kiro")


def relay_classification_reason(name: str, description: str = "") -> str:
    """Return a conservative relay-service reason derived primarily from the title."""
    title = re.sub(r"\s+", " ", str(name or "")).strip().casefold()
    excluded = any(term in title for term in EXCLUDED_TITLE_TERMS)
    credit_signal = re.search(r"(额度|余额|兑换码|cdk|卡密|\d+\s*刀|倍率|api)", title)
    if "中转站" in title and not excluded and credit_signal:
        return "explicit_relay_station"
    if any(term in title for term in ("源头中转", "中转额度", "中转余额", "中转特供")) and "送" not in title:
        return "explicit_relay_product"
    if "中转" in title and credit_signal and not excluded:
        return "relay_credit"
    if any(term in title for term in ("官转", "逆向")) and any(term in title for term in MODEL_TERMS):
        return "official_or_reverse_relay"
    if excluded:
        return ""
    if "api" in title and re.search(r"(额度|余额|兑换码|cdk|密钥|key|按量|倍率|充值|\d+\s*刀)", title):
        return "api_credit"
    if "余额卡" in title and any(term in title for term in MODEL_TERMS):
        return "model_balance_card"
    if re.search(r"\d+\s*刀额度", title) and any(term in title for term in MODEL_TERMS):
        return "model_dollar_credit"
    if "订阅" in title:
        return ""
    if "额度" in title and any(term in title for term in MODEL_TERMS) and any(
        marker in title for marker in ("美金", "刀", "余额", "兑换码", "充值", "倍率")
    ):
        return "model_credit"
    return ""
