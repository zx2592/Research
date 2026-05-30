"""
业务参数配置中心。环境变量 > 默认值。

所有业务硬编码数值集中在此模块，消费端通过 settings.xxx 读取。
运行时可通过 .env 或环境变量覆盖默认值，无需改代码。
"""
from core import config


class ExecutionSettings:
    max_position_pct: float = config.get_float("GUARD_MAX_POSITION_PCT", 15.0)
    cooldown_hours: float = config.get_float("GUARD_COOLDOWN_HOURS", 24.0)
    reverse_cooldown_days: int = config.get_int("GUARD_REVERSE_COOLDOWN_DAYS", 30)
    default_confidence: float = config.get_float("TRADE_DEFAULT_CONFIDENCE", 0.9)
    preview_confidence: float = config.get_float("TRADE_PREVIEW_CONFIDENCE", 1.0)


class SearchSettings:
    max_searches: int = config.get_int("SEARCH_MAX_PER_WORKFLOW", 8)
    budget_max: int = config.get_int("SEARCH_BUDGET_MAX", 30)
    content_truncation: int = config.get_int("SEARCH_CONTENT_TRUNCATION", 300)
    quota_warn_pct: int = config.get_int("SEARCH_QUOTA_WARN_PCT", 80)


class TriggerSettings:
    morning_scan_cooldown: int = config.get_int("TRIGGER_MORNING_SCAN_COOLDOWN", 6 * 3600)
    position_review_cooldown: int = config.get_int("TRIGGER_POSITION_REVIEW_COOLDOWN", 24 * 3600)
    price_move_threshold: float = config.get_float("TRIGGER_PRICE_MOVE_PCT", 3.5)
    price_move_cooldown: int = config.get_int("TRIGGER_PRICE_MOVE_COOLDOWN", 4 * 3600)
    earnings_cooldown: int = config.get_int("TRIGGER_EARNINGS_COOLDOWN", 24 * 3600)
    earnings_window_days: int = config.get_int("TRIGGER_EARNINGS_WINDOW_DAYS", 7)


class BotSettings:
    max_message_length: int = config.get_int("BOT_MAX_MESSAGE_LENGTH", 4000)


class ToolLoopSettings:
    max_iterations: int = config.get_int("TOOL_LOOP_MAX_ITERATIONS", 15)


# Singletons
execution = ExecutionSettings()
search = SearchSettings()
trigger = TriggerSettings()
bot = BotSettings()
tool_loop = ToolLoopSettings()
