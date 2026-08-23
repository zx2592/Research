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

# 主文件里引用参考文件的写法：`.agent/workflows/references/xxx.md`
REFERENCE_PATTERN = re.compile(r"`(\.agent/workflows/[a-z0-9/_-]+\.md)`")


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


class TestReferencePointersResolve:
    @pytest.mark.parametrize("workflow_file", _workflow_files(), ids=lambda p: p.name)
    def test_referenced_files_exist(self, workflow_file):
        text = workflow_file.read_text(encoding="utf-8")
        for rel in REFERENCE_PATTERN.findall(text):
            target = PROJECT_ROOT / rel
            assert target.is_file(), f"{workflow_file.name} 引用了不存在的文件: {rel}"


class TestSlimMainFiles:
    """主文件在每个阶段都会被加载，必须保持精简。"""

    # 已做 progressive disclosure 的工作流，主文件不应再包含完整报告骨架
    SPLIT_WORKFLOWS = {"deep", "value", "scan", "buy"}

    @pytest.mark.parametrize("name", sorted(SPLIT_WORKFLOWS))
    def test_report_skeleton_is_not_inline(self, name):
        text = (WORKFLOW_DIR / f"{name}.md").read_text(encoding="utf-8")
        # 报告骨架的标志：内嵌的 markdown 代码块 + 质量自检章节模板
        assert "## 质量自检" not in text, f"{name}.md 仍内联着报告骨架，应下沉到 references/ 或 stages/"

    @pytest.mark.parametrize("name", sorted(SPLIT_WORKFLOWS))
    def test_main_file_stays_small(self, name):
        size = (WORKFLOW_DIR / f"{name}.md").stat().st_size
        assert size < 20000, f"{name}.md 有 {size} 字节，超出主文件预算"
