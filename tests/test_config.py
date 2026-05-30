"""
Tests for core/config.py — centralized configuration loader.
"""
import pytest
from core import config


class TestConfig:
    def test_get_returns_env_var(self, monkeypatch):
        monkeypatch.setenv("TEST_CONFIG_KEY", "hello")
        assert config.get("TEST_CONFIG_KEY") == "hello"

    def test_get_returns_default(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_KEY_12345", raising=False)
        assert config.get("NONEXISTENT_KEY_12345", "fallback") == "fallback"

    def test_get_int(self, monkeypatch):
        monkeypatch.setenv("INT_KEY", "42")
        assert config.get_int("INT_KEY") == 42

    def test_get_int_default(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_INT_KEY", raising=False)
        assert config.get_int("NONEXISTENT_INT_KEY", 99) == 99

    def test_get_int_invalid(self, monkeypatch):
        monkeypatch.setenv("BAD_INT", "not_a_number")
        assert config.get_int("BAD_INT", 7) == 7

    def test_get_bool_true(self, monkeypatch):
        for val in ("1", "true", "True", "YES", "yes"):
            monkeypatch.setenv("BOOL_KEY", val)
            assert config.get_bool("BOOL_KEY") is True

    def test_get_bool_false(self, monkeypatch):
        monkeypatch.setenv("BOOL_KEY", "0")
        assert config.get_bool("BOOL_KEY") is False

    def test_get_bool_default(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_BOOL_KEY", raising=False)
        assert config.get_bool("NONEXISTENT_BOOL_KEY", True) is True
