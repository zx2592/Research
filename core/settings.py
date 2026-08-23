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


class WorkflowBudgetSettings:
    """每个 workflow 的联网取证预算——单一真理源。

    此前同一个数字散落三处且互相矛盾：workflow 正文各写各的（scan 28 / theme 8 /
    quick 1）、SYSTEM.md 写「每个任务最多 8 次」、SearchSettings.max_searches
    无人消费。现在预算只在这里声明，由 ToolFactory 在工具层强制、由 WorkflowRunner
    注入提示词，提示词与执行同源，改一处即全局生效。

    单位是「取证点数」而非严格的搜索次数：search_web / browser_fetch / drill_source
    各计 1 点，learn_source 计 2 点（生成适配器代价更高）。
    """

    # 逐 workflow 上限。依据是各 workflow 正文原本声明的搜索次数，
    # 未声明的按任务重量归档到默认值。
    PER_WORKFLOW: dict[str, int] = {
        "scan": 28,      # 市场全景：宏观 4 + 持仓 2 + 市场 22
        "deep": 14,      # 深研：Phase B0 高密度聚合 + 分维度补证
        "value": 12,
        "buy": 10,       # 决策类：需要交叉验证与反方取证
        "sell": 10,
        "lead": 10,
        "theme": 8,
        "position": 8,
        "core": 6,
        "update": 6,
        "verify": 6,     # 事实核查靠一手源交叉，次数不高但不能压到 1
        "option": 6,
        "macro": 4,
        "optimize": 4,   # Step0-2 不联网，仅 Step3 定性
        "rethink": 3,
        "quick": 2,      # 事件快评：1 次聚合查询 + 1 次容错重试
        "add": 0,        # 知识卡片留存：纯本地整理，不应联网
    }

    DEFAULT: int = config.get_int("SEARCH_MAX_PER_WORKFLOW", 8)

    @classmethod
    def for_workflow(cls, name: str) -> int:
        """返回该 workflow 的取证预算。

        环境变量 `SEARCH_BUDGET_<WORKFLOW>`（如 SEARCH_BUDGET_SCAN）可单独覆盖，
        便于临时放宽某个流程而不改代码。
        """
        key = (name or "").strip().lower()
        override = config.get_int(f"SEARCH_BUDGET_{key.upper()}", -1)
        if override >= 0:
            return override
        return cls.PER_WORKFLOW.get(key, cls.DEFAULT)


class WorkflowStageSettings:
    """多阶段工作流定义（progressive disclosure + 上下文隔离）。

    单阶段工作流把「研究过程 + 报告骨架 + 契约」一次性塞进一个 system instruction，
    再跑最多 15 轮工具循环——每一轮都把这一整坨重新发一遍。深研类工作流因此最贵。

    拆成阶段后有两处收益：
    1. 每个阶段只装自己那一半（研究阶段不需要报告骨架，组装阶段不需要搜索纪律）；
    2. 组装阶段不再继承研究阶段的工具调用历史，上下文从「一路累积」变成「只带结论」。

    `contracts` 指定该阶段加载哪几份公共契约（按文件名前缀）：
    00=报告结构 10=证据标准 20=质量门禁。
    """

    # (阶段名, 阶段指令文件, 加载的契约, 是否用 Pro)
    STAGES: dict[str, tuple[tuple[str, str, tuple[str, ...], bool], ...]] = {
        "deep": (
            ("research", "stages/deep-1-research.md", ("00", "10"), True),
            ("assemble", "stages/deep-2-assemble.md", ("00", "20"), False),
            ("critique", "stages/critique.md", ("20",), False),
        ),
        "value": (
            ("research", "stages/value-1-research.md", ("00", "10"), True),
            ("assemble", "stages/value-2-assemble.md", ("00", "20"), False),
            ("critique", "stages/critique.md", ("20",), False),
        ),
    }

    @classmethod
    def stages_for(cls, name: str) -> tuple:
        """返回该 workflow 的阶段定义；单阶段工作流返回空元组。

        `WORKFLOW_STAGES_DISABLED=1` 可整体退回单阶段模式，便于对照排查。
        """
        if config.get_bool("WORKFLOW_STAGES_DISABLED", False):
            return ()
        return cls.STAGES.get((name or "").strip().lower(), ())

    @classmethod
    def is_staged(cls, name: str) -> bool:
        return bool(cls.stages_for(name))


class ModelRoutingSettings:
    """模型分档路由。

    高后果任务（触碰真实下单的 buy/sell、建档级深研 deep/value）走 Pro，
    其余走 Flash。一次 Pro 调用的成本增量远低于一次错误交易。
    """

    _DEFAULT_PRO = ("deep", "value", "buy", "sell")

    @classmethod
    def pro_workflows(cls) -> frozenset[str]:
        """Pro 档 workflow 集合，可用 PRO_WORKFLOWS 环境变量（逗号分隔）整体覆盖。"""
        raw = config.get("PRO_WORKFLOWS", "")
        if raw.strip():
            return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())
        return frozenset(cls._DEFAULT_PRO)


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
workflow_budget = WorkflowBudgetSettings()
model_routing = ModelRoutingSettings()
workflow_stages = WorkflowStageSettings()
trigger = TriggerSettings()
bot = BotSettings()
tool_loop = ToolLoopSettings()
