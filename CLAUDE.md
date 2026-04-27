# CLAUDE.md — GLITCHLAB v4.5.0

## Identity

GLITCHLAB is a local-first, repo-agnostic, multi-agent development engine. The Controller orchestrates a deterministic 7-agent pipeline. It never writes code. Agents are stateless between runs. State flows through Pydantic models (`TaskState`, `StepState`) and a mutable `PipelineState` bag.

## Critical Rules

1. **No speculative refactors.** Only change what the task explicitly requires.
2. **No renaming, moving, or deleting files** unless the task specifically asks for it.
3. **No changing function signatures** on public API surfaces without explicit approval: `BaseAgent`, `AgentContext`, `AgentResult`, `Router`, `Workspace`, `ToolExecutor`, `EventBus`, `BoundaryEnforcer`, `SymbolIndex`, `TaskState`.
4. **No rewriting files from scratch.** Use targeted edits. If you must rewrite, explain why first.
5. **Run tests after every change:** `.venv/bin/python3 -m pytest tests/`
6. **Run the linter after every change:** `python3 -m ruff check glitchlab/`
7. **Do not modify `config.yaml` defaults** (routing, limits, allowed_tools, blocked_patterns) unless the task is specifically about configuration.

## Architecture

### Pipeline (do not reorder or skip)

```
Plan → Implement → Debug → Testgen → Security → Release → Archivist
```

Each phase maps to an agent role, a runner function (in `agent_runners.py`), and a post-processing handler (in `step_handlers.py`). The pipeline is declared in `config.yaml` and iterated by `controller.py`.

### Decomposed Controller

The Controller was decomposed from a 2100-line monolith into focused modules:

| Module | Responsibility |
|---|---|
| `controller.py` (385 lines) | Pipeline loop, dispatch, startup/finalize |
| `agent_runners.py` | Context building + agent invocation (one function per role) |
| `step_handlers.py` | Post-processing per agent result → `HandlerSignal` (CONTINUE or EARLY_RETURN) |
| `run_context.py` | `RunContext` dataclass — per-run shared state |
| `lifecycle.py` | Startup checks, workspace creation, PR creation, session entry |
| `task_state.py` | Canonical `TaskState` + `StepState` (structured working memory) |

### Invariants

- **Agents inherit from `BaseAgent`** (`agents/__init__.py`). Each implements `build_messages()` and `parse_response()`. Do not add logic to `BaseAgent.run()`.
- **Context-Router pattern.** `TaskState.to_agent_summary(for_agent)` controls what each agent sees. Field visibility is driven by `AGENT_FIELDS` and `FIELD_CAPS` in `task_state.py`. Do not expand summaries without justification.
- **EventBus is a global singleton** (`event_bus.py`). Events carry `run_id`, `action_id`, `metadata`. All tool executions and agent actions emit events. Do not bypass the bus.
- **Workspace isolation uses git worktrees.** Agents never write to `main`. Do not change `Workspace.create()`, `Workspace.cleanup()`, or the worktree lifecycle.
- **ToolExecutor enforces allowlist + blocklist** (`workspace/tools.py`). Blocked patterns are checked first. Commands are prefix-matched against `allowed_tools`. Do not weaken these checks.
- **BoundaryEnforcer** (`governance/__init__.py`) gates protected paths behind `--allow-core`. Do not soften boundary checks.
- **Router** (`router.py`) wraps LiteLLM with budget tracking, retry logic, and context monitoring. Agents never know which model backs them. Do not leak model names into agent prompts.

## File Ownership

High-coupling files. Read downstream consumers before editing.

| File | Risk |
|---|---|
| `controller.py` | Orchestrates pipeline. Calls into agent_runners, step_handlers, lifecycle. |
| `agent_runners.py` | Builds every agent's context. Changes here alter what agents see. |
| `step_handlers.py` | Post-processing for all 7 agents. Drives PipelineState mutations. |
| `task_state.py` | `TaskState` is canonical. `AGENT_FIELDS` controls context routing for every agent. |
| `agents/__init__.py` | `BaseAgent` + `AgentContext` + `AgentResult` — every agent depends on these shapes. |
| `workspace/__init__.py` | Git worktree lifecycle. Breakage = data loss or orphaned branches. |
| `workspace/tools.py` | `ToolExecutor` — the security boundary for all shell execution. |
| `router.py` | Model routing + budget tracking. Breakage = runaway costs or silent failures. |
| `event_bus.py` | Global singleton. Schema changes break all event consumers. |
| `governance/__init__.py` | `BoundaryEnforcer`. Weakening = removing safety rails. |
| `config.yaml` | Runtime defaults. Changing blocked_patterns or allowed_tools = security surface change. |
| `registry.py` | Agent registry. Adding/removing agents must stay in sync with step_handlers + config.yaml pipeline. |

## Agents

7 agents, all in `glitchlab/agents/`:

| Role | Class | Model tier | Key behavior |
|---|---|---|---|
| `planner` | `PlannerAgent` | high | Agentic tool loop (max 10 iterations). Outputs ≤4 steps with code hints. |
| `implementer` | `ImplementerAgent` | high | Agentic tool loop (step 10 write-deadline). Switchboard delegation. |
| `debugger` | `DebuggerAgent` | high | Fix loop with thrash detection + cascading failure abort. Scope-locked. |
| `testgen` | `TestGenAgent` | high | Single-shot. Generates one regression test. Skipped if doc_only. |
| `security` | `SecurityAgent` | low | Agentic loop. Verdict: pass/warn/block. Block halts pipeline. |
| `release` | `ReleaseAgent` | low | Single-shot. Version bump + changelog. |
| `archivist` | `ArchivistAgent` | low | Single-shot. Writes ADR if change is significant. |

## Circuit Breakers & Safety

- **Planner step cap:** Plans >4 steps are rejected and replanned.
- **Implementer write-deadline:** Forced `done` at step 10 if no real writes occurred.
- **Debugger thrash detection:** Stops if the same fix is attempted twice.
- **Cascading failure abort:** Debug loop exits if test failure count is increasing.
- **Scope-locked debugger:** Only fixes tests broken by the current change, not pre-existing failures.
- **Task quality gate:** Rejects vague objectives before pipeline starts.
- **Budget enforcement:** Per-task limits (1M tokens / $10) with per-role percentages. Raises `BudgetExceededError`.
- **Context monitor:** Proactively snips old messages when approaching model context window.

## Config & Routing

Models are configured in `config.yaml` under `routing:`. Current defaults:
- **High tier:** `openai/gpt-5.4` (planner, implementer, debugger, testgen)
- **Low tier:** `openai/gpt-5.4-mini` (auditor, security, release, archivist)

Config merge order: built-in defaults → repo `.glitchlab/config.yaml` → profile override → env vars.

## Codebase Understanding Stack

Agents don't get raw files dumped on them. Context flows through layers:

1. **RepoIndex** (`indexer.py`) — `git ls-files` + symbol extraction → routing map
2. **SymbolIndex** (`symbols.py`) — tree-sitter AST search (optional, graceful degradation)
3. **ScopeResolver** (`scope.py`) — dependency-aware file + signature resolution
4. **PreludeContext** (`prelude.py`) — bridge to `prelude-context` CLI (architecture/constraints)
5. **Brain** (`brain_writer.py`, `history.py`) — persistent learned heuristics across runs

## CLI Commands

Entry point: `glitchlab` (via `cli.py` / Typer).

| Command | Purpose |
|---|---|
| `run` | Main pipeline. Flags: `--repo`, `--issue`, `--task-file`, `--allow-core`, `--auto-approve`, `--surgical`, `--auto-merge`, `--test`, `--verbose` |
| `interactive` | Human-in-the-loop mode with approval gates |
| `batch` | Parallel multi-task execution |
| `status` | Show config, routing, API key availability |
| `init` | Bootstrap `.glitchlab/` in a repo |
| `history` | View previous runs |
| `audit` | Scan repo for actionable improvements (Ouroboros) |

## Conventions

- **Python 3.11+.** Type hints everywhere. Pydantic v2 for structured data.
- **Ruff** for linting. Line length 100. Target `py311`.
- **Loguru** for logging (`logger.info`, `logger.debug`, `logger.warning`). No `print()` in library code.
- **Rich** for CLI output. Console output goes through `rich.console.Console`.
- **Tests** live in `tests/`. Pytest. 32 test files, 136 tests. No test files outside `tests/`.
- **ADRs** live in `docs/adr/`.
- **Imports:** Absolute only (`from glitchlab.*`). No relative imports.

## Testing

- Every new public function gets a test.
- Do not delete existing tests to make a change pass.
- If a test fails after your change, fix the code — not the test — unless the test was wrong.
- The suite is thin (136 tests). That makes each one more important, not less.

## Adding a New Agent

1. Create `agents/<role>.py` — subclass `BaseAgent`, implement `build_messages()` + `parse_response()`.
2. Add to `registry.py` `AGENT_REGISTRY`.
3. Add runner function in `agent_runners.py`.
4. Add handler function in `step_handlers.py` `STEP_HANDLERS`.
5. Add field routing in `task_state.py` `AGENT_FIELDS`.
6. Add pipeline step in `config.yaml`.
7. No controller edits required.

## What "Optimize" Means Here

- Reduce token consumption in agent prompts (context routing, not context hoarding).
- Reduce redundant I/O or subprocess calls.
- Tighten type safety or error handling.
- Improve clarity of agent system prompts.
- **Not:** rewrite modules, introduce new abstractions, add dependencies, or restructure the pipeline.

## Before You Start Any Task

1. Read the specific files involved. Grep to understand call sites.
2. Identify which tests cover the code you're changing.
3. State your plan (what changes, which files, why) before writing code.
4. Make the smallest change that satisfies the task.
5. Run tests. Run linter. Confirm green before declaring done.
