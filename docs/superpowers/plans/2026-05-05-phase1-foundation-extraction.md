# Phase 1: aios-foundation Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract eight pure-foundation Python modules from the monorepo into a new `aios-foundation` package, publish to GitHub at `aios-kit/aios-foundation`, tag v0.1.0, and wire the monorepo to install it via pip from the git tag — without breaking the running Clymb Co daemon or any test.

**Architecture:** New repo `aios-kit/aios-foundation` ships a Python package that uses PEP 420 implicit namespace packages so `aios.foundation.*` and `aios.memory.*` install into the same `aios` namespace as the monorepo's remaining `aios.daemon.*` and `aios.registry`. Migration is lift-and-shift; module contents stay byte-identical. Tests come along with each module. Monorepo swaps its local `aios/foundation/` and `aios/memory/` for a pip dependency on the tagged package; full test suite + daemon smoke test gate the cutover.

**Tech Stack:** Python 3.11, uv (dep manager), pytest, GitHub (gh CLI), git tags for versioning, PEP 420 namespace packages.

**What is NOT in Phase 1:**
- `aios/foundation/registry.py` (depends on `systems.scout.supabase_backends`; belongs in deployment template, Phase 3)
- `aios/registry.py` (depends on `systems.base`; defer to Phase 2 with system base class)
- `aios/daemon/*` (deployment runtime; Phase 3)

---

## File Structure

### New repo `aios-kit/aios-foundation` will create

```
aios-foundation/
├── pyproject.toml                          (package config, deps, build system)
├── README.md                                (overview, install, usage)
├── RUNBOOK.md                               (ops: how to upgrade, common issues)
├── docs/
│   └── public-api.md                        (one-page API surface)
├── src/
│   └── aios/
│       ├── foundation/
│       │   ├── __init__.py                  (public API exports)
│       │   ├── autonomy.py
│       │   ├── decision_logger.py
│       │   ├── embedder.py
│       │   ├── employee_memory.py
│       │   ├── feedback_loop.py
│       │   ├── knowledge.py
│       │   └── pattern_matcher.py
│       └── memory/
│           ├── __init__.py
│           └── store.py
├── tests/
│   ├── __init__.py
│   ├── test_foundation/
│   │   ├── __init__.py
│   │   ├── test_autonomy.py
│   │   ├── test_decision_logger.py
│   │   ├── test_embedder.py
│   │   ├── test_employee_memory.py
│   │   ├── test_feedback_loop.py
│   │   ├── test_knowledge.py
│   │   └── test_pattern_matcher.py
│   └── test_memory/
│       ├── __init__.py
│       └── test_store.py
├── skills/
│   ├── meta/
│   │   ├── README.md
│   │   └── validate-writing.md
│   └── playbooks/
│       ├── README.md
│       ├── build-cloudflare-protected-scraper.md
│       ├── configure-trigify-monitors.md
│       └── discover-trigify-leads.md
├── rules/
│   └── global-writing-guardrails.md
├── .gitignore
└── .github/
    └── workflows/
        └── tests.yml                        (run pytest on push)
```

**Key choice — `src/` layout:** Keeps the package importable only after install (catches missing-dep bugs during test). Avoids namespace shadowing between repo root and installed package.

**Key choice — no `src/aios/__init__.py`:** Makes `aios` a PEP 420 implicit namespace package. The monorepo's existing `aios/__init__.py` will be deleted in Task 8 to match. Both packages then contribute to the same logical `aios` namespace at runtime.

### Monorepo will modify

- [pyproject.toml](pyproject.toml) — add `aios-foundation` as a git-tag dependency
- [aios/__init__.py](aios/__init__.py) — DELETE (convert `aios` to namespace package)
- [aios/foundation/](aios/foundation/) — DELETE (now installed from pip)
- [aios/memory/](aios/memory/) — DELETE (now installed from pip)
- [skills/meta/](skills/meta/) — DELETE (moved to foundation)
- [skills/playbooks/](skills/playbooks/) — DELETE (moved to foundation)
- [rules/global-writing-guardrails.md](rules/global-writing-guardrails.md) — DELETE (moved to foundation)

---

## Task 1: Bootstrap `aios-foundation` repo skeleton

**Files:**
- Create: `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation/pyproject.toml`
- Create: `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation/README.md`
- Create: `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation/.gitignore`
- Create: `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation/src/aios/foundation/__init__.py`
- Create: `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation/src/aios/memory/__init__.py`
- Create: `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation/tests/__init__.py`

- [ ] **Step 1: Create the `aios-kit` GitHub org**

```bash
# Confirm org doesn't exist yet
gh api orgs/aios-kit 2>&1 | grep -q "Not Found" && echo "OK to create" || echo "Already exists"
```

Expected: `OK to create` (if existing, skip to Step 2). To create the org, use the GitHub web UI (gh cli does not create orgs). Open https://github.com/account/organizations/new — choose Free plan, name `aios-kit`, contact email = operator's primary GitHub email.

- [ ] **Step 2: Verify the org exists and you have admin access**

```bash
gh api orgs/aios-kit --jq '.login + " — " + .plan.name'
```

Expected: `aios-kit — free` (or similar). If `Not Found`, return to Step 1.

- [ ] **Step 3: Create the empty `aios-foundation` repo on GitHub**

```bash
gh repo create aios-kit/aios-foundation \
  --private \
  --description "Shared core for the AIOS productised kit: autonomy gates, decision logger, employee memory, knowledge embedder, feedback loop, validators." \
  --add-readme=false
```

Expected: `https://github.com/aios-kit/aios-foundation`

- [ ] **Step 4: Clone the new repo locally**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS
gh repo clone aios-kit/aios-foundation
cd aios-foundation
```

Expected: working directory at `~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation`, branch `main`.

- [ ] **Step 5: Create directory skeleton**

```bash
mkdir -p src/aios/foundation src/aios/memory tests/test_foundation tests/test_memory skills/meta skills/playbooks rules docs .github/workflows
```

- [ ] **Step 6: Write `pyproject.toml`**

Path: `aios-foundation/pyproject.toml`

```toml
[project]
name = "aios-foundation"
version = "0.1.0"
description = "Shared core for the AIOS productised kit"
requires-python = ">=3.11"
license = { text = "Proprietary" }
authors = [
    { name = "Kirsten" },
]
dependencies = [
    # Anthropic SDK (used by some foundation modules indirectly via tooling)
    "anthropic>=0.34.0",

    # Embeddings
    "voyageai>=0.2.3",

    # Database
    "supabase>=2.7.0",
    "asyncpg>=0.29.0",
    "pgvector>=0.3.0",

    # Config
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
    "python-dotenv>=1.0.0",

    # Logging
    "structlog>=24.0.0",

    # Utilities
    "tenacity>=8.5.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/aios"]

[tool.hatch.build]
# Include the markdown skills + rules in sdist for downstream consumers
include = [
    "src/**",
    "skills/**",
    "rules/**",
    "README.md",
    "RUNBOOK.md",
    "docs/**",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 7: Write `.gitignore`**

Path: `aios-foundation/.gitignore`

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/

# Tests
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# Editors
.vscode/
.idea/
*.swp
.DS_Store

# Env
.env
.env.local
```

- [ ] **Step 8: Create empty `__init__.py` files for the namespace setup**

Path: `aios-foundation/src/aios/foundation/__init__.py`

```python
```

(Empty file. Public API exports get added in Task 2.)

Path: `aios-foundation/src/aios/memory/__init__.py`

```python
```

(Empty file. Filled in Task 3.)

Path: `aios-foundation/tests/__init__.py`

```python
```

Path: `aios-foundation/tests/test_foundation/__init__.py`

```python
```

Path: `aios-foundation/tests/test_memory/__init__.py`

```python
```

**Important:** Do NOT create `aios-foundation/src/aios/__init__.py`. The absence of that file is what makes `aios` a PEP 420 namespace package.

- [ ] **Step 9: Write a placeholder README**

Path: `aios-foundation/README.md`

```markdown
# aios-foundation

Shared core for the AIOS productised kit. See [docs/public-api.md](docs/public-api.md).

## Install

```bash
pip install git+https://github.com/aios-kit/aios-foundation.git@v0.1.0
```

## Modules

- `aios.foundation.autonomy` — autonomy gating (suggest → draft → act_notify → autonomous)
- `aios.foundation.decision_logger` — decision_log writer with outcome backfill
- `aios.foundation.embedder` — Voyage AI 1024-dim embedder with cost tracking
- `aios.foundation.employee_memory` — per-employee semantic memory store
- `aios.foundation.feedback_loop` — learning_events emitter
- `aios.foundation.knowledge` — knowledge_base read API
- `aios.foundation.pattern_matcher` — vector pattern match
- `aios.memory.store` — general-purpose embedded memory store

## Versioning

Tagged releases via git. Pin in dependent repos:

```toml
dependencies = [
    "aios-foundation @ git+https://github.com/aios-kit/aios-foundation.git@v0.1.0",
]
```

See [RUNBOOK.md](RUNBOOK.md) for upgrade procedure.
```

- [ ] **Step 10: Install the package locally and verify the namespace works**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
python -c "import aios.foundation; import aios.memory; print('namespace OK')"
```

Expected: `namespace OK`. If `ModuleNotFoundError`, check that `pyproject.toml` `[tool.hatch.build.targets.wheel]` points to `src/aios` and that no `src/aios/__init__.py` was accidentally created.

- [ ] **Step 11: Commit the skeleton**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
git add pyproject.toml README.md .gitignore src tests
git commit -m "chore: bootstrap aios-foundation repo skeleton"
git push origin main
```

Expected: push succeeds, repo on GitHub shows initial commit.

---

## Task 2: Migrate the seven `aios.foundation.*` modules

**Files:**
- Copy from monorepo `aios/foundation/{autonomy,decision_logger,embedder,employee_memory,feedback_loop,knowledge,pattern_matcher}.py` to `aios-foundation/src/aios/foundation/`
- Copy from monorepo `tests/test_foundation/test_*.py` to `aios-foundation/tests/test_foundation/`
- Modify: `aios-foundation/src/aios/foundation/__init__.py` (add public API exports)

- [ ] **Step 1: Copy the seven foundation modules byte-for-byte**

```bash
SRC=~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
DST=~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
cp "$SRC/aios/foundation/autonomy.py" "$DST/src/aios/foundation/autonomy.py"
cp "$SRC/aios/foundation/decision_logger.py" "$DST/src/aios/foundation/decision_logger.py"
cp "$SRC/aios/foundation/embedder.py" "$DST/src/aios/foundation/embedder.py"
cp "$SRC/aios/foundation/employee_memory.py" "$DST/src/aios/foundation/employee_memory.py"
cp "$SRC/aios/foundation/feedback_loop.py" "$DST/src/aios/foundation/feedback_loop.py"
cp "$SRC/aios/foundation/knowledge.py" "$DST/src/aios/foundation/knowledge.py"
cp "$SRC/aios/foundation/pattern_matcher.py" "$DST/src/aios/foundation/pattern_matcher.py"
```

Verify:

```bash
ls "$DST/src/aios/foundation/"
```

Expected: 8 files (`__init__.py` + 7 module files).

- [ ] **Step 2: Copy the seven foundation tests byte-for-byte**

```bash
cp "$SRC/tests/test_foundation/test_autonomy.py" "$DST/tests/test_foundation/test_autonomy.py"
cp "$SRC/tests/test_foundation/test_decision_logger.py" "$DST/tests/test_foundation/test_decision_logger.py"
cp "$SRC/tests/test_foundation/test_embedder.py" "$DST/tests/test_foundation/test_embedder.py"
cp "$SRC/tests/test_foundation/test_employee_memory.py" "$DST/tests/test_foundation/test_employee_memory.py"
cp "$SRC/tests/test_foundation/test_feedback_loop.py" "$DST/tests/test_foundation/test_feedback_loop.py"
cp "$SRC/tests/test_foundation/test_knowledge.py" "$DST/tests/test_foundation/test_knowledge.py"
cp "$SRC/tests/test_foundation/test_pattern_matcher.py" "$DST/tests/test_foundation/test_pattern_matcher.py"
```

Verify:

```bash
ls "$DST/tests/test_foundation/"
```

Expected: 8 files (`__init__.py` + 7 test files).

- [ ] **Step 3: Run the foundation test suite in isolation to verify imports resolve**

```bash
cd "$DST"
source .venv/bin/activate
pytest tests/test_foundation/ -v 2>&1 | tail -40
```

Expected: All tests collected. Any failures here indicate either:
- A missing dep in `pyproject.toml` (look for `ImportError`/`ModuleNotFoundError`)
- A test that depends on monorepo-only modules (e.g. imports from `systems.*` or `api.*`) — those tests should be flagged for Phase 2 migration, not foundation. If found, paste the failing test name and ask the operator before deleting; do NOT auto-skip.
- A fixture file referenced in the tests that wasn't copied — check `tests/conftest.py` in the monorepo.

If `conftest.py` exists in `$SRC/tests/test_foundation/`, copy it:

```bash
[ -f "$SRC/tests/test_foundation/conftest.py" ] && cp "$SRC/tests/test_foundation/conftest.py" "$DST/tests/test_foundation/conftest.py"
[ -f "$SRC/tests/conftest.py" ] && cp "$SRC/tests/conftest.py" "$DST/tests/conftest.py"
```

Then re-run pytest. If still failing on monorepo-only imports in a `conftest.py`, edit that conftest to remove only the monorepo-specific fixtures (and document which fixtures got removed in the commit message).

- [ ] **Step 4: Wire the public API in `__init__.py`**

Path: `aios-foundation/src/aios/foundation/__init__.py`

```python
"""AIOS foundation: shared primitives for autonomy, decisions, memory, embeddings, and feedback loops.

Every system imports from here. Never bypass.
"""
from aios.foundation.autonomy import AutonomyGate
from aios.foundation.decision_logger import DecisionLogger
from aios.foundation.embedder import EmbedderCostExceeded, VoyageEmbedder
from aios.foundation.employee_memory import EmployeeMemory, EmployeeMemoryPgVector, Memory
from aios.foundation.feedback_loop import FeedbackLoop
from aios.foundation.knowledge import KnowledgeStore
from aios.foundation.pattern_matcher import PatternMatcher

__all__ = [
    "AutonomyGate",
    "DecisionLogger",
    "EmbedderCostExceeded",
    "EmployeeMemory",
    "EmployeeMemoryPgVector",
    "FeedbackLoop",
    "KnowledgeStore",
    "Memory",
    "PatternMatcher",
    "VoyageEmbedder",
]
```

- [ ] **Step 5: Verify the public API imports**

```bash
cd "$DST"
source .venv/bin/activate
python -c "from aios.foundation import AutonomyGate, DecisionLogger, VoyageEmbedder, EmployeeMemory, FeedbackLoop, KnowledgeStore, PatternMatcher; print('public API OK')"
```

Expected: `public API OK`.

- [ ] **Step 6: Re-run the full foundation test suite**

```bash
cd "$DST"
source .venv/bin/activate
pytest tests/test_foundation/ -v
```

Expected: same pass count as in Step 3, no new regressions from the `__init__.py` change.

- [ ] **Step 7: Commit**

```bash
cd "$DST"
git add src/aios/foundation tests/test_foundation
git commit -m "feat: migrate seven aios.foundation modules + tests from monorepo"
```

---

## Task 3: Migrate `aios.memory.store`

**Files:**
- Copy from monorepo `aios/memory/store.py` to `aios-foundation/src/aios/memory/store.py`
- Copy from monorepo `tests/test_memory/test_store.py` to `aios-foundation/tests/test_memory/test_store.py`
- Modify: `aios-foundation/src/aios/memory/__init__.py`

- [ ] **Step 1: Copy the module and test**

```bash
SRC=~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
DST=~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
cp "$SRC/aios/memory/store.py" "$DST/src/aios/memory/store.py"
cp "$SRC/tests/test_memory/test_store.py" "$DST/tests/test_memory/test_store.py"
[ -f "$SRC/tests/test_memory/conftest.py" ] && cp "$SRC/tests/test_memory/conftest.py" "$DST/tests/test_memory/conftest.py"
```

- [ ] **Step 2: Wire the public API**

Path: `aios-foundation/src/aios/memory/__init__.py`

```python
"""AIOS memory: general-purpose embedded memory store."""
from aios.memory.store import MemoryStore

__all__ = ["MemoryStore"]
```

- [ ] **Step 3: Run memory tests**

```bash
cd "$DST"
source .venv/bin/activate
pytest tests/test_memory/ -v
```

Expected: all tests pass. If failures, follow the same triage as Task 2 Step 3.

- [ ] **Step 4: Run the full test suite to make sure nothing regressed**

```bash
cd "$DST"
pytest -v
```

Expected: all foundation + memory tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/aios/memory tests/test_memory
git commit -m "feat: migrate aios.memory.store + test from monorepo"
```

---

## Task 4: Migrate cross-cutting skills + rules

**Files:**
- Copy from monorepo `skills/meta/` to `aios-foundation/skills/meta/`
- Copy from monorepo `skills/playbooks/` to `aios-foundation/skills/playbooks/`
- Copy from monorepo `rules/global-writing-guardrails.md` to `aios-foundation/rules/global-writing-guardrails.md`

- [ ] **Step 1: Copy directories**

```bash
SRC=~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
DST=~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
cp -r "$SRC/skills/meta/." "$DST/skills/meta/"
cp -r "$SRC/skills/playbooks/." "$DST/skills/playbooks/"
cp "$SRC/rules/global-writing-guardrails.md" "$DST/rules/global-writing-guardrails.md"
```

- [ ] **Step 2: Verify file presence**

```bash
ls "$DST/skills/meta/" "$DST/skills/playbooks/" "$DST/rules/"
```

Expected:
- `skills/meta/`: README.md, validate-writing.md
- `skills/playbooks/`: README.md, build-cloudflare-protected-scraper.md, configure-trigify-monitors.md, discover-trigify-leads.md
- `rules/`: global-writing-guardrails.md

- [ ] **Step 3: Commit**

```bash
git add skills rules
git commit -m "chore: migrate cross-cutting skills (meta + playbooks) and writing guardrails"
```

---

## Task 5: Documentation (RUNBOOK + public API doc)

**Files:**
- Create: `aios-foundation/RUNBOOK.md`
- Create: `aios-foundation/docs/public-api.md`

- [ ] **Step 1: Write `RUNBOOK.md`**

Path: `aios-foundation/RUNBOOK.md`

```markdown
# aios-foundation Runbook

Operational guide for upgrading and consuming `aios-foundation` from downstream repos.

## Versioning

- Releases are git tags (e.g. `v0.1.0`). Tags are immutable.
- Breaking changes bump major (e.g. `v1.0.0` → `v2.0.0`).
- Additive changes bump minor (e.g. `v0.1.0` → `v0.2.0`).
- Patches bump patch (e.g. `v0.1.0` → `v0.1.1`).

## Cutting a new release

1. Ensure all changes are committed and pushed to `main`.
2. Run the full test suite locally: `pytest -v`. Must pass.
3. Update version in `pyproject.toml` (e.g. `version = "0.2.0"`).
4. Commit the version bump: `git commit -am "chore: bump version to v0.2.0"`.
5. Tag and push: `git tag v0.2.0 && git push --tags`.
6. Notify downstream repos. Each downstream pins to a specific tag in its `pyproject.toml`.

## Consuming the package

In any downstream repo's `pyproject.toml`:

```toml
dependencies = [
    "aios-foundation @ git+https://github.com/aios-kit/aios-foundation.git@v0.1.0",
]
```

Or for direct pip install:

```bash
pip install git+https://github.com/aios-kit/aios-foundation.git@v0.1.0
```

## Upgrade procedure for downstream

1. Read the release notes for the target tag.
2. Update the pin in your `pyproject.toml`.
3. Reinstall: `uv pip install --upgrade aios-foundation` (or `pip install --upgrade ...`).
4. Run your full test suite. Failures here block the upgrade until resolved.
5. Run any local smoke tests (e.g. daemon boot, single-cycle pipeline).

## Common issues

### `ModuleNotFoundError: No module named 'aios.foundation'`

The `aios` namespace got shadowed. Check your monorepo doesn't have an `aios/__init__.py` file. PEP 420 namespace packages require NO `__init__.py` at the namespace root.

### Test failures referencing `systems.*` or `api.*`

The test was depending on monorepo-only modules. Either:
- That test belongs in the downstream repo's test suite, not foundation, OR
- The function under test secretly depends on something foundation shouldn't import. Refactor.

### Tag does not appear in pip install

Wait 60 seconds for GitHub's CDN; then `pip install --no-cache-dir`. If still failing, verify the tag is pushed: `git ls-remote --tags origin`.

## Public API surface

See [docs/public-api.md](docs/public-api.md).
```

- [ ] **Step 2: Write `docs/public-api.md`**

Path: `aios-foundation/docs/public-api.md`

```markdown
# aios-foundation Public API

All exports listed below are stable. Anything not listed is internal and may change without a major version bump.

## `aios.foundation`

| Export | Source | Purpose |
|---|---|---|
| `AutonomyGate` | `autonomy.py` | Decide whether an action needs human approval based on the client's autonomy rules and the decision's confidence + sample size. |
| `DecisionLogger` | `decision_logger.py` | Write rows to `decision_log` with context, reasoning, and outcome backfill. |
| `EmbedderCostExceeded` | `embedder.py` | Raised when a Voyage call would exceed the configured per-call cost cap. |
| `VoyageEmbedder` | `embedder.py` | Async Voyage AI embedder. 1024-dim. Batched. Cost-tracked. |
| `EmployeeMemory` | `employee_memory.py` | Protocol for per-employee memory backends. |
| `EmployeeMemoryPgVector` | `employee_memory.py` | Default pgvector-backed implementation of `EmployeeMemory`. |
| `Memory` | `employee_memory.py` | Pydantic model for a single memory row. |
| `FeedbackLoop` | `feedback_loop.py` | Emit `learning_events` from one employee to subscribed employees. |
| `KnowledgeStore` | `knowledge.py` | Read API for `knowledge_base` (expert frameworks, swipe files). |
| `PatternMatcher` | `pattern_matcher.py` | Vector similarity search for past decisions. |

## `aios.memory`

| Export | Source | Purpose |
|---|---|---|
| `MemoryStore` | `store.py` | General-purpose embedded memory (separate from per-employee memory). |

## How systems consume foundation

Every system constructs the foundation modules it needs at startup:

```python
from aios.foundation import (
    AutonomyGate, DecisionLogger, VoyageEmbedder,
    EmployeeMemoryPgVector, FeedbackLoop, KnowledgeStore, PatternMatcher,
)

decision_logger = DecisionLogger(supabase_client)
embedder = VoyageEmbedder(api_key=settings.voyage_api_key)
employee_memory = EmployeeMemoryPgVector(supabase_client, embedder=embedder)
# ... etc
```

Wiring these into a `SystemRegistry` is the deployment's responsibility, not foundation's. See `aios-deployment-template/registry.py` for the wiring pattern.

## Cross-cutting skills

The following markdown skills ship with `aios-foundation` and are intended to be referenced by downstream skill chains:

- `skills/meta/validate-writing.md` — fail-closed validator for any AIOS-generated copy.
- `skills/playbooks/build-cloudflare-protected-scraper.md` — Cloudflare-bypass scraper playbook.
- `skills/playbooks/configure-trigify-monitors.md` — Trigify monitor authoring SOP.
- `skills/playbooks/discover-trigify-leads.md` — daily Trigify discovery routine.
- `rules/global-writing-guardrails.md` — banned phrases and tone rules.

These files are included in the wheel; downstream consumers can locate them via `importlib.resources` or by reading from the cloned repo path.
```

- [ ] **Step 3: Commit documentation**

```bash
git add RUNBOOK.md docs/
git commit -m "docs: add RUNBOOK and public API surface doc"
```

---

## Task 6: Add a basic CI workflow + final pre-tag verification

**Files:**
- Create: `aios-foundation/.github/workflows/tests.yml`

- [ ] **Step 1: Write the GitHub Actions workflow**

Path: `aios-foundation/.github/workflows/tests.yml`

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: |
          uv venv
          uv pip install -e ".[dev]"

      - name: Run tests
        run: |
          source .venv/bin/activate
          pytest -v
```

- [ ] **Step 2: Run the full local test suite one last time**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
source .venv/bin/activate
pytest -v
```

Expected: all tests green. If any fail, fix before tagging. A tag is immutable; do not tag with failing tests.

- [ ] **Step 3: Commit and push**

```bash
git add .github
git commit -m "ci: add tests workflow"
git push origin main
```

Expected: CI run kicks off on GitHub. Wait for the CI run to go green before Task 7. Verify with:

```bash
gh run list --repo aios-kit/aios-foundation --limit 1
```

Expected: status `completed`, conclusion `success`.

---

## Task 7: Tag v0.1.0 release

**Files:** none (git operation only)

- [ ] **Step 1: Verify clean state**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/aios-foundation
git status
```

Expected: `nothing to commit, working tree clean`. If anything uncommitted, commit it first.

- [ ] **Step 2: Tag and push**

```bash
git tag -a v0.1.0 -m "Initial release: foundation extraction from monorepo"
git push origin v0.1.0
```

Expected: tag created and pushed. Verify on GitHub:

```bash
gh release list --repo aios-kit/aios-foundation
```

(Note: a tag is not a release. To create a GitHub Release from the tag — optional but recommended for human-readable changelog — run:)

```bash
gh release create v0.1.0 \
  --repo aios-kit/aios-foundation \
  --title "v0.1.0 — initial extraction" \
  --notes "Initial release. Eight foundation modules + cross-cutting skills migrated from the ai-os-blueprint monorepo. See RUNBOOK.md."
```

- [ ] **Step 3: Verify pip install from the tag works in a clean venv**

```bash
cd /tmp
rm -rf foundation-test
mkdir foundation-test && cd foundation-test
python -m venv venv
source venv/bin/activate
pip install git+https://github.com/aios-kit/aios-foundation.git@v0.1.0
python -c "from aios.foundation import AutonomyGate, DecisionLogger, VoyageEmbedder; print('install OK')"
deactivate
cd ~ && rm -rf /tmp/foundation-test
```

Expected: `install OK`. If this fails, do NOT proceed to monorepo cutover; debug the package build first.

---

## Task 8: Monorepo cutover — add dep, delete migrated modules, fix namespace

**Files:**
- Modify: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/pyproject.toml` (add aios-foundation dep)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/aios/__init__.py` (convert to namespace)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/aios/foundation/` (now from pip)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/aios/memory/` (now from pip)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/skills/meta/` (now in foundation)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/skills/playbooks/` (now in foundation)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/rules/global-writing-guardrails.md` (now in foundation)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/tests/test_foundation/` (now in foundation)
- Delete: `~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/tests/test_memory/` (now in foundation)

**This task is the high-risk one.** Create a feature branch first.

- [ ] **Step 1: Create a feature branch in the monorepo**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
git checkout -b feat/foundation-extraction
git status
```

Expected: clean branch. If your working tree has uncommitted changes from earlier sessions, commit or stash first.

- [ ] **Step 2: Add `aios-foundation` to monorepo `pyproject.toml`**

Edit [pyproject.toml](pyproject.toml) and add inside `dependencies = [...]`:

```toml
    # Foundation (pinned to released tag)
    "aios-foundation @ git+https://github.com/aios-kit/aios-foundation.git@v0.1.0",
```

Then remove duplicated deps that the foundation package now provides. Specifically, delete from monorepo `pyproject.toml`:
- `"voyageai>=0.2.3",` (foundation re-declares; keeping it here is fine but not required — leave it for clarity since other monorepo code uses it directly)
- DO NOT remove `anthropic`, `supabase`, `asyncpg`, `pgvector`, `pydantic`, `pydantic-settings`, `python-dotenv`, `structlog`, `tenacity` — these are still used directly elsewhere in the monorepo.

(In other words, the only required edit is adding the `aios-foundation` line. Keep all other deps for now.)

- [ ] **Step 3: Install the new dependency**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
uv pip install -e .
```

Expected: aios-foundation installs from git tag. Verify:

```bash
pip show aios-foundation | grep -E "Name|Version|Location"
```

Expected: shows `Name: aios-foundation`, `Version: 0.1.0`, `Location: <site-packages path>`.

- [ ] **Step 4: Verify the installed package shadows the local copy**

```bash
python -c "import aios.foundation; print(aios.foundation.__file__)"
```

Expected: a path inside `site-packages/aios/foundation/__init__.py`, NOT the monorepo's `aios/foundation/__init__.py`.

If it points at the monorepo path, that means Python's import resolver is finding the local copy first because of `aios/__init__.py` making it a regular package. Move to Step 5.

- [ ] **Step 5: Delete `aios/__init__.py` to convert `aios` to a namespace package**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
rm aios/__init__.py
```

- [ ] **Step 6: Delete the migrated module directories**

```bash
rm -rf aios/foundation aios/memory
```

- [ ] **Step 7: Delete the migrated skills + rules**

```bash
rm -rf skills/meta skills/playbooks
rm rules/global-writing-guardrails.md
```

- [ ] **Step 8: Delete the migrated test directories**

```bash
rm -rf tests/test_foundation tests/test_memory
```

- [ ] **Step 9: Verify import resolution after deletion**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
python -c "from aios.foundation import AutonomyGate, DecisionLogger, VoyageEmbedder; print('foundation OK')"
python -c "from aios.memory.store import MemoryStore; print('memory OK')"
python -c "from aios.daemon.scheduler import Scheduler; print('daemon namespace OK')" 2>&1 | head -3
```

Expected: all three succeed. The third one verifies the namespace package still finds `aios.daemon.*` from the monorepo even though `aios/__init__.py` is gone.

If any fails with `ModuleNotFoundError`, the most likely cause is a stale `__pycache__`. Clear it:

```bash
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
```

Then retry Step 9.

- [ ] **Step 10: Commit the cutover**

```bash
git add pyproject.toml
git rm -r aios/__init__.py aios/foundation aios/memory skills/meta skills/playbooks rules/global-writing-guardrails.md tests/test_foundation tests/test_memory
git commit -m "feat: cut monorepo over to aios-foundation v0.1.0 from pip"
```

---

## Task 9: Run full monorepo test suite

**Files:** none (verification)

- [ ] **Step 1: Run the full pytest suite**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
source .venv/bin/activate  # or whatever the monorepo's venv path is
pytest -v 2>&1 | tee /tmp/phase1-test-run.log
```

Expected: all tests pass. The test count will be lower than the pre-Phase-1 count (because `tests/test_foundation/` and `tests/test_memory/` were deleted; those tests now live in `aios-foundation` itself).

- [ ] **Step 2: If any tests fail, triage**

Common failure modes and fixes:

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'aios.foundation'` | aios-foundation install didn't take | Re-run `uv pip install -e .` |
| `AttributeError: module 'aios.foundation' has no attribute 'X'` | X wasn't exported in `__init__.py` | Add to foundation's `__init__.py`, tag v0.1.1, update monorepo pin |
| `ImportError: cannot import name 'aios'` from a script | Script ran without venv activation | Activate the monorepo venv |
| Test fails with a Supabase / Voyage credential error | Local env isn't set | Set `.env` per [scripts/sql/](scripts/sql/) docs; not a Phase 1 issue |

- [ ] **Step 3: Confirm test count delta is ONLY the migrated tests**

```bash
# Compare pre-cutover and post-cutover test counts
pytest --collect-only 2>&1 | grep -E "^[0-9]+ tests collected" | tail -1
```

Cross-reference against the deleted directories. If the count drops by anything other than the foundation + memory test counts, investigate.

---

## Task 10: Daemon smoke test

**Files:** none (verification)

- [ ] **Step 1: Boot the daemon in dry-run mode**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
source .venv/bin/activate
python scripts/run_daemon_once.py --dry-run 2>&1 | tee /tmp/phase1-daemon-smoke.log
```

Expected: daemon boots, registers all systems, runs one cycle, logs cleanly, exits 0. No `ImportError`, no `ModuleNotFoundError`, no unhandled exception.

- [ ] **Step 2: Verify Supabase writes are intact**

```bash
# Pick a recent decision_log row written by the smoke test (find by timestamp in log)
psql "$SUPABASE_DB_URL" -c "SELECT decision_type, source, created_at FROM decision_log ORDER BY created_at DESC LIMIT 5;"
```

Expected: a row from the last 5 minutes confirming the foundation modules wrote correctly via the pip-installed package.

- [ ] **Step 3: If any smoke-test step fails, ROLL BACK before debugging**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
git reset --hard HEAD~1   # undo the cutover commit
git checkout main          # or whichever branch was the parent
```

Then debug from a clean state. The aios-foundation tag stays valid; only the monorepo cutover gets reverted.

---

## Task 11: Final commit + PR

**Files:** none (git ops)

- [ ] **Step 1: Push the feature branch**

```bash
cd ~/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
git push origin feat/foundation-extraction
```

- [ ] **Step 2: Open a PR**

```bash
gh pr create --title "Phase 1: extract aios-foundation to pip-installable package" --body "$(cat <<'EOF'
## Summary
- Carved out 7 foundation modules + aios.memory.store + cross-cutting skills + writing guardrails into a new `aios-kit/aios-foundation` repo, tagged v0.1.0
- Monorepo now installs `aios-foundation` from a pinned git tag instead of holding the modules locally
- Converted `aios` from a regular package to a PEP 420 namespace package (deleted `aios/__init__.py`) so the pip-installed `aios.foundation.*` and `aios.memory.*` coexist with the monorepo's `aios.daemon.*` and `aios.registry`

## Test plan
- [x] aios-foundation isolated test suite green (locally + GitHub Actions)
- [x] Pip install from v0.1.0 tag works in a clean venv
- [x] Monorepo full pytest suite green (test count drops only by the migrated tests)
- [x] Daemon smoke test (`run_daemon_once.py --dry-run`) boots and exits 0
- [x] Supabase write verified post-smoke (decision_log row appears)

## Rollback
Revert this commit. The aios-foundation tag stays valid for any future re-attempt.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 3: Update todo list and session log**

In the conversation that runs this plan, update todos to mark Phase 1 complete and Phase 2 next. Append to `memory/sessions/2026-05-05.md` (or current-day session file) with a delta block: decisions, files changed, test counts, daemon smoke result.

---

## Self-Review

**Spec coverage:**
- Carve foundation into separate repo: Tasks 1-7 ✓
- Use pip-from-git-tag distribution: Task 7 + Task 8 Step 2 ✓
- Eight modules migrate, registry.py excluded: Tasks 2-3 + plan-header explicit exclusion ✓
- Cross-cutting skills + rules migrate: Task 4 ✓
- Documentation deliverables (README, RUNBOOK, public API doc): Tasks 1, 5 ✓
- Tests pass in both repos: Tasks 6, 9 ✓
- Daemon smoke test: Task 10 ✓
- Non-breaking migration with rollback: Task 8 (feature branch), Task 10 Step 3 (rollback recipe) ✓
- Tag v0.1.0: Task 7 ✓

**Placeholder scan:** No "TBD", "TODO", or "implement later" remaining. Every step has commands or code.

**Type consistency:** `EmployeeMemory` vs `EmployeeMemoryPgVector` are both exported (Task 2 Step 4) and that matches `aios/foundation/registry.py:27` in the source. `Memory` model also exported. `EmbedderCostExceeded` is exported (Task 2 Step 4). All match the existing import surface enumerated by the grep in the exploration phase.

**Known assumption to verify in Task 2 Step 3:**
- `tests/test_foundation/*.py` and `tests/test_memory/test_store.py` may import from `tests/conftest.py` at the monorepo level. Step 3 includes a conftest copy and triage path. If a foundation test imports from `systems.*` or `api.*`, that test does not belong in foundation; surface to operator before deleting.

**Phase 1 completion criteria:** PR merged, daemon running on the new structure for 24 hours with no regressions, and the v0.1.0 tag intact. Phase 2 (carve `aios-scout`) starts after this gate.
