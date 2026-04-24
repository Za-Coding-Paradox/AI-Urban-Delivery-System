# Contributing to Positron

Thank you for your interest in contributing. This document covers everything you need to know to make a contribution — from setting up a development environment to getting a pull request merged.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Ways to Contribute](#ways-to-contribute)
3. [Development Setup](#development-setup)
4. [Project Structure](#project-structure)
5. [Development Workflow](#development-workflow)
6. [Code Standards](#code-standards)
7. [Testing Requirements](#testing-requirements)
8. [Commit Messages](#commit-messages)
9. [Pull Request Process](#pull-request-process)
10. [Architecture Guidelines](#architecture-guidelines)

---

## Code of Conduct

This project is a collaborative, educational codebase. All contributors are expected to engage respectfully and constructively. Hostile, dismissive, or exclusionary behavior toward other contributors will not be tolerated.

---

## Ways to Contribute

**Bug reports** — If you find a bug, open an issue with a clear title, steps to reproduce, expected behavior, and actual behavior. Include your OS, Python version, Node version, and browser if relevant.

**Bug fixes** — If you have a fix, open a PR with a reference to the issue. Keep the fix focused — don't mix unrelated changes.

**New algorithms** — The algorithm registry is designed for extension. Adding a new search algorithm requires implementing four methods. See [Architecture Guidelines](#architecture-guidelines).

**New heuristics** — One line in the `HEURISTIC_REGISTRY` dict. See `backend/heuristics/distance.py`.

**New cell types** — Define the type in `cell_type_registry.json` and update `cell.schema.json`. See [Architecture Guidelines](#architecture-guidelines).

**Frontend improvements** — UI enhancements, accessibility improvements, new metric visualizations, performance optimizations.

**Documentation** — Corrections, clarifications, and additions to any documentation file are welcome.

**Tests** — Additional test coverage for edge cases, performance, or untested code paths.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm

### Full setup

```bash
# Clone the repo
git clone <repo-url>
cd AI-Urban-Delivery-System

# Run the development setup script
bash setup.sh --dev

# Or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
pnpm install
cd ..

export PYTHONPATH=$PWD
python -c "
from backend.engine.profile_manager import ProfileManager
mgr = ProfileManager()
for seed, name in [(1,'alpha'),(42,'roundtrip'),(7,'dense_city'),(100,'open_grid')]:
    mgr.save(mgr.generate(seed, name), name)
"
```

### Running in development

```bash
# Terminal 1 — backend
source .venv/bin/activate
export PYTHONPATH=$PWD
uvicorn backend.websocket.web_server:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
pnpm dev
```

---

## Project Structure

```
AI-Urban-Delivery-System/
├── backend/
│   ├── algorithms/       # Search algorithm implementations
│   ├── common/           # Shared constants
│   ├── engine/           # EventBus, GridBuilder, ProfileManager
│   ├── heuristics/       # Heuristic functions and registry
│   ├── profiles/         # Saved city profiles (JSON)
│   ├── schemas/          # JSON Schema definitions
│   ├── tests/            # pytest test suite
│   ├── trace/            # StackTraceBuilder
│   └── websocket/        # FastAPI server and RunController
├── frontend/
│   └── src/
│       ├── components/   # React components by feature
│       ├── hooks/        # Custom React hooks
│       ├── lib/          # Utilities, API client, constants
│       ├── store/        # Zustand store
│       └── types/        # TypeScript types
├── docs/                 # Documentation
├── Dockerfile
├── setup.sh
└── setup.bat
```

---

## Development Workflow

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feature/my-feature
   # or
   git checkout -b fix/issue-123
   ```

2. **Make your changes** following the code standards below.

3. **Write or update tests** for your change. PRs without tests for new behavior will be asked to add them before merging.

4. **Run the full test suite** and confirm it passes:
   ```bash
   pytest backend/tests/ -v
   ```

5. **Run the linter:**
   ```bash
   ruff check backend/
   ```

6. **Run TypeScript type checking:**
   ```bash
   cd frontend && pnpm typecheck
   ```

7. **Commit** with a clear message following the commit message format below.

8. **Open a pull request** against `main` with a description of what changed and why.

---

## Code Standards

### Python

- **Style:** PEP 8, enforced by `ruff`. Line length: 100 characters (configured in `pyproject.toml`).
- **Type hints:** required on all function signatures. Use `from __future__ import annotations` for forward references.
- **Docstrings:** required on all public classes and methods. Explain *why*, not just *what*.
- **Error handling:** raise specific, descriptive exceptions. Never `except Exception: pass` in new code.
- **No global state** in new modules. Use dependency injection or pass parameters explicitly.

```bash
# Run linter
ruff check backend/

# Auto-fix where possible
ruff check backend/ --fix

# Format
black backend/
```

### TypeScript / React

- **Strict TypeScript** — no `any` types in new code. Use proper generics or union types.
- **React hooks rules** — all hooks must be called unconditionally at the top of the component. No hooks after conditional returns.
- **No direct DOM manipulation** — use React state and refs appropriately.
- **Zustand actions** — state mutations belong in the store, not in components. Components call store actions; they do not call `set()` directly.
- **Memoization** — use `useMemo` for derived state that would otherwise recompute on every render. Use `useCallback` for stable callback references passed to child components.
- **No inline `store.getState()` in render** — `getState()` is for imperative callbacks (intervals, event handlers). Subscribed state goes through `useStore(selector)`.

```bash
# Type check
cd frontend && pnpm typecheck

# Lint
pnpm lint
```

### Shared

- **No magic numbers** — constants go in `backend/common/constants.py` or `frontend/src/lib/constants.ts`.
- **No hardcoded URLs** — backend URLs in the frontend go through the API client (`frontend/src/lib/api.ts`).
- **JSON Schema first** — any new data type that crosses a module boundary must have a JSON Schema definition in `backend/schemas/`.

---

## Testing Requirements

All new backend code must have test coverage. The minimum bar:

- **New algorithms:** tests for path found, path cost correctness, metrics shape, and no-path scenario.
- **New heuristics:** tests for correct values, edge cases (same cell, zero distance), and registry lookup.
- **New endpoints:** tests via the httpx async client in `test_websocket_server.py`.
- **New store actions:** unit tests in a frontend test file (Jest + React Testing Library).
- **Bug fixes:** a regression test that fails before the fix and passes after.

```bash
# Run with coverage report
pytest backend/tests/ --cov=backend --cov-report=term-missing -v
```

Coverage below 80% on new files will be flagged in PR review.

---

## Commit Messages

Use the conventional commits format:

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:**
- `feat` — a new feature
- `fix` — a bug fix
- `docs` — documentation changes only
- `test` — adding or updating tests
- `refactor` — code restructuring without behavior change
- `perf` — performance improvement
- `chore` — tooling, build system, dependencies

**Examples:**

```
feat(algorithms): add bidirectional BFS runner

fix(playback): jump flat cursor to first segment event on play

docs(readme): add Docker deployment section

test(event_bus): add coverage for wildcard subscription replay

refactor(store): extract segmentFlatIndices into shared hook
```

Keep the subject line under 72 characters. Use the body to explain *why*, not *what* — the diff shows what changed.

---

## Pull Request Process

1. **Title** — follow the commit message format: `feat(scope): description`.

2. **Description** — include:
   - What problem this solves or what feature it adds
   - How you tested it
   - Any migration steps needed (schema changes, profile regeneration, etc.)
   - Screenshots or recordings for UI changes

3. **Size** — keep PRs focused. A PR that adds a new algorithm should not also refactor the event bus. Split unrelated changes into separate PRs.

4. **Review** — at least one review is required before merging. Address all review comments before requesting re-review.

5. **CI** — all tests must pass. The PR will not be merged with failing tests.

6. **Merge strategy** — squash merge for small changes, merge commit for features with meaningful history. The maintainer decides.

---

## Architecture Guidelines

### Adding a New Algorithm

1. Create `backend/algorithms/my_algo.py` extending `BaseRunner`:

```python
from backend.algorithms.base_runner import BaseRunner
from backend.engine.event_bus import EventBus
import heapq

class MyAlgoRunner(BaseRunner):
    def __init__(self, bus: EventBus):
        super().__init__(bus)
        self._frontier = []

    def _init_frontier(self) -> None:
        self._frontier = []

    def _push(self, node: dict, priority) -> None:
        heapq.heappush(self._frontier, (priority, node))

    def _pop(self) -> dict:
        _, node = heapq.heappop(self._frontier)
        return node

    def _is_empty(self) -> bool:
        return len(self._frontier) == 0

    def _frontier_size(self) -> int:
        return len(self._frontier)

    def _priority(self, g: float, h: float):
        return g + h  # example: A*-style
```

2. Register it in `backend/algorithms/algorithms_registry.py`:

```python
from backend.algorithms.my_algo import MyAlgoRunner

ALGORITHM_REGISTRY = {
    ...
    "my_algo": MyAlgoRunner,
}
```

3. Add it to `backend/schemas/algorithm_config.schema.json` and `backend/schemas/trace_event.schema.json` enum lists.

4. Add tests in `backend/tests/test_algorithms.py`.

5. Add it to the frontend's `AlgorithmId` type in `frontend/src/types/index.ts`.

That's it. The RunController, EventBus, PlaybackBar, GridView, and MetricsView all handle it automatically.

### Adding a New Cell Type

1. Add the type to `backend/schemas/cell_type_registry.json` with its `passable` and `cost` rules.
2. Update `backend/schemas/cell.schema.json` to include it in the `type` enum.
3. Add color/style in `frontend/src/lib/constants.ts` or the relevant component.
4. No algorithm code changes needed — algorithms only check `cell["passable"]` and `cell["cost"]`.

### Adding a New Heuristic

1. Add the function to `backend/heuristics/distance.py`:

```python
def chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    """Chebyshev distance — max of abs differences. For 8-directional movement."""
    return max(abs(ax - bx), abs(ay - by))
```

2. Register it:

```python
HEURISTIC_REGISTRY = {
    ...
    "chebyshev": chebyshev,
}
```

3. Add it to the `heuristic` enum in `backend/schemas/algorithm_config.schema.json`.

4. Add tests in `backend/tests/test_heuristics.py`.

---

## Questions

If you're unsure about anything — approach, design, scope — open an issue or discussion before starting work. It saves everyone time to align early rather than review a large PR that goes in the wrong direction.
