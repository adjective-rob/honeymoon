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

A local-first, repo-agnostic, multi-agent development engine with stigmergic swarm execution. Takes a task, decomposes it, dispatches parallel worker bees in isolated worktrees, and merges the results. Runs on your machine. Designed for weak hardware and local quantized LLMs.

---

## The Hive

| Bee | Role | What it does |
|-----|------|-------------|
| 👑 **The Queen** | Planner | Breaks tasks into execution steps. Directs the hive. Never writes code. |
| 🏗️ **The Builder** | Implementer | Writes code in a tool loop: think, read, search, write, verify. |
| 🩺 **The Nurse** | Debugger | Fixes broken tests. Scope-locked. Thrash detection. |
| 🔍 **The Inspector** | TestGen | Single-shot regression test generation. |
| 🐝 **The Guard** | Security | Scans diffs for vulnerabilities. Can block the pipeline. |
| 💃 **The Waggle** | Release | Determines version bump + changelog via the waggle dance. |
| 🍯 **The Keeper** | Archivist | Writes ADRs. Preserves the hive's memory in royal jelly. |

Plus the **Sentry** (swarm monitor), **Decomposer** (task splitter), and **Pheromone Trail** (shared awareness layer).

---

## Quick Start

```bash
cd honeymoon
pip install -e .

# Configure API keys
cp .env.example .env
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...

# Initialize a target repo
cd ~/your-project
honeymoon init

# Run on a task
honeymoon run --repo . --issue 42

# Interactive mode
honeymoon interactive --repo .

# Swarm mode (decompose + parallel)
honeymoon swarm --repo . --objective "Add rate limiting to all API endpoints" --ants 5
```

---

## Swarm Mode

The killer feature. Instead of one agent working sequentially:

```
Task → Decomposer → [Sub-task A] → Ant 0 (worktree 0)
                     [Sub-task B] → Ant 1 (worktree 1)
                     [Sub-task C] → Ant 2 (worktree 2)
                                         ↓
                              Pheromone Trail (.honeymoon/pheromones.jsonl)
                                         ↓
                                    Consensus Merge
```

- **Pheromone Trail** — Shared awareness via file-locked append-only log. Ants see who's editing what, what failed, what succeeded.
- **Symbol Locking** — If Ant 0 claims `router.py`, Ant 1 skips it and picks a different sub-task.
- **Sentry** — Monitors token burn rate. Kills doom-looping ants. Halts the swarm if budget is blown.
- **Wave Scheduling** — Dependency-ordered execution. Independent sub-tasks run in parallel, dependent ones wait.

---

## Pipeline

```
Task → 👑 Plan → 🏗️ Implement → 🩺 Debug → 🔍 Test → 🐝 Secure → 💃 Release → 🍯 Archive → PR
```

Every step is a gate. Nothing ships without approval.

---

## Architecture

```
honeymoon/
├── cli.py              # CLI interface (Typer)
├── controller.py       # Orchestration shell (the spine)
├── decomposer.py       # Task → non-overlapping sub-tasks
├── swarm.py            # Parallel ant colony runner
├── pheromone.py        # Shared swarm awareness layer
├── sentry.py           # Doom loop + budget monitor
├── step_handlers.py    # Per-agent post-processing
├── agent_runners.py    # Context builders + agent invocation
├── router.py           # Vendor-agnostic model routing (LiteLLM)
├── scope.py            # Dependency-aware context resolution
├── symbols.py          # AST search via tree-sitter + symbol locking
├── agents/             # The hive (Queen, Builder, Nurse, etc.)
├── workspace/          # Git worktree isolation + tool executor
├── governance/         # Boundary enforcement + budget control
└── profiles/           # Pipeline profiles (default, surgical)
```

---

## Governance

- **Boundaries** — Protected paths need `--allow-core` override.
- **Budget** — Per-task token + dollar caps. Pipeline halts on breach.
- **Quality Gate** — Rejects vague objectives before they burn tokens.
- **Sentry** — Kills doom-looping agents. Detects stalls. Emits `swarm.halt`.
- **Event Bus** — Every action is a signed event. Append-only JSONL audit trail.

---

## Design Principles

- **Local-first.** Runs on your machine. Targets weak hardware.
- **Repo-agnostic.** Rust, Python, TypeScript, Go — anything with tests.
- **Deterministic.** Controller logic is explicit, not probabilistic.
- **Stigmergic.** Agents communicate through the environment (pheromone trail), not direct messages.
- **Bounded.** Budget caps, retry limits, tool allowlists, doom-loop detection.

---

## License

MIT — Adjective LLC
