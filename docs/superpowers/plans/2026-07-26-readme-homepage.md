# Research README Homepage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current `README.md` with a polished, accurate project homepage that explains AlphaSystem's purpose, architecture, features, installation, usage, roadmap, and contribution process.

**Architecture:** Keep `README.md` as the single landing page and arrange it in two reading layers: a concise value proposition and working quick start first, then implementation-backed architecture and contributor detail. Treat the current default-branch code and configuration as authoritative when existing documents disagree.

**Tech Stack:** Markdown, Python 3, pytest, Gemini via `google-genai`, OpenAI-compatible providers via `openai`, optional Node.js/Playwright integration.

## Global Constraints

- Write the homepage primarily in Simplified Chinese while preserving established English technical names.
- Modify only `README.md` during implementation.
- Do not claim a license, screenshot, benchmark, stability guarantee, or unimplemented capability.
- Run commands from the repository root; do not prefix local paths with the nonexistent `research/` directory.
- Keep the Eyes–Brain–Memory architecture as the central system explanation.
- Describe trading execution as an optional guarded subsystem, not a safety guarantee or default live-trading mode.
- Clearly state that the project is for research and engineering experimentation and does not constitute investment advice.
- Link to existing detailed documents instead of duplicating their full content.

---

### Task 1: Rewrite the project homepage

**Files:**
- Modify: `README.md`
- Reference: `research_cli.py`
- Reference: `.env.example`
- Reference: `requirements.txt`
- Reference: `package.json`
- Reference: `core/llm_client.py`
- Reference: `core/llm_providers.py`
- Reference: `services/datahub/sources/`
- Reference: `services/execution/`
- Reference: `services/portfolio/`
- Reference: `services/trigger/`
- Reference: `.agent/workflows/`
- Reference: `CHANGELOG.md`
- Reference: `Development_Roadmap_Summary.md`
- Reference: `next phase.md`

**Interfaces:**
- Consumes: Repository-root commands, the 17 workflow definitions, supported provider names `gemini`, `openai`, `openrouter`, and `qwen`, and the existing example configuration files.
- Produces: A standalone `README.md` that is the canonical onboarding page and links readers to deeper documentation.

- [ ] **Step 1: Record the current homepage defects**

Run:

```bash
rg -n 'research/requirements|cd research|python research/|贡献|Roadmap|路线图|不构成投资建议' README.md
```

Expected: the old homepage contains root-path assumptions such as `research/requirements.txt` or `cd research`, and does not contain complete roadmap, contribution, and investment-risk sections.

- [ ] **Step 2: Confirm the implementation-backed command and configuration surface**

Run:

```bash
python research_cli.py --help
find .agent/workflows -maxdepth 1 -type f -name '*.md' -print | sort
rg -n 'LLM_PROVIDER|GEMINI_API_KEY|OPENAI_API_KEY|OPENROUTER_API_KEY|QWEN_API_KEY|DASHSCOPE_API_KEY' .env.example core
```

Expected: CLI help exits successfully; the repository contains workflow files for `add`, `buy`, `core`, `deep`, `lead`, `macro`, `optimize`, `option`, `position`, `quick`, `rethink`, `scan`, `sell`, `theme`, `update`, `value`, and `verify`; configuration confirms the four supported provider modes and their key variables.

- [ ] **Step 3: Replace `README.md` with the approved two-layer information architecture**

Write these sections in this order:

```markdown
# AlphaSystem
> One-sentence positioning for an auditable, reusable AI investment-research workbench.

Project-status and non-investment-advice notice

## Why AlphaSystem
## Core capabilities
## Architecture
## Quick start
### 1. Clone and create a virtual environment
### 2. Install Python dependencies
### 3. Configure environment variables
### 4. Prepare optional personal configuration
### 5. Inspect CLI help and run a workflow
## Usage
## Research workflows
## Configuration
### LLM providers
### Data sources and optional integrations
## Repository structure
## Security, privacy, and execution boundaries
## Testing
## Roadmap
## Contributing
## Documentation
## Acknowledgements
```

Use repository-root commands:

```bash
git clone https://github.com/zx2592/Research.git
cd Research
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cp Config/holdings.example.json Config/holdings.json
cp Memory_Layer/Investment_Persona.example.md Memory_Layer/Investment_Persona.md
python research_cli.py --help
python research_cli.py scan
python research_cli.py deep NVDA
```

State that Windows activation uses `.venv\Scripts\activate`. Explain that API requirements vary by selected provider and workflow/data source, instead of claiming both Gemini and Tavily are universally mandatory.

Summarize all 17 user-facing workflows in compact grouped tables. Exclude `timezone-context.md` because it is supporting workflow context, not a user-facing command.

Describe the data flow as:

```text
CLI / Telegram / Scheduler
          ↓
Eyes: DataHub + market/search/social sources + cache
          ↓
Brain: workflow SOP + LLM provider + ToolBus/evidence
          ↓
Memory: reports + knowledge base + portfolio/event records
```

Describe the three optional supporting subsystems separately:

- `services/execution/`: kill switch, guard chain, wallet, adapter, and ledger flow;
- `services/portfolio/`: SQLite-backed event ledger, snapshots, importers, and health calculations;
- `services/trigger/`: scheduled, price-move, and earnings-related monitoring and execution.

Link to `SYSTEM.md`, `COMMANDS.md`, `System_Manual.md`, `Phase7_Guide.md`, `DEPLOY_MAC_V2.2.md`, `CHANGELOG.md`, and `Development_Roadmap_Summary.md`.

- [ ] **Step 4: Check the homepage structure and stale path removal**

Run:

```bash
rg -n '^## (Why AlphaSystem|核心能力|系统架构|快速开始|使用方式|研究工作流|配置|项目结构|安全、隐私与执行边界|测试|路线图|贡献|文档|致谢)' README.md
if rg -n 'pip install -r research/requirements\.txt|cd research|python research/' README.md; then exit 1; fi
```

Expected: all intended major sections are present and the stale `research/` command paths are absent.

- [ ] **Step 5: Commit the homepage rewrite**

Run:

```bash
git add README.md
git commit -m "docs: revamp project homepage"
```

Expected: one commit containing only the `README.md` rewrite.

---

### Task 2: Validate the commit-ready README

**Files:**
- Verify: `README.md`
- Verify: all repository-relative paths linked from `README.md`

**Interfaces:**
- Consumes: The rewritten `README.md` from Task 1.
- Produces: Evidence that the Markdown is internally consistent, commands are discoverable, repository links resolve, and the repository test suite still passes.

- [ ] **Step 1: Check whitespace and Markdown link targets**

Run:

```bash
git diff HEAD^ --check
python - <<'PY'
from pathlib import Path
import re

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
missing = []
for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
    if target.startswith(("http://", "https://", "#", "mailto:")):
        continue
    path = target.split("#", 1)[0]
    if path and not Path(path).exists():
        missing.append(target)
if missing:
    raise SystemExit("Missing local link targets: " + ", ".join(missing))
print("All repository-relative README links resolve.")
PY
```

Expected: no whitespace errors and the script prints `All repository-relative README links resolve.`

- [ ] **Step 2: Verify workflow count and important safety language**

Run:

```bash
for command in scan lead theme core deep value quick update verify buy sell option macro position optimize rethink add; do
  rg -q "\`/$command\`" README.md || { echo "Missing workflow: $command"; exit 1; }
done
rg -n '不构成投资建议|KillSwitch|GuardChain|个人数据|\.gitignore' README.md
```

Expected: all 17 workflow names are present and the safety/privacy language is found.

- [ ] **Step 3: Verify CLI help**

Run:

```bash
python research_cli.py --help
```

Expected: exit code 0 and help output listing the supported CLI commands.

- [ ] **Step 4: Run the repository test suite**

Run:

```bash
python -m pytest tests/
```

Expected: exit code 0. Tests that require optional credentials must remain skipped or mocked according to the existing test configuration.

- [ ] **Step 5: Review the final change scope**

Run:

```bash
git status --short --branch
git show --stat --oneline HEAD
git diff HEAD^ -- README.md
```

Expected: the homepage commit modifies only `README.md`; the local branch may also be ahead by the previously approved design and plan documentation commits, with no uncommitted implementation changes.
