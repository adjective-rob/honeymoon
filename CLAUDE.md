# CLAUDE.md — HONEYMOON v5.0.0

## Identity

HONEYMOON is a local-first, repo-agnostic, multi-agent development and security engine. The Controller orchestrates a deterministic 7-agent pipeline for code changes, plus mission-based pipelines for investigation, simulation, and hardening. Every action is cryptographically signed.

## Critical Rules

1. **No speculative refactors.** Only change what the task explicitly requires.
2. **No renaming, moving, or deleting files** unless the task specifically asks for it.
3. **No changing function signatures** on public API surfaces without explicit approval: `BaseAgent`, `AgentContext`, `AgentResult`, `Router`, `Workspace`, `ToolExecutor`, `EventBus`, `BoundaryEnforcer`, `SymbolIndex`, `TaskState`.
4. **No rewriting files from scratch.** Use targeted edits. If you must rewrite, explain why first.
5. **Run tests after every change:** `.venv/bin/python3 -m pytest tests/`
6. **Run the linter after every change:** `python3 -m ruff check honeymoon/`
7. **Do not modify `config.yaml` defaults** (routing, limits, allowed_tools, blocked_patterns) unless the task is specifically about configuration.

## Architecture

### Development Pipeline (do not reorder or skip)

```
Plan → Implement → Debug → Testgen → Security → Release → Archivist
```

### Security Mission Pipelines

```
Investigate:  Scout (planner) → Analyst (read-only implementer) → Verifier (security)
Simulate:     Threat Modeler → Red Team (read-only) → Blue Team
Harden:       Simulate → Diff against ledger → Compute posture → Sign + append
Deep:         Audit (static) → Parallel investigation lanes → Merge → SPEC.md
```

Missions are YAML profiles in `honeymoon/missions/`. They override agent prompts, tools, and pipeline steps without changing code.

### Decomposed Controller

| Module | Responsibility |
|---|---|
| `controller.py` | Pipeline loop, dispatch, startup/finalize |
| `agent_runners.py` | Context building + agent invocation (one function per role) |
| `step_handlers.py` | Post-processing per agent result → `HandlerSignal` |
| `run_context.py` | `RunContext` dataclass — per-run shared state (includes mission) |
| `lifecycle.py` | Startup checks, workspace creation, PR creation, session entry |
| `task_state.py` | Canonical `TaskState` + `StepState` (structured working memory) |
| `mission.py` | Mission profiles + agent overrides |
| `ledger.py` | Append-only signed hardening ledger |
| `report.py` | Report writer (md + json + html + SPEC) |
| `daemon.py` | WebSocket + HTTP server for live dashboard |
| `mcp_server.py` | MCP server exposing 15 tools for agent integration |

### Invariants

- **Agents inherit from `BaseAgent`** (`agents/__init__.py`). Each implements `build_messages()` and `parse_response()`.
- **Context-Router pattern.** `TaskState.to_agent_summary(for_agent)` controls what each agent sees.
- **EventBus is a global singleton** (`event_bus.py`). All tool executions and agent actions emit events.
- **Workspace isolation uses git worktrees.** Agents never write to `main`.
- **ToolExecutor enforces allowlist + blocklist** (`workspace/tools.py`). `shell=False` with `shlex.split()`. Shell metacharacter detection before execution.
- **BoundaryEnforcer** (`governance/__init__.py`) gates protected paths behind `--allow-core`.
- **Router** (`router.py`) wraps LiteLLM with budget tracking (75% implementer, 40% security). Per-role budget enforcement.
- **Read-only mode:** When `_mission_read_only` is set, implementer uses `INVESTIGATE_TOOLS` (no write tools), write-deadline breaker is disabled, read cap is 30.
- **Forced submission:** Analyst and security agents are forced to submit on their final step.
- **Report mode:** When mission `output_mode == "report"`, verifier "block" = "disputed" (doesn't halt), fast_mode is skipped, findings go to report not PR.

## File Ownership

High-coupling files. Read downstream consumers before editing.

| File | Risk |
|---|---|
| `controller.py` | Orchestrates pipeline. Calls into agent_runners, step_handlers, lifecycle. |
| `agent_runners.py` | Builds every agent's context. Changes here alter what agents see. |
| `step_handlers.py` | Post-processing for all agents. Drives PipelineState mutations. |
| `task_state.py` | `TaskState` is canonical. `AGENT_FIELDS` controls context routing. |
| `agents/__init__.py` | `BaseAgent` + `AgentContext` + `AgentResult`. |
| `workspace/__init__.py` | Git worktree lifecycle. Auto-detects branch name. |
| `workspace/tools.py` | `ToolExecutor` — security boundary. shell=False, metacharacter detection. |
| `router.py` | Model routing + budget tracking. Role limits: implementer 75%, security 40%. |
| `event_bus.py` | Global singleton. Schema changes break all consumers. |
| `config.yaml` | Runtime defaults. Model: gpt-5.4-mini. Budget: 500K tokens / $1.00. |
| `ledger.py` | Hardening ledger. Posture scoring, diff engine, Ed25519 signing. |
| `report.py` | Report generation. write_report, write_spec, _write_html_report. |
| `mcp_server.py` | MCP tool definitions. 15 tools for external agent integration. |

## Agents

7 development agents + mission-specific roles:

| Role | Class | Key behavior |
|---|---|---|
| `planner` | `PlannerAgent` | Agentic tool loop (max 5 iterations). ≤4 steps. Field validators for dumb models. |
| `implementer` | `ImplementerAgent` | Agentic loop. Complexity-gated budget (trivial=12, small=18, medium=30, large=45). Denial feedback on blocked commands. check_after_write waived after 3 denials. |
| `debugger` | `DebuggerAgent` | Fix loop with thrash detection + cascading failure abort. Scope-locked. |
| `testgen` | `TestGenAgent` | Single-shot. Generates one regression test. |
| `security` | `SecurityAgent` | Agentic loop. Verdict: pass/warn/block. Forced submit on final step. |
| `release` | `ReleaseAgent` | Single-shot. Version bump + changelog. |
| `archivist` | `ArchivistAgent` | Single-shot. Writes ADR if significant. |

Mission roles (defined in YAML, reuse agent classes):
- **Scout** (planner) — search plans, not execution plans
- **Analyst** (implementer, read-only) — `INVESTIGATE_TOOLS` + `submit_findings`
- **Verifier** (security) — spot-check references, submit verdict fast
- **Threat Modeler** (planner) — attack plans
- **Red Team** (implementer, read-only) — exploitation chains
- **Blue Team** (security) — evaluates feasibility, suggests fixes

## CLI Commands

| Command | Purpose |
|---|---|
| `deep` | Audit → parallel investigate → SPEC.md. `--fix` for remediation tasks. |
| `harden` | Adversarial simulation + posture tracking. `--posture` for status. |
| `simulate` | Red/Blue attack simulation with signed chains. |
| `scan` | Quick investigate + auto-opens HTML report. |
| `ssp` | Generate a NIST 800-53 Rev 5 System Security Plan. `--baseline low/moderate/high`. |
| `investigate` | Manual objective investigation with signed report. |
| `audit` | Static analysis + dependency vulns (pip-audit/npm audit/cargo audit). |
| `compare` | Compare two task runs — cost, loop steps, planner accuracy, tool divergence. |
| `run` | Main dev pipeline. `--issue`, `--task-file`, `--surgical`, etc. |
| `interactive` | Human-in-the-loop mode. |
| `swarm` | Decompose + parallel execution. |
| `batch` | Run multiple task files in parallel. |
| `serve` | WebSocket daemon for live dashboard (port 4200 WS + 4201 HTTP). |
| `mcp` | Start MCP server (stdio transport) for agent integration. |
| `mcp-config` | Print MCP configuration JSON for Claude Desktop / MCP clients. |
| `init` | Bootstrap `.honeymoon/` in a repository (positional arg). |
| `status` | Check config, routing, API keys. |
| `history` | View previous runs. |
| `doctor` | Verify agent registry integrity. |

## MCP Server

`honeymoon/mcp_server.py` exposes 15 tools via MCP (stdio transport):

| Tool | Type | Description |
|---|---|---|
| `honeymoon_scan` | subprocess | Quick investigation with findings |
| `honeymoon_simulate` | subprocess | Red/Blue adversarial simulation |
| `honeymoon_harden` | subprocess + ledger | Hardening run with posture diff |
| `honeymoon_deep` | subprocess + audit | Full deep scan with parallel lanes |
| `honeymoon_fix_finding` | subprocess | Generate a remediation task from a finding and optionally execute it |
| `honeymoon_posture` | direct Python | Read-only posture score (free, instant) |
| `honeymoon_audit` | direct Python | Static analysis (free, no LLM) |
| `honeymoon_get_report` | direct Python | Get specific or latest report |
| `honeymoon_get_ledger` | direct Python | Full hardening ledger history |
| `honeymoon_verify_report` | direct Python | Verify a report's Ed25519 signature |
| `honeymoon_diff_posture` | direct Python | Compare two hardening runs by posture scores and findings |
| `honeymoon_get_spec` | direct Python | Get the latest SPEC.md content from the reports directory |
| `honeymoon_threat_intel` | direct Python | Query the global threat intelligence database |
| `honeymoon_threat_intel_for_repo` | direct Python | Threat patterns from other repos this repo should check for |
| `honeymoon_threat_intel_stats` | direct Python | Aggregate stats across all repos in the threat intel database |

Pipeline tools run via subprocess. Read-only tools call Python directly.

Start: `honeymoon mcp` (stdio) or get config: `honeymoon mcp-config`

## Dashboard

Live dashboard in `dashboard/` (Next.js + Tailwind + Framer Motion + Lucide).

| Component | What it shows |
|---|---|
| The Hive | Hexagonal agent cells, pulse when active |
| Posture Gauge | Animated radial SVG with trend |
| Command Bar | Scan, Simulate, Harden, Deep Scan buttons |
| Event Stream tab | Real-time parsed events from daemon |
| Reports tab | All investigation reports, expandable findings |
| Findings panel | Latest findings with severity pills |
| Hardening Ledger | Bar chart of posture over time |

Daemon: `honeymoon serve --repo .` (WS 4200 + HTTP 4201)
Frontend: `cd dashboard && pnpm dev` (port 3000)

## Output Files

| File | Purpose |
|---|---|
| `.honeymoon/reports/{id}.md` | Markdown investigation report |
| `.honeymoon/reports/{id}.html` | Self-contained HTML report (SVG icons, print-friendly) |
| `.honeymoon/reports/{id}.json` | Structured data for machine consumption |
| `.honeymoon/reports/SPEC-{id}.md` | Signed remediation plan (deep only) |
| `.honeymoon/ledger.jsonl` | Append-only signed hardening ledger |
| `.honeymoon/logs/audit.jsonl` | Zephyr-signed event trail |
| `.context/decisions.json` | Prelude decisions from medium+ findings |

## Signing

Three layers:
1. **Pipeline events** — Zephyr hardware signing (or Ed25519 fallback) → `audit.jsonl`
2. **Reports** — Ed25519 → `.md` attestation block
3. **Ledger entries** — Ed25519 → `ledger.jsonl`

## Config & Routing

Default model: `openai/gpt-5.4-mini` (dumb model proof).
Budget: 500K tokens / $1.00 per task.
Role limits: implementer 75%, security 40%, planner 15%.

## Conventions

- **Python 3.11+.** Type hints. Pydantic v2.
- **Ruff** for linting. Line length 100.
- **Loguru** for logging. No `print()` in library code.
- **Rich** for CLI output.
- **Tests** in `tests/`. 223 passing.
- **Imports:** Absolute only (`from honeymoon.*`).

## Before You Start Any Task

1. Read the specific files involved.
2. Identify which tests cover the code you're changing.
3. State your plan before writing code.
4. Make the smallest change that satisfies the task.
5. Run tests. Run linter. Confirm green before declaring done.
