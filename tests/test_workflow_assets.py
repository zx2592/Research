"""Workflow 资产完整性检查。

Progressive disclosure 的失败模式是安静的：主文件让模型去 `read_file` 一个
不存在的路径，模型读不到就凭记忆写，报告结构悄悄跑偏。这里把「指针指向的文件
必须存在」变成测试。
"""
import re
from pathlib import Path

import pytest

from core import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = PROJECT_ROOT / ".agent" / "workflows"

# workflow 正文里以反引号引用的仓库内路径。
# 只匹配带目录分隔符的相对路径——裸文件名（`KB_INDEX.md`）是行文提及，不是指针。
REFERENCE_PATTERN = re.compile(r"`([A-Za-z_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.\[\]-]+)+\.(?:md|py|json))`")

# 输出路径模板与 gitignore 的用户文件不是断链，跳过。
PLACEHOLDER_MARKERS = ("YYYYMMDD", "[Ticker]", "[YYYYMMDD]", "{ticker}")
GITIGNORED_PREFIXES = (
    "Config/",                  # 从 .example 复制而来
    "Memory_Layer/",            # 个人知识库与画像
    "Reports/",                 # 运行时产出
)


def _workflow_files():
    return sorted(p for p in WORKFLOW_DIR.glob("*.md"))


class TestStageFilesExist:
    @pytest.mark.parametrize("workflow", sorted(settings.workflow_stages.STAGES))
    def test_every_declared_stage_file_exists(self, workflow):
        for stage_name, rel_path, _, _ in settings.workflow_stages.STAGES[workflow]:
            path = WORKFLOW_DIR / rel_path
            assert path.is_file(), f"{workflow}/{stage_name} 指向不存在的阶段文件: {rel_path}"
            assert path.read_text(encoding="utf-8").strip(), f"{rel_path} 是空文件"

    def test_staged_workflows_have_a_main_file(self):
        for workflow in settings.workflow_stages.STAGES:
            assert (WORKFLOW_DIR / f"{workflow}.md").is_file()


def _all_instruction_files():
    """主文件、阶段文件、参考文件——三者都会被送进提示词，指针都得能解析。"""
    return sorted(
        list(WORKFLOW_DIR.glob("*.md"))
        + list(WORKFLOW_DIR.glob("stages/*.md"))
        + list(WORKFLOW_DIR.glob("references/*.md"))
        + list(WORKFLOW_DIR.glob("common/*.md"))
    )


def _is_checkable(rel: str) -> bool:
    if any(marker in rel for marker in PLACEHOLDER_MARKERS):
        return False
    return not rel.startswith(GITIGNORED_PREFIXES)


class TestReferencePointersResolve:
    """断链是安静的失败：模型读不到就凭记忆写，结构悄悄跑偏。

    这里检查全仓库路径而不只是 `.agent/workflows/` 下的——
    `Workflow_Layer/Templates/...` 那次断链正是因为只查后者而漏掉。
    """

    @pytest.mark.parametrize("instruction_file", _all_instruction_files(), ids=lambda p: p.name)
    def test_referenced_files_exist(self, instruction_file):
        text = instruction_file.read_text(encoding="utf-8")
        for rel in REFERENCE_PATTERN.findall(text):
            if not _is_checkable(rel):
                continue
            # 指针可能相对仓库根，也可能相对 .agent/workflows/（如 `common/00-...md`）
            candidates = (PROJECT_ROOT / rel, WORKFLOW_DIR / rel)
            assert any(c.exists() for c in candidates), (
                f"{instruction_file.name} 引用了不存在的路径: {rel}"
            )

    def test_the_pattern_would_have_caught_the_known_regression(self, tmp_path):
        # 曾经真实存在过的断链写法，必须被这条规则抓到
        sample = "见 `Workflow_Layer/Templates/Template_A_Quality_Compounder.md`。"
        found = REFERENCE_PATTERN.findall(sample)
        assert found == ["Workflow_Layer/Templates/Template_A_Quality_Compounder.md"]
        assert _is_checkable(found[0])
        assert not (PROJECT_ROOT / found[0]).exists()

    def test_output_path_templates_are_not_treated_as_pointers(self):
        assert not _is_checkable("Reports/deepdive/[YYYYMMDD]_[Ticker]_Deep.md")
        assert not _is_checkable("Config/holdings.json")


class TestSlimMainFiles:
    """主文件在每个阶段都会被加载，必须保持精简。"""

    # 已做 progressive disclosure 的工作流，主文件不应再包含完整报告骨架
    SPLIT_WORKFLOWS = {"deep", "value", "scan", "buy", "position", "sell", "theme"}

    @pytest.mark.parametrize("name", sorted(SPLIT_WORKFLOWS))
    def test_report_skeleton_is_not_inline(self, name):
        text = (WORKFLOW_DIR / f"{name}.md").read_text(encoding="utf-8")
        # 报告骨架的标志：内嵌的 markdown 代码块 + 质量自检章节模板
        assert "## 质量自检" not in text, f"{name}.md 仍内联着报告骨架，应下沉到 references/ 或 stages/"

    @pytest.mark.parametrize("name", sorted(SPLIT_WORKFLOWS))
    def test_main_file_stays_small(self, name):
        size = (WORKFLOW_DIR / f"{name}.md").stat().st_size
        assert size < 20000, f"{name}.md 有 {size} 字节，超出主文件预算"
