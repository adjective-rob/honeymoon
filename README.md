```
                                          \.
                                         \\\\
                                        \\\\\\
                                       \\\\\\\\
                          _.._         \\\\\\\\\\
                        .'    '.       \\\\\\\\\\\\
                       /   __   \      \\\\\\\\\\\\\
                      |   (@@)   |      \\\\\\\\\\\\
                      |    __    |       \\\\\\\\\\\
                       \  (__)  /       //||\\\\\\\\
                     _.'`------`'._    // || \\\\\\\\
                   .'  \  ||||  /  '. //  ||  \\\\\\\\
                  /  /\ \  ||  / /\  \\   ||   \\\\\\
                 | /   \ '.__.' /   \ |   ||    \\\\\
                 |/ BZZ \      / BZZ \|   ||     \\\\
                 '-------`----`-------'   ||      \\\
                    \\\   \  /   ///      ||       \\
                     \\\   \/   ///       ||        \
                      \\\  /\  ///
                       \\\//\\///         THE
                        \\//\\//      HIVE MIND
                         \\  //      DEV ENGINE
                          \\//
                           \/
```

# HONEYMOON v5.0.0

**The Hive Mind Dev Engine**

A local-first, repo-agnostic, multi-agent development engine with stigmergic swarm execution. Takes a task, decomposes it into non-overlapping sub-tasks, dispatches parallel worker bees in isolated git worktrees, signs every action with Ed25519, and opens PRs. Runs entirely on your machine. Designed for weak hardware and local quantized LLMs.

---

## Table of Contents

- [The Hive (Agent Roster)](#the-hive)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [The Pipeline](#the-pipeline)
- [Swarm Mode](#swarm-mode)
- [Codebase Understanding](#codebase-understanding)
- [Cryptographic Audit Trail](#cryptographic-audit-trail)
- [Governance & Safety](#governance--safety)
- [Task Sources](#task-sources)
- [The Auditor (Ouroboros)](#the-auditor)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Best Use Cases](#best-use-cases)
- [Design Principles](#design-principles)

---

## The Hive

Seven agents, each with one job. The Controller coordinates but never writes code.

| Bee | Role | How it works |
|-----|------|-------------|
| 👑 **The Queen** | Planner | Agentic tool loop (max 10 iterations). Reads the codebase with `get_function`, `get_class`, and `search_grep` before planning. Outputs a max-4-step execution plan with file targets, code hints, and do-not-touch boundaries. Rejects overscoped plans. |
| 🏗️ **The Builder** | Implementer | Agentic tool loop with read-write-verify cycle. Tools: `read_file`, `get_function`, `search_grep`, `write_file`, `replace_in_file`, `create_file`, `run_check`. Has a write-deadline circuit breaker at step 10 — aborts if no meaningful writes occurred. Can delegate to other agents via switchboard. |
| 🩺 **The Nurse** | Debugger | Fix loop: read error → think → apply fix → re-run tests. Scope-locked — only fixes tests broken by the current change, ignores pre-existing failures. Thrash detection stops repeated failed attempts. Cascading failure abort exits if test count is getting worse. |
| 🔍 **The Inspector** | TestGen | Single-shot. After The Builder writes code, The Inspector generates one focused regression test. No configuration needed. Skipped in doc-only mode or if tests were already added. |
| 🐝 **The Guard** | Security | Agentic security loop. Scans diffs for hardcoded secrets, unsafe dependencies, permission escalations, injection risks. Verdicts: `pass` (clean), `warn` (continue with caution), `block` (halts pipeline, requires human override). |
| 💃 **The Waggle** | Release | Analyzes API surface to determine semver bump (patch, minor, major). Writes the changelog entry. Named after the waggle dance — how bees announce what's new. |
| 🍯 **The Keeper** | Archivist | Writes Architecture Decision Records when a change is significant enough. Captures why, not just what. Preserves the hive's memory for future runs. |

Plus three infrastructure components:

| Component | What it does |
|-----------|-------------|
| **Sentry** | Monitors swarm health. Detects doom loops (token burn without progress), budget blowout, consecutive failures, stalled workers. Emits `swarm.halt` signals. |
| **Decomposer** | Splits a task into non-overlapping sub-tasks by running The Queen, then partitioning plan steps by file ownership. Detects transitive overlaps and infers dependencies. |
| **Pheromone Trail** | Shared awareness layer for the swarm. File-locked append-only JSONL. Records claims, releases, completions, failures, and tool errors. Enables symbol locking and ancestral failure memory. |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/adjective-rob/honeymoon
cd honeymoon
pip install -e .
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

Honeymoon routes through [LiteLLM](https://github.com/BerriAI/litellm), so any supported provider works. Models are configured per-agent in `config.yaml` — agents never know which vendor backs them.

### 3. Initialize a Target Repository

```bash
cd ~/your-project
honeymoon init
```

This creates:
- `.honeymoon/config.yaml` — repo-level configuration overrides
- `.honeymoon/tasks/` — task queue directory
- `.honeymoon/keys/` — Ed25519 signing keypair (auto-generated)
- `.honeymoon/context.json` — native codebase context (stack, imports, constraints)

### 4. Run

```bash
# From a GitHub issue
honeymoon run --repo . --issue 42

# From a local task YAML
honeymoon run --repo . --task-file .honeymoon/tasks/queue/my-task.yaml

# Interactive mode (describe what you want)
honeymoon interactive --repo .

# Swarm mode (decompose + parallel execution)
honeymoon swarm --repo . --objective "Add input validation to all API handlers" --ants 5

# Surgical mode (minimal pipeline, single fix)
honeymoon run --repo . --issue 42 --surgical
```

---

## CLI Commands

| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `honeymoon run` | Execute the full agent pipeline on a task | `--repo`, `--issue`, `--task-file`, `--allow-core`, `--auto-approve`, `--surgical`, `--auto-merge`, `--test`, `--verbose` |
| `honeymoon interactive` | Human-in-the-loop mode — describe what you want | `--repo`, `--surgical` |
| `honeymoon swarm` | Decompose a task and run sub-tasks in parallel | `--repo`, `--objective`, `--task-file`, `--ants` |
| `honeymoon batch` | Run multiple task files in parallel | `--repo`, `--tasks-dir`, `--workers`, `--auto-merge` |
| `honeymoon audit` | Scan repo for actionable improvements | `--repo`, `--kind`, `--category`, `--scout`, `--dry-run` |
| `honeymoon init` | Bootstrap `.honeymoon/` in a repository | `[path]` |
| `honeymoon status` | Check configuration, API keys, and readiness | `--repo` |
| `honeymoon history` | View past runs and aggregate statistics | `--repo`, `--count`, `--stats` |
| `honeymoon compare` | Side-by-side comparison of two task runs | `--repo`, `task_a`, `task_b` |
| `honeymoon doctor` | Verify agent registry and handler integrity | — |

---

## The Pipeline

```
Task → 👑 Plan → 🏗️ Implement → 🩺 Debug → 🔍 Test → 🐝 Secure → 💃 Release → 🍯 Archive → PR
```

The Controller is a thin orchestration shell. It pulls a task, builds a `RunContext` (shared state bundle), iterates pipeline steps, and enforces stop conditions. It dispatches everything and decides nothing. All post-processing logic lives in a handler registry — you can add a new agent type by writing one function and registering it. No controller edits required.

### Pipeline phases in detail

**1. Plan** — The Queen reads the repo route map and task objective, explores the codebase with read-only tools, and produces a max-4-step `ExecutionPlan`. Each step declares which files to touch, what action to take (modify/create/delete), a code hint, and a do-not-touch list. Plans exceeding 4 steps are rejected and replanned.

**2. Implement** — The Builder receives the plan plus file context from the Scope Resolver. Operates in a think-read-search-write-verify tool loop. Has a write-deadline circuit breaker: if step 10 is reached without any meaningful file writes, the run aborts to prevent token-burning exploration. After every write, The Builder must run a verification check before declaring done.

**3. Debug** — The Nurse runs the test suite. If tests fail, enters a fix loop: read error output → analyze root cause → apply fix → re-run tests. The loop is scope-locked (ignores pre-existing failures) and has thrash detection (stops if the same fix is attempted twice). If test failures are increasing with each fix attempt, the cascading failure abort kicks in.

**4. TestGen** — The Inspector generates one focused regression test for the changes. Single-shot, no configuration. Skipped if tests were already added during implementation or if the change is doc-only.

**5. Security** — The Guard scans the diff for dangerous patterns. Issues a verdict: `pass`, `warn`, or `block`. A `block` verdict halts the pipeline and requires explicit human override (`--auto-approve` or interactive confirmation).

**6. Release** — The Waggle analyzes the API surface to determine the version bump (patch/minor/major) and writes a changelog entry.

**7. Archive** — The Keeper evaluates whether the change warrants an Architecture Decision Record. If significant, writes an ADR capturing the reasoning. Skipped for trivial changes.

### Skip conditions

Steps can be skipped based on context:
- `doc_only` — detected when the plan only touches documentation files. Skips Debug, TestGen, Security, Release.
- `fast_mode` — detected when the change touches ≤2 files. Skips Release and Archive.
- `no_test_command` — if no test runner is configured or detected, Debug is skipped.

### Surgical mode

The `--surgical` flag loads a minimal pipeline profile: just Implement + Test. Max fix attempts: 1. Designed for trivially scoped fixes. Auto-detected in batch mode for low-risk, single-file tasks.

---

## Swarm Mode

The parallel execution model. Instead of one agent working sequentially through a task, the swarm decomposes it and dispatches multiple workers simultaneously.

```
Task → Decomposer → [Sub-task A] → Ant 0 (worktree 0)
                     [Sub-task B] → Ant 1 (worktree 1)
                     [Sub-task C] → Ant 2 (worktree 2)
                                         ↓
                              Pheromone Trail (.honeymoon/pheromones.jsonl)
                                         ↓
                                    Results collected by Queen
```

### How decomposition works

1. The Decomposer runs The Queen (planner) on the full task to get an ExecutionPlan.
2. Plan steps are partitioned by file ownership — steps that share files get merged into the same sub-task.
3. Transitive overlap detection ensures that if Step A touches `shared.py` and Step B also touches `shared.py`, they end up in the same sub-task even if they don't directly overlap.
4. Dependencies are inferred from `do_not_touch` cross-references: if Sub-task A's do-not-touch mentions files in Sub-task B, A depends on B.
5. If the task is too small to decompose (≤2 steps), it runs as a single worker.

### Pheromone trail

The shared awareness layer. A file-locked, append-only JSONL log at `.honeymoon/pheromones.jsonl`. Records six event types:

| Type | Purpose |
|------|---------|
| `claim` | Ant claims a file for editing |
| `release` | Ant releases a claim |
| `progress` | Ant reports pipeline step completion |
| `completion` | Ant finished its sub-task |
| `failure` | Ant failed (with error context) |
| `tool_error` | A tool call failed (for ancestral memory) |

**Symbol locking** — Before an ant edits a file, it checks the pheromone trail. If another ant has claimed that file, the current ant skips it and picks a different sub-task. Prevents merge conflicts by design instead of resolving them after the fact.

**Ancestral failure memory** — The trail records tool errors from all ants. Future agents can read the last N failures to avoid repeating the same mistakes in the same session.

### Wave scheduling

Sub-tasks are partitioned into dependency-ordered waves via topological sort:
- **Wave 0:** Sub-tasks with no dependencies (run in parallel)
- **Wave 1:** Sub-tasks whose deps are all in Wave 0 (wait, then run in parallel)
- Diamond dependencies, chains, and unresolvable deps are all handled.

### Sentry monitoring

The Sentry is a passive EventBus subscriber that watches the swarm:
- **Doom loop detection** — If an ant burns 50k+ tokens without completing a pipeline step, it gets halted.
- **Budget enforcement** — Warns at 70% budget usage, halts the swarm at 90%.
- **Consecutive failure detection** — 3 failures in a row halts the ant.
- **Stall detection** — If no event from an ant for 5 minutes, it's flagged.

All thresholds are configurable via `SentryConfig`.

---

## Codebase Understanding

Agents don't receive raw file dumps. Context flows through a layered system that gives each agent precisely what it needs.

### Layer 1: Repo Index (`indexer.py`)

Built from `git ls-files` at the start of every run. Extracts symbols (classes, functions, structs) and imports via regex for speed. Produces a "route map" that tells agents where things are without showing them full file contents. Agents use tools (`get_function`, `search_grep`) to pull specific code on demand.

### Layer 2: Symbol Index (`symbols.py`)

AST-aware code intelligence via tree-sitter. Three capabilities:
- `find_references(symbol)` — structural references (ignores comments/strings)
- `get_function_body(symbol)` — extract full function blocks
- `get_class_outline(class_name)` — method signatures with bodies collapsed

Optional — gracefully degrades if tree-sitter isn't installed. Also supports pheromone-based symbol locking for swarm mode.

### Layer 3: Scope Resolver (`scope.py`)

Dependency-aware context resolution. When The Builder needs to modify `controller.py`, the Scope Resolver traces its imports, pulls signature summaries of dependencies, and provides exactly the context needed. Language-specific import extractors for Python, Rust, and JavaScript/TypeScript.

### Layer 4: Native Context (`hive_context.py`)

Pure-Python codebase understanding with zero external dependencies. Generated at `honeymoon init` time and refreshed at the start of each run. Detects:

| What | How |
|------|-----|
| **Language** | File extension frequency from the index |
| **Framework** | Dependency file scanning (FastAPI, React, Axum, Gin, etc.) |
| **Package manager** | Lockfile detection (pip, poetry, uv, npm, pnpm, yarn, bun, cargo, go modules) |
| **Test framework** | Dependency scanning (pytest, jest, vitest, mocha) |
| **Import graph** | Who depends on what, resolved from the index |
| **Constraints** | Python version, Rust edition, Node engine, linter config |

Outputs `.honeymoon/context.json` and provides a `compact(max_tokens)` method that agents consume directly in their prompts.

### Layer 5: Prelude (`prelude.py`) — Optional Upgrade

[Prelude](https://www.npmjs.com/package/prelude-context) is a separate open-source tool that generates richer, machine-readable context about a codebase — stack, architecture, patterns, constraints, and Architecture Decision Records.

When Prelude is installed (`npm install -g prelude-context`), Honeymoon automatically uses it instead of the native context layer. Agents get deeper project understanding including:
- Structured architecture descriptions
- Explicit project constraints and decisions
- Cross-file pattern recognition
- Compact token-efficient context injection (`prelude compact`)

When Prelude is not installed, agents use the native HiveContext layer. The interface is identical — agents call `compact()` and `get_constraints()` either way and don't know which backend is active.

### Layer 6: Brain (`brain_writer.py`, `history.py`)

Persistent learned heuristics that accumulate across runs. After each successful run, the Brain Writer extracts structural facts from agent message history:
- Which files are read together
- Which edit strategies succeed
- Which patterns cause failures

Stored at `~/.honeymoon/brain/codebase_heuristics.json`. A repo with 100 runs of brain data produces measurably better agent performance than a cold start — the brain tells agents what worked before.

The Task History (`history.py`) is a separate append-only JSONL log at `.honeymoon/logs/history.jsonl` that records every run's status, cost, token usage, and failure patterns. Used for the `honeymoon history` and `honeymoon compare` commands.

---

## Cryptographic Audit Trail

Every event in the pipeline is signed with Ed25519 and appended to an immutable audit log.

### How it works

1. **`honeymoon init`** generates an Ed25519 keypair:
   - `.honeymoon/keys/signing.key` — private key (chmod 600, gitignored)
   - `.honeymoon/keys/verify.pub` — public key (shareable)

2. **Every event** (tool calls, plan steps, code mutations, agent completions) is serialized to JSON, signed with the private key, and appended to `.honeymoon/logs/audit.jsonl`.

3. **Verification** requires only the public key. Anyone with `verify.pub` can validate that every entry in the audit trail was produced by the machine that holds the signing key, and that no entries have been tampered with.

### What gets signed

- Every LLM call (model, tokens, cost, duration)
- Every tool execution (command, stdout, stderr, return code)
- Every pipeline step start/completion/skip
- Every plan submission and implementation
- Every security verdict
- Every workspace creation and cleanup
- Every boundary violation or budget breach

### Signing priority

| Priority | Backend | When |
|----------|---------|------|
| 1 | Zephyr hardware signing | If `zephyr` binary is in PATH (optional upgrade) |
| 2 | Ed25519 software signing | If keypair exists (default after `honeymoon init`) |
| 3 | Unsigned JSONL | If PyNaCl is not installed and no Zephyr |

Signatures are embedded in event metadata as hex strings alongside the public key, making each event independently verifiable.

---

## Governance & Safety

### Boundary enforcement

Protected paths are declared in `.honeymoon/config.yaml`. Agents cannot modify files in protected paths unless the user passes `--allow-core`. Checked at both plan time (The Queen's output) and implementation time (before file writes).

### Budget controls

Two hard limits per task:
- **Token cap** — Default 1,000,000 tokens. Enforced per-role with percentage allocations (implementer gets 60%, planner gets 15%, etc.).
- **Dollar cap** — Default $10.00. Tracked via LiteLLM cost estimation.

If either limit is exceeded, the pipeline halts with a `BudgetExceededError`. In swarm mode, the Sentry monitors cumulative budget across all ants.

### Task quality gate

Before a task enters the pipeline, its objective is scanned for ambiguous language patterns (`"clean up"`, `"improve the"`, `"make robust"`, `"handle gracefully"`, etc.). If detected, narrow-interpretation constraints are injected:

> "This task objective contains ambiguous language. Interpret it NARROWLY. Only modify files explicitly named in the objective or plan. If you are unsure what the objective means, make the SMALLEST possible change."

This prevents implementer exploration spirals on vague auditor-generated tasks.

### Tool executor sandbox

Agents do not run arbitrary shell commands. The `ToolExecutor` enforces:
1. **Blocked patterns** (checked first) — `rm -rf`, `curl`, `wget`, `sudo`, `| bash`, `eval(`, `exec(`. Always rejected.
2. **Allowlist** (prefix-matched) — Only pre-approved commands: `cargo test`, `npm test`, `python -m pytest`, `git diff`, `ls`, `cat`, etc. Everything else is rejected.
3. **Working directory scoping** — All execution is confined to the worktree.

The allowlist and blocklist are configurable in `config.yaml`.

### Human intervention points

| Gate | When it fires | Override |
|------|--------------|----------|
| **Plan review** | After The Queen submits a plan | `--auto-approve` |
| **Core boundary** | When a plan touches protected paths | `--allow-core` |
| **Security block** | When The Guard issues a `block` verdict | `--auto-approve` or interactive confirmation |
| **Pre-PR review** | Before the PR is opened | `--auto-approve` |
| **Budget breach** | When token or dollar cap is exceeded | Pipeline halts, no override |
| **Fix loop exhaustion** | After max debug attempts | Pipeline halts |

### Circuit breakers

| Breaker | What it prevents |
|---------|-----------------|
| Planner step cap (≤4) | Overscoped plans that cause cascading implementation failures |
| Write-deadline (step 10) | Token-burning exploration spirals with no code output |
| Thrash detection | Same fix attempted twice in the debug loop |
| Cascading failure abort | Test failures increasing instead of decreasing |
| Scope-locked debugger | Wasting time on pre-existing test failures |
| Doom loop detection (Sentry) | Ants burning tokens without making progress |
| Consecutive failure halt | 3+ failures in a row from a single ant |

### Workspace isolation

Every task runs in its own git worktree — a full filesystem copy branched from `main`. Agents never write to the main branch. The worktree lifecycle is transactional:
1. Create worktree + branch
2. Run pipeline
3. Commit, push, create PR
4. Cleanup worktree + delete branch

Stale worktrees from crashed runs are automatically detected and cleaned up.

---

## Task Sources

### GitHub Issues

```bash
honeymoon run --repo . --issue 42
```

Fetches the issue title and body as the task objective.

### Local YAML

```yaml
# .honeymoon/tasks/queue/add-validation.yaml
id: add-validation-001
objective: "Add input validation to the /api/users POST endpoint"
constraints:
  - "No new dependencies"
  - "Must return 422 on invalid input"
acceptance:
  - "Tests pass"
  - "New test covers validation"
risk: low
```

```bash
honeymoon run --repo . --task-file .honeymoon/tasks/queue/add-validation.yaml
```

### Interactive

```bash
honeymoon interactive --repo .
# >> Describe what you want HONEYMOON to do:
# >> Add rate limiting to all public API endpoints
```

### Auditor-generated

```bash
honeymoon audit --repo .
# Scans codebase, generates task files in .honeymoon/tasks/queue/
honeymoon batch --repo . --workers 4
# Runs all generated tasks in parallel
```

---

## The Auditor

Honeymoon's ouroboros — it generates work for itself.

The Auditor scans the codebase using tree-sitter (no API calls, no tokens burned) and finds actionable improvements:

| Finding type | What it catches |
|-------------|----------------|
| Missing docstrings | Public functions/classes without documentation |
| TODOs | `TODO`, `FIXME`, `HACK` comments |
| Complex functions | High cyclomatic complexity |
| Untested code | Files with no corresponding test file |
| Dead code | Unused imports, unreachable branches |
| Dependency vulnerabilities | Known CVE patterns in lockfiles |

Findings are ranked by severity and category (security, bug, test, refactor, cleanup, docs, feature). The Task Writer then generates well-scoped YAML task files with decomposition rules that prevent oversized work items.

**Scout mode** (`--scout`) enables LLM-powered analysis on top of the static scan — creative feature suggestions, architectural improvements, and pattern recognition that tree-sitter alone can't do.

Respects the `.honeymoon/ROADMAP.md` — tasks that advance "Now" items are boosted, "Deferred" areas are skipped.

---

## Configuration

### Config merge order

1. Built-in defaults (`honeymoon/config.yaml`)
2. Repo-level overrides (`.honeymoon/config.yaml`)
3. Profile overrides (e.g., `surgical.yaml`)
4. Environment variables (API keys)

### Model routing

```yaml
routing:
  planner: "openai/gpt-5.4"
  implementer: "openai/gpt-5.4"
  debugger: "openai/gpt-5.4"
  testgen: "openai/gpt-5.4"
  security: "openai/gpt-5.4-mini"
  release: "openai/gpt-5.4-mini"
  archivist: "openai/gpt-5.4-mini"
  auditor: "openai/gpt-5.4-mini"

fallbacks:
  high_tier: "openai/gpt-5.4"
  low_tier: "openai/gpt-5.4-mini"
```

Agents never know which model backs them. Swap vendors in config without changing agent code. The Router handles failover automatically — if a model returns 503, it falls back to the configured tier.

### Budget limits

```yaml
limits:
  max_fix_attempts: 4
  max_tokens_per_task: 1000000
  max_dollars_per_task: 10.0
```

Per-role token budgets are enforced as percentages: implementer gets 60%, planner 15%, debugger 30%, etc.

### Boundaries

```yaml
boundaries:
  protected_paths:
    - "core/auth"
    - "migrations/"
```

### Pipeline profiles

The default pipeline runs all 7 agents. The `surgical` profile runs only Implement + Test with 1 fix attempt. Custom profiles can be added under `honeymoon/profiles/`.

---

## Architecture

```
honeymoon/
├── cli.py                # CLI interface (Typer) — 10 commands
├── controller.py         # Orchestration shell (thin spine)
├── run_context.py        # Per-run shared state bundle
├── task_state.py         # TaskState + StepState (structured working memory)
├── step_handlers.py      # Per-agent post-processing (registry pattern)
├── agent_runners.py      # Context builders + agent invocation
├── lifecycle.py          # Startup, finalize, PR creation, session entry
│
├── decomposer.py         # Task → non-overlapping sub-tasks
├── swarm.py              # Parallel ant colony runner + wave scheduling
├── pheromone.py          # Shared swarm awareness layer
├── sentry.py             # Doom loop + budget + failure monitor
│
├── router.py             # Vendor-agnostic model routing (LiteLLM)
├── scope.py              # Dependency-aware context resolution
├── symbols.py            # AST search via tree-sitter + symbol locking
├── indexer.py             # Repo navigator (git ls-files + symbol extraction)
├── hive_context.py        # Native codebase context (Prelude-free)
├── prelude.py             # Prelude integration (optional upgrade)
├── brain_writer.py        # Persistent learned heuristics
├── history.py             # Append-only run log + pattern extraction
├── context_compressor.py  # Token budget management
│
├── signing.py             # Ed25519 event signing (PyNaCl)
├── audit_logger.py        # Signed append-only audit trail
├── event_bus.py           # Global event system (pub/sub singleton)
├── events.py              # Unified event emitter
│
├── task.py                # Task model + apply_changes + apply_tests
├── task_quality.py        # Ambiguity detection gate
├── config_loader.py       # Config loading + profile merging
├── identity.py            # Version, codename, banner
│
├── agents/                # The hive (Queen, Builder, Nurse, Inspector, Guard, Waggle, Keeper)
├── workspace/             # Git worktree isolation + tool executor sandbox
├── governance/            # Boundary enforcement
├── auditor/               # Codebase scanner + task writer (ouroboros)
├── reporting/             # Run reports and dashboard
└── profiles/              # Pipeline profiles (default, surgical)
```

### Context-Router pattern

Agents don't receive the full `TaskState`. Each agent gets only the fields it needs, controlled by `TaskState.to_agent_summary(for_agent)`. Field visibility is driven by `AGENT_FIELDS` (which fields each role sees) and `FIELD_CAPS` (tail-slice limits for list fields). Adding a new agent role means adding one entry to `AGENT_FIELDS`.

### Event Bus

Every meaningful action in the pipeline flows through the `EventBus` — a global pub/sub singleton. Subscribers include:
- **AuditLogger** — signs events and appends to the audit trail
- **PheromoneTrail** — converts pipeline events into pheromone records for swarm awareness
- **Sentry** — monitors for doom loops and budget breaches

Events carry `run_id`, `agent_id`, `action_id`, and `metadata` (for signatures).

---

## Best Use Cases

### Where Honeymoon excels

- **Internal dev teams with large monorepos** — hundreds of small tickets (lint fixes, missing tests, doc updates, migration tasks, endpoint additions that follow existing patterns)
- **Mechanical engineering at scale** — well-defined work that nobody wants to do manually
- **Strict governance requirements** — signed audit trails, boundary enforcement, human approval gates, budget controls
- **Limited compute environments** — designed for dev laptops and small CI boxes, not cloud GPU clusters
- **Tech debt reduction** — run `honeymoon audit` to find problems, `honeymoon batch` to fix them in parallel

### The Monday morning workflow

1. **Scan:** `honeymoon audit --repo .` → 40 well-scoped task files generated
2. **Dispatch:** `honeymoon batch --repo . --workers 4` → 4 parallel workers, isolated worktrees
3. **Review:** 35 PRs open in 30 minutes, each with signed audit trails
4. **Merge:** Humans review diffs. 80% are clean and merge. 15% need tweaks. 5% get closed.

### Where Honeymoon is NOT the right tool

- Greenfield architecture (no existing patterns to follow)
- One-off creative work (write me a game engine)
- Tasks requiring product judgment or user research
- Anything that needs back-and-forth conversation

---

## Design Principles

- **Local-first.** Runs on your machine. No cloud dependency. Targets weak hardware.
- **Repo-agnostic.** Rust, Python, TypeScript, Go, Java — anything with a test runner.
- **Deterministic.** Controller logic is explicit, not probabilistic. Same input → same pipeline.
- **Stigmergic.** Agents communicate through the environment (pheromone trail), not direct messages.
- **Bounded.** Budget caps, retry limits, tool allowlists, doom-loop detection. Nothing runs away.
- **Signed.** Every action is cryptographically attested. The audit trail is tamper-evident.
- **Layered context.** Agents get precisely what they need — not a repo dump, not a guess.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| [LiteLLM](https://github.com/BerriAI/litellm) | Vendor-agnostic LLM routing |
| [Pydantic](https://docs.pydantic.dev/) | Structured data validation |
| [Rich](https://github.com/Textualize/rich) | CLI formatting and tables |
| [Typer](https://typer.tiangolo.com/) | CLI framework |
| [PyNaCl](https://pynacl.readthedocs.io/) | Ed25519 signing (libsodium) |
| [GitPython](https://gitpython.readthedocs.io/) | Git operations |
| [Loguru](https://loguru.readthedocs.io/) | Structured logging |
| [Tenacity](https://tenacity.readthedocs.io/) | Retry logic |
| [tree-sitter](https://tree-sitter.github.io/) | AST parsing (optional) |
| [Prelude](https://www.npmjs.com/package/prelude-context) | Rich codebase context (optional) |

---

## License

MIT — Adjective LLC
