"""
Centralized configuration loader.

Single call to load_dotenv(); provides typed getters for environment variables.
"""
import os
from dotenv import load_dotenv

# Load .env once at import time
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_ENV_PATH)

_loaded = True


def get(key: str, default: str = "") -> str:
    """Return an environment variable as a string."""
    return os.getenv(key, default)


def get_int(key: str, default: int = 0) -> int:
    """Return an environment variable as an integer."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_float(key: str, default: float = 0.0) -> float:
    """Return an environment variable as a float."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """Return an environment variable as a boolean. Truthy: '1', 'true', 'yes'."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes")


class MaskedSecret(str):
    """日志中自动掩码的字符串。str() 返回原始值，repr() 返回掩码。"""

    def __repr__(self):
        if len(self) <= 8:
            return "'****'"
        return f"'{self[:4]}...{self[-4:]}'"


def get_secret(key: str, default: str = "") -> str:
    """Return an environment variable as a MaskedSecret (safe for logging)."""
    val = os.getenv(key, default)
    return MaskedSecret(val) if val else MaskedSecret(default)
