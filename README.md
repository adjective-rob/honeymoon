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

A local-first, multi-agent development and security engine. Builds code, investigates codebases, simulates attacks, and tracks security posture — all with cryptographic attestation. Every agent action is Zephyr-signed. Every report is Ed25519-signed. Every finding is provable.

---

## Table of Contents

- [What's New: Security Intelligence](#whats-new-security-intelligence)
- [Quick Start](#quick-start)
- [Command Suite](#command-suite)
- [Security Intelligence](#security-intelligence)
- [The Hive (Agent Roster)](#the-hive)
- [The Pipeline](#the-pipeline)
- [Swarm Mode](#swarm-mode)
- [Codebase Understanding](#codebase-understanding)
- [Cryptographic Audit Trail](#cryptographic-audit-trail)
- [Governance & Safety](#governance--safety)
- [The Auditor](#the-auditor)
- [Dashboard](#dashboard)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Design Principles](#design-principles)

---

## What's New: Security Intelligence

Honeymoon is no longer just a dev engine. It's now a **continuous adversarial hardening platform** with signed attack simulations, a hardening ledger, and a posture tracking system.

```bash
# One command — full security audit with HTML report
honeymoon scan --repo ~/my-project

# Deep scan — audit + investigate + signed SPEC.md
honeymoon deep --repo ~/my-project

# Red/Blue adversarial attack simulation
honeymoon simulate --repo ~/my-project

# Continuous hardening with signed posture ledger
honeymoon harden --repo ~/my-project

# Check your security posture score
honeymoon harden --repo ~/my-project --posture
```

### The Closed Loop

```
Find → Fix → Verify → Sign

Hardening Run #1: Posture 25/100 (1 critical, 3 high)
  ↓ Fix shell=True, dashboard binding, metacharacter detection
Hardening Run #2: Posture 80/100 (5 resolved, 2 new)
  ↓ All signed. All provable. All in the ledger.
```

Every hardening run:
1. Red Team traces exploitation chains through your codebase
2. Blue Team evaluates feasibility and suggests fixes
3. Findings are diffed against previous runs (new vs resolved)
4. Posture score is computed and appended to the signed ledger
5. Findings persist to [Prelude](https://www.npmjs.com/package/prelude-context) as architectural decisions

### The Moat

Every simulation produces **signed, replayable attack chains**. Over time across repos, this becomes a unique dataset: vulnerability → exploitation path → impact. Tamper-evident. Verifiable by anyone with the public key. No one else has this.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/adjective-rob/honeymoon
cd honeymoon
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env`:
```
OPENAI_API_KEY=sk-...
```

Honeymoon routes through [LiteLLM](https://github.com/BerriAI/litellm). Any supported provider works. Default model: `gpt-5.4-mini` — designed to work with cheap, fast models.

### 3. Initialize a Target Repository

```bash
honeymoon init ~/your-project
```

This creates `.honeymoon/` with config, task queue, Ed25519 keypair, and codebase context.

### 4. Run

```bash
# Security scan (fastest way to see what Honeymoon does)
honeymoon scan --repo ~/your-project

# Full deep scan with remediation plan
honeymoon deep --repo ~/your-project

# Code changes from a GitHub issue
honeymoon run --repo ~/your-project --issue 42

# Interactive mode
honeymoon interactive --repo ~/your-project
```

---

## Command Suite

### Security Intelligence

| Command | Purpose | Cost* |
|---------|---------|-------|
| `honeymoon scan --repo .` | Quick investigate + auto-opens HTML report | ~$0.05 |
| `honeymoon deep --repo .` | Audit → Investigate → SPEC.md | ~$0.10 |
| `honeymoon deep --repo . --fix` | + generates remediation task YAMLs | ~$0.10 |
| `honeymoon simulate --repo .` | Red/Blue adversarial attack simulation | ~$0.07 |
| `honeymoon harden --repo .` | Simulate + diff + append to signed ledger | ~$0.10 |
| `honeymoon harden --repo . --posture` | View posture score and trend | free |
| `honeymoon audit --repo .` | Static analysis + dependency vulns | free |

*Typical cost on `gpt-5.4-mini` for a ~100 file codebase.

### Development

| Command | Purpose |
|---------|---------|
| `honeymoon run --repo . --issue 42` | Execute pipeline on a GitHub issue |
| `honeymoon run --repo . --local-task` | Execute pipeline on a local task YAML |
| `honeymoon interactive --repo .` | Human-in-the-loop: describe what you want |
| `honeymoon swarm --repo . -o "..." --ants 5` | Decompose + parallel execution |
| `honeymoon batch --repo . --workers 4` | Run multiple task files in parallel |
| `honeymoon investigate --repo . -o "..."` | Read-only forensics with signed report |

### Utilities

| Command | Purpose |
|---------|---------|
| `honeymoon init [path]` | Bootstrap `.honeymoon/` in a repository |
| `honeymoon status --repo .` | Check configuration and readiness |
| `honeymoon history --repo .` | View past runs and statistics |
| `honeymoon compare --repo . task_a task_b` | Side-by-side run comparison |
| `honeymoon doctor` | Verify agent registry integrity |

---

## Security Intelligence

### honeymoon deep

The flagship command. One shot, full codebase intelligence.

```
Phase 1 · AUDIT       Static analysis + dependency vulnerability scan
Phase 2 · INVESTIGATE  Agent-powered forensics (Scout → Analyst → Verifier)
Phase 3 · SPEC         Signed remediation plan (SPEC.md)
Phase 4 · FIX          (--fix) Remediation task YAMLs for batch execution
```

**Default output is SPEC.md** — a signed deliverable with prioritized remediation tasks (P0-P4). Hand it to your team, your agent, whoever. You own the liability.

**With `--fix`:** generates up to 5 task YAMLs from high/medium findings, queued for `honeymoon batch`. Tasks are scoped to not break existing functionality.

### honeymoon simulate

Red/Blue adversarial attack simulation with signed attack chains.

| Agent | Role | What it does |
|-------|------|-------------|
| **Threat Modeler** | Planner | Produces an attack plan: surfaces, entry points, escalation paths |
| **Red Team** | Analyst | Traces exploitation chains through the code with file:line evidence |
| **Blue Team** | Defender | Evaluates feasibility, rates exploitability, suggests minimal fixes |

The Red Team thinks like a penetration tester. It hunts for:
- Command injection (subprocess, shell execution, eval/exec)
- Authentication bypass (empty credentials, missing checks)
- SQL injection and data exfiltration paths
- Hardcoded secrets and API keys
- Privilege escalation via trust boundary gaps

Every step is Zephyr-signed. The output is a replayable proof chain.

### honeymoon harden

Continuous adversarial hardening with a signed posture ledger.

```bash
# Run #1: baseline
honeymoon harden --repo .
# Posture: 25/100 (5 findings)

# Fix the issues...

# Run #2: verify improvement
honeymoon harden --repo .
# Posture: 80/100 (+55 points, 5 resolved, 2 new)

# Check posture anytime
honeymoon harden --repo . --posture
# Posture score: 80/100 ↑ improving
# Since first run: +55 points
```

The ledger (`.honeymoon/ledger.jsonl`) is append-only and Ed25519-signed. Each entry records:
- Posture score (100 minus weighted severity penalties)
- New findings (not in previous run)
- Resolved findings (in previous run but not current)
- Severity breakdown and trend (improving/stable/degrading)
- Cost per run

**The compliance play:** teams run `harden` on a schedule, building a signed record of their security posture over time. Every improvement is provable. Every regression is immediately visible.

### Posture Scoring

```
Score = 100 - (critical × 25) - (high × 15) - (medium × 5) - (low × 1)
```

| Score | Interpretation |
|-------|---------------|
| 90-100 | Excellent — minimal attack surface |
| 70-89 | Good — some issues to address |
| 40-69 | Concerning — significant vulnerabilities |
| 0-39 | Critical — immediate attention needed |

### Output Files

Every security command produces three report formats plus ledger entries:

| File | Format | Purpose |
|------|--------|---------|
| `.honeymoon/reports/{id}.md` | Markdown | Human-readable investigation report |
| `.honeymoon/reports/{id}.html` | HTML | Beautiful self-contained report (auto-opens in browser) |
| `.honeymoon/reports/{id}.json` | JSON | Machine-consumable structured data |
| `.honeymoon/reports/SPEC-{id}.md` | Markdown | Signed remediation plan (deep only) |
| `.honeymoon/ledger.jsonl` | JSONL | Append-only signed hardening history |
| `.context/decisions.json` | JSON | Prelude decisions from findings |

### Dependency Vulnerability Scanning

The audit phase automatically runs available package auditors:

| Ecosystem | Tool | Trigger |
|-----------|------|---------|
| Python | `pip-audit` | `requirements.txt` or `pyproject.toml` exists |
| Node.js | `npm audit` | `package.json` exists |
| Rust | `cargo audit` | `Cargo.toml` exists |

Findings are integrated into the investigation context so agents can trace whether known CVEs are actually reachable in your code.

---

## The Hive

Seven agents for development, plus mission-specific roles for security.

### Development Agents

| Bee | Role | How it works |
|-----|------|-------------|
| 👑 **The Queen** | Planner | Agentic tool loop (max 5 iterations). Reads codebase with tools before planning. Max 4-step plans with code hints and do-not-touch boundaries. |
| 🏗️ **The Builder** | Implementer | Agentic tool loop with complexity-gated budget (trivial=12, small=18, medium=30 steps). Write-deadline breaker. Denial feedback on blocked commands. |
| 🩺 **The Nurse** | Debugger | Fix loop with thrash detection + cascading failure abort. Scope-locked to tests broken by current change. |
| 🔍 **The Inspector** | TestGen | Single-shot regression test generation. |
| 🐝 **The Guard** | Security | Agentic security loop. Verdict: pass/warn/block. Forced submission on final step. |
| 💃 **The Waggle** | Release | Semver bump + changelog. |
| 🍯 **The Keeper** | Archivist | ADR generation for significant changes. |

### Security Mission Agents

| Agent | Mission | Role |
|-------|---------|------|
| **The Scout** | investigate | Planner in forensic mode — produces search plans, not execution plans |
| **The Analyst** | investigate | Read-only implementer with `submit_findings`. Strips all write tools. |
| **The Verifier** | investigate | Security agent as second pair of eyes. Spot-checks references. |
| **Threat Modeler** | simulate | Planner as adversarial thinker — produces attack plans |
| **Red Team** | simulate | Read-only analyst tracing exploitation chains |
| **Blue Team** | simulate | Defender evaluating feasibility and suggesting fixes |

---

## The Pipeline

### Development Pipeline

```
Task → 👑 Plan → 🏗️ Implement → 🩺 Debug → 🔍 Test → 🐝 Secure → 💃 Release → 🍯 Archive → PR
```

### Investigation Pipeline

```
Objective → Scout (plan) → Analyst (read-only forensics) → Verifier → Signed Report
```

### Simulation Pipeline

```
Scenario → Threat Modeler (attack plan) → Red Team (exploitation) → Blue Team (defense) → Signed Report
```

### Hardening Pipeline

```
Scenario → Simulate → Diff against ledger → Compute posture → Sign and append → Prelude decisions
```

All pipelines are defined as YAML mission profiles in `honeymoon/missions/`. Custom missions can override agent prompts, tool sets, and pipeline steps without changing any code.

---

## Swarm Mode

Parallel execution via task decomposition. Instead of one agent working sequentially, the swarm dispatches multiple workers in isolated git worktrees.

```
Task → Decomposer → [Sub-task A] → Ant 0 (worktree 0)
                     [Sub-task B] → Ant 1 (worktree 1)
                     [Sub-task C] → Ant 2 (worktree 2)
```

Features:
- **Pheromone trail** — shared awareness via file-locked append-only JSONL
- **Symbol locking** — prevents merge conflicts by design
- **Wave scheduling** — dependency-ordered parallel execution
- **Sentry monitoring** — doom loop detection, budget enforcement, stall detection

---

## Codebase Understanding

Agents don't receive raw file dumps. Context flows through layers:

| Layer | Component | What it provides |
|-------|-----------|-----------------|
| 1 | **Repo Index** | Route map from `git ls-files` + symbol extraction |
| 2 | **Symbol Index** | AST-aware search via tree-sitter (optional) |
| 3 | **Scope Resolver** | Dependency-aware file + signature resolution |
| 4 | **Native Context** | Auto-detected stack, framework, constraints |
| 5 | **Prelude** | Rich architectural context (optional upgrade) |
| 6 | **Brain** | Persistent learned heuristics across runs |

---

## Cryptographic Audit Trail

### Three layers of signing

| What | How | Where |
|------|-----|-------|
| **Pipeline events** | Zephyr hardware signing (or Ed25519 fallback) | `.honeymoon/logs/audit.jsonl` |
| **Investigation reports** | Ed25519 | `.honeymoon/reports/{id}.md` |
| **Hardening ledger entries** | Ed25519 | `.honeymoon/ledger.jsonl` |

### What gets signed

- Every LLM call (model, tokens, cost, duration)
- Every tool execution (command, stdout, stderr, return code)
- Every pipeline step start/completion/skip
- Every plan, implementation, and security verdict
- Every investigation finding (severity, evidence, analysis)
- Every simulation attack chain (step by step)
- Every posture score change (new findings, resolved, trend)

### Signing priority

| Priority | Backend | When |
|----------|---------|------|
| 1 | Zephyr hardware signing | `zephyr` binary in PATH |
| 2 | Ed25519 software signing | Keypair exists (after `honeymoon init`) |
| 3 | Unsigned JSONL | No PyNaCl and no Zephyr |

---

## Governance & Safety

### Tool Executor Sandbox

Agents do not run arbitrary shell commands. The `ToolExecutor` enforces:

1. **Shell metacharacter rejection** — `;`, `&&`, `||`, `|`, `` ` ``, `$(`, `${`, `\n`, `>>`, `>&` are blocked before any execution
2. **Blocked patterns** — `rm -rf`, `curl`, `wget`, `sudo`, `| bash`, `eval(`, `exec(`
3. **Allowlist** (prefix-matched) — only pre-approved commands reach execution
4. **`shell=False`** — all execution uses `shlex.split()` + argument vectors, never raw shell

### Other safety mechanisms

- **Boundary enforcement** — protected paths require `--allow-core`
- **Budget controls** — 500K tokens / $1.00 per task (configurable)
- **Circuit breakers** — write-deadline, thrash detection, cascading failure abort, doom loop detection
- **Workspace isolation** — every task runs in its own git worktree
- **Human intervention gates** — plan review, security block, pre-PR review

---

## The Auditor

Honeymoon's ouroboros — it generates work for itself.

Static scanning (no API calls) for:
- Missing docstrings, TODOs, complex functions, large files
- Hardcoded secrets and credential patterns
- **Dependency vulnerabilities** via `pip-audit`, `npm audit`, `cargo audit`

**Scout mode** (`--scout`) adds LLM-powered creative analysis.

```bash
honeymoon audit --repo .          # Static scan
honeymoon audit --repo . --scout  # + LLM analysis
honeymoon batch --repo . -w 4     # Execute findings
```

---

## Dashboard

Three-tab attestation dashboard served at `localhost:8080`:

```bash
python3 honeymoon/reporting/serve.py --repo ~/my-project
```

| Tab | What it shows |
|-----|--------------|
| **Attestation** | Zephyr-signed event timeline with signature badges, pipeline progress bars, expandable event details |
| **Findings** | Investigation reports with severity pills, expandable finding cards, evidence blocks, cost breakdown |
| **Hardening** | Posture score chart (SVG sparkline), run history with new/resolved indicators, trend tracking |

The dashboard binds to `127.0.0.1` (localhost only) and serves data via `/api/audit`, `/api/reports`, `/api/ledger`.

---

## Configuration

### Model routing

```yaml
routing:
  planner: "openai/gpt-5.4-mini"
  implementer: "openai/gpt-5.4-mini"
  debugger: "openai/gpt-5.4-mini"
  security: "openai/gpt-5.4-mini"
```

Designed to work with cheap, fast models. Agents never know which vendor backs them.

### Mission profiles

```yaml
# honeymoon/missions/simulate.yaml
name: simulate
output_mode: report
pipeline:
  - {name: planner, agent_role: planner}
  - {name: red_team, agent_role: implementer}
  - {name: blue_team, agent_role: security}
agent_overrides:
  implementer:
    label: "Red Team"
    read_only: true
    system_prompt_override: "You are RED TEAM..."
```

Custom missions can override prompts, tools, pipeline steps, and output modes without changing code.

---

## Architecture

```
honeymoon/
├── cli.py                 # CLI (Typer) — 14 commands
├── controller.py          # Pipeline orchestration
├── ledger.py              # Signed hardening ledger
├── report.py              # Report writer (md + json + html + spec)
├── mission.py             # Mission profiles + agent overrides
├── agents/                # 7 dev agents + mission role overrides
├── workspace/tools.py     # Tool executor sandbox (shell=False, metachar detection)
├── auditor/               # Static scanner + dependency vulns + task writer
├── reporting/             # Dashboard (attestation + findings + hardening tabs)
│   ├── index.html         # React dashboard (single-file)
│   ├── report_template.html # HTML report template
│   └── serve.py           # Dashboard server (localhost:8080)
├── missions/              # YAML mission profiles
│   ├── investigate.yaml   # Scout → Analyst → Verifier
│   ├── simulate.yaml      # Threat Modeler → Red Team → Blue Team
│   ├── bulk.yaml          # Standard dev pipeline
│   └── monitor.yaml       # Continuous watch (planned)
├── signing.py             # Ed25519 event signing
├── audit_logger.py        # Zephyr/Ed25519 audit trail
└── ...                    # Router, indexer, scope, brain, swarm, etc.
```

---

## Design Principles

- **Local-first.** Runs on your machine. No cloud dependency.
- **Dumb model proof.** Works with `gpt-5.4-mini`. Doesn't need frontier models.
- **Repo-agnostic.** Python, Rust, TypeScript, Go — anything with source files.
- **Signed everything.** Events (Zephyr), reports (Ed25519), ledger (Ed25519).
- **Find → Fix → Verify → Sign.** The closed loop is the product.
- **Default safe.** SPEC.md output. User owns liability. `--fix` is opt-in.
- **Stigmergic.** Agents communicate through the environment, not direct messages.
- **Bounded.** Budget caps, tool allowlists, circuit breakers. Nothing runs away.

---

## License

MIT — Adjective LLC
