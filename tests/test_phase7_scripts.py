"""
TDD Tests for Phase 7 - Active Intelligence Scripts

Tests are written FIRST (TDD). No production API calls are made;
all external dependencies (yfinance, Gemini, Telegram) are mocked.

Covers:
  - scripts/earnings_reminder.py
  - scripts/morning_scan_push.py
  - scripts/weekly_position_report.py

Run with:
    pytest tests/test_phase7_scripts.py -v
"""
import os
import sys
import json
import textwrap
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_holdings_json(tmp_dir):
    """Write a minimal holdings.json for tests."""
    holdings = {
        "tickers": {
            "NVDA": {"strategy": "Long-Term Core", "sector": "Technology"},
            "8888.HK": {"strategy": "Long-Term Core", "sector": "Energy"},
        },
        "cash": {"CNY": 10000.0}
    }
    path = os.path.join(tmp_dir, "holdings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False)
    return path


@pytest.fixture
def sample_scan_report(tmp_dir):
    """Write a minimal Market Scan report for tests."""
    today = "20260310"
    report_dir = os.path.join(tmp_dir, today)
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{today}_Market_Scan.md")
    content = textwrap.dedent("""\
        # 20260310 市场全景扫描

        > **主战场：** A股/港股 (盘前/盘中)
        > **市场体温：** Risk On (进攻)
        > **一句话摘要：** 油运板块爆发，科技普涨。

        ## 1. 市场数据速览

        略...

        ## 4. 持仓预警 (Portfolio Alerts)

        | 持仓标的 | 影响方向 | 触发事件 |
        | :--- | :--- | :--- |
        | NVDA | 🟢利好 | AI 芯片需求超预期 |
        | 8888.HK | 🟢利好 | VLCC 运费飙升 |

        ## 6. 风险与纪律警告

        - **地缘博弈**: 霍尔木兹封锁若迅速缓和，油运运费可能急速回调。
    """)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    return tmp_dir, today, report_path


# ─── Tests for earnings_reminder.py ──────────────────────────────────────────

class TestEarningsReminder:
    """Tests driven by earnings_reminder.py contract:
    - load tickers from holdings_path
    - query yfinance for upcoming earnings dates
    - if any earnings within next 7 days, push Telegram message
    - if no earnings, do NOT push
    """

    def _import(self):
        import importlib
        import scripts.earnings_reminder as m
        importlib.reload(m)
        return m

    def test_get_tickers_from_holdings(self, sample_holdings_json):
        """Should parse ticker list from holdings.json."""
        from earnings_reminder import get_tickers_from_holdings
        tickers = get_tickers_from_holdings(sample_holdings_json)
        assert "NVDA" in tickers
        assert "8888.HK" in tickers

    def test_no_earnings_no_push(self, sample_holdings_json):
        """When no positions have upcoming earnings, no Telegram push."""
        from earnings_reminder import check_and_notify_earnings

        mock_ticker = MagicMock()
        mock_ticker.calendar = None  # no earnings date

        with patch("earnings_reminder.yf.Ticker", return_value=mock_ticker), \
             patch("earnings_reminder.send_telegram_message") as mock_push:
            check_and_notify_earnings(holdings_path=sample_holdings_json)
            mock_push.assert_not_called()

    def test_upcoming_earnings_triggers_push(self, sample_holdings_json):
        """When a position has earnings within 7 days, push a Telegram alert."""
        from earnings_reminder import check_and_notify_earnings
        from datetime import datetime, timedelta
        import pandas as pd

        next_week = datetime.now() + timedelta(days=3)

        mock_ticker_nvda = MagicMock()
        mock_ticker_nvda.calendar = pd.DataFrame(
            {"Earnings Date": [next_week]},
            index=["Earnings Date"]
        ).T

        mock_ticker_other = MagicMock()
        mock_ticker_other.calendar = None

        def side_effect(ticker_sym):
            if "NVDA" in ticker_sym.upper():
                return mock_ticker_nvda
            return mock_ticker_other

        with patch("earnings_reminder.yf.Ticker", side_effect=side_effect), \
             patch("earnings_reminder.send_telegram_message") as mock_push:
            check_and_notify_earnings(holdings_path=sample_holdings_json)
            mock_push.assert_called_once()
            msg = mock_push.call_args[0][0]
            assert "NVDA" in msg
            assert "财报" in msg

    def test_earnings_message_contains_date(self, sample_holdings_json):
        """The Telegram message should include the earnings date."""
        from earnings_reminder import check_and_notify_earnings
        from datetime import datetime, timedelta
        import pandas as pd

        target_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        next_week = datetime.strptime(target_date, "%Y-%m-%d")

        mock_ticker = MagicMock()
        mock_ticker.calendar = pd.DataFrame(
            {"Earnings Date": [next_week]},
            index=["Earnings Date"]
        ).T

        with patch("earnings_reminder.yf.Ticker", return_value=mock_ticker), \
             patch("earnings_reminder.send_telegram_message") as mock_push:
            check_and_notify_earnings(holdings_path=sample_holdings_json)
            msg = mock_push.call_args[0][0]
            assert target_date in msg


# ─── Tests for morning_scan_push.py ──────────────────────────────────────────

class TestMorningScanPush:
    """Tests driven by morning_scan_push.py contract:
    - locate today's market scan report
    - extract summary snippet (header + portfolio alert section)
    - push to Telegram
    - gracefully handle missing report file
    """

    def test_extract_summary_from_report(self, sample_scan_report):
        """Should extract header block and portfolio alert section."""
        from morning_scan_push import extract_summary
        _, today, report_path = sample_scan_report

        summary = extract_summary(report_path)
        assert "市场全景扫描" in summary
        assert "持仓预警" in summary

    def test_summary_within_telegram_limit(self, sample_scan_report):
        """Extracted summary must be ≤ 4000 characters."""
        from morning_scan_push import extract_summary
        _, today, report_path = sample_scan_report

        summary = extract_summary(report_path)
        assert len(summary) <= 4000

    def test_push_sends_message(self, sample_scan_report):
        """Should call send_telegram_message with a non-empty string."""
        from morning_scan_push import run_morning_push
        reports_root, today, _ = sample_scan_report

        with patch("morning_scan_push.send_telegram_message") as mock_push:
            run_morning_push(reports_root=reports_root, date_str=today)
            mock_push.assert_called_once()
            msg = mock_push.call_args[0][0]
            assert len(msg) > 0

    def test_missing_report_does_not_crash(self, tmp_dir):
        """If today's report doesn't exist yet, log and return without crashing."""
        from morning_scan_push import run_morning_push

        with patch("morning_scan_push.send_telegram_message") as mock_push:
            # Pass a date with no corresponding report
            run_morning_push(reports_root=tmp_dir, date_str="99991231")
            mock_push.assert_not_called()  # should NOT push if file missing


# ─── Tests for weekly_position_report.py ─────────────────────────────────────

class TestWeeklyPositionReport:
    """Tests driven by weekly_position_report.py contract:
    - load holdings
    - fetch week performance via yfinance
    - format portfolio health summary with Gemini
    - push to Telegram
    """

    def test_calculate_weekly_pnl(self, sample_holdings_json):
        """Should compute weekly PnL from mock yfinance data."""
        from weekly_position_report import calculate_weekly_pnl
        import pandas as pd

        mock_hist = pd.DataFrame({
            "Close": [100.0, 102.0, 101.0, 105.0, 110.0]
        })
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch("weekly_position_report.yf.Ticker", return_value=mock_ticker):
            pnl = calculate_weekly_pnl(holdings_path=sample_holdings_json)

        assert isinstance(pnl, dict)
        assert "NVDA" in pnl
        # 10% gain from 100 to 110
        assert abs(pnl["NVDA"] - 10.0) < 0.5

    def test_pnl_handles_no_data(self, sample_holdings_json):
        """If yfinance returns an empty DataFrame, PnL for that ticker is None."""
        from weekly_position_report import calculate_weekly_pnl
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("weekly_position_report.yf.Ticker", return_value=mock_ticker):
            pnl = calculate_weekly_pnl(holdings_path=sample_holdings_json)

        for ticker in pnl:
            assert pnl[ticker] is None

    def test_generate_summary_calls_gemini(self, sample_holdings_json):
        """Should call Gemini API with context and return a non-empty string."""
        from weekly_position_report import generate_portfolio_summary

        mock_response = MagicMock()
        mock_response.text = "📊 本周持仓健康度报告：组合表现稳健，NVDA 本周大涨10%。"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("weekly_position_report.genai.Client", return_value=mock_client), \
             patch("weekly_position_report._genai_client", mock_client):
            summary = generate_portfolio_summary(
                pnl_data={"NVDA": 10.0, "8888.HK": 5.2}
            )

        assert len(summary) > 0
        assert "NVDA" in summary or "持仓" in summary

    def test_run_weekly_report_pushes_message(self, sample_holdings_json):
        """Full integration: should call send_telegram_message once."""
        from weekly_position_report import run_weekly_report
        import pandas as pd

        mock_hist = pd.DataFrame({"Close": [100.0, 103.0, 105.0, 107.0, 110.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        mock_response = MagicMock()
        mock_response.text = "本周组合稳健，油运标的大涨。"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("weekly_position_report.yf.Ticker", return_value=mock_ticker), \
             patch("weekly_position_report._genai_client", mock_client), \
             patch("weekly_position_report.send_telegram_message") as mock_push:
            run_weekly_report(holdings_path=sample_holdings_json)
            mock_push.assert_called_once()
            msg = mock_push.call_args[0][0]
            assert len(msg) > 0
