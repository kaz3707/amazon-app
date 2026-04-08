import configparser
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config.ini"


def _load_config():
    config = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        config.read(CONFIG_FILE, encoding="utf-8")
    return config


_cfg = _load_config()


class SaleMonsterConfig:
    login_id: str = _cfg.get("sale_monster", "login_id", fallback="")
    password: str = _cfg.get("sale_monster", "password", fallback="")
    login_url: str = _cfg.get(
        "sale_monster", "login_url", fallback="https://www.sale-monster.com/login"
    )


class CacheConfig:
    fee_ttl_hours: int = int(_cfg.get("cache", "fee_cache_ttl_hours", fallback="24"))
    customs_ttl_days: int = int(_cfg.get("cache", "customs_cache_ttl_days", fallback="7"))
    exchange_rate_ttl_minutes: int = int(
        _cfg.get("cache", "exchange_rate_ttl_minutes", fallback="60")
    )


class KeepaConfig:
    api_key: str = _cfg.get("keepa", "api_key", fallback="")


class ClaudeConfig:
    api_key: str = _cfg.get("claude", "api_key", fallback="")
    model: str = _cfg.get("claude", "model", fallback="claude-sonnet-4-6")


class AppConfig:
    TEST_MODE: bool = _cfg.get("app", "test_mode", fallback="false").lower() == "true"
    DEBUG: bool = _cfg.get("app", "debug", fallback="true").lower() == "true"
    SECRET_KEY: str = _cfg.get("app", "secret_key", fallback="dev-secret-key-change-me")
    UPLOAD_FOLDER: str = str(BASE_DIR / _cfg.get("app", "upload_folder", fallback="uploads"))
    MAX_UPLOAD_BYTES: int = int(_cfg.get("app", "max_upload_size_mb", fallback="10")) * 1024 * 1024
    DATABASE_URI: str = f"sqlite:///{BASE_DIR / 'instance' / 'database.db'}"
