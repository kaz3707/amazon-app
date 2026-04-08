"""
為替レート取得サービス。
無料API（open.er-api.com）を使用。APIキー不要。
"""
import requests
from utils.cache_manager import get_exchange_rate_from_cache, save_exchange_rate_to_cache
from config.settings import AppConfig


def get_cny_to_jpy() -> float:
    """人民元→円の為替レートを返す。キャッシュ優先。"""
    if AppConfig.TEST_MODE:
        return 21.56  # テストモード固定値

    pair = "CNY_JPY"
    cached = get_exchange_rate_from_cache(pair)
    if cached is not None:
        return cached

    rate = _fetch_from_api()
    save_exchange_rate_to_cache(pair, rate)
    return rate


def _fetch_from_api() -> float:
    """外部APIから人民元→円レートを取得する。"""
    try:
        # open.er-api.com: 無料・APIキー不要
        resp = requests.get(
            "https://open.er-api.com/v6/latest/CNY",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"]["JPY"]
        return float(rate)
    except Exception:
        pass

    try:
        # フォールバック: frankfurter.app
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=CNY&to=JPY",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data["rates"]["JPY"])
    except Exception:
        # 最終フォールバック: 固定値
        return 21.5
