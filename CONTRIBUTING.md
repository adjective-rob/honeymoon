# Contributing to HONEYMOON

Thanks for considering a contribution. HONEYMOON is an agentic dev and security engine, and it has
a few architectural rules worth knowing before you dive in.

## Architecture in brief

HONEYMOON is a **deterministic orchestrator** (the Controller) that drives a pipeline of agents.

1. **Controller** (`honeymoon/controller.py`) runs the pipeline:
   Plan → Implement → Debug → Testgen → Security → Release → Archivist.
2. **Agents** (`honeymoon/agents/`) inherit from `BaseAgent` and implement `build_messages()` and
   `parse_response()`.
3. **Missions** (`honeymoon/missions/`) are YAML profiles that override prompts, tools, and
   pipeline steps for investigate / simulate / harden runs without changing code.
4. **Governance** (`honeymoon/governance/`) enforces protected paths.
5. **Workspace** (`honeymoon/workspace/`) isolates every run in a git worktree and gates commands
   through the `ToolExecutor` allowlist.

See the [README](README.md) and [`docs/`](docs/) for the full picture.

## Getting started

### Prerequisites

- Python 3.11+
- Git
- An API key for any [LiteLLM](https://github.com/BerriAI/litellm)-supported provider
  (the default routing uses OpenAI)
- Node 22+ and pnpm, only if you are working on the dashboard

### Local setup

```bash
git clone https://github.com/<your-fork>/honeymoon
cd honeymoon
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add your key(s)
```

## Before you open a pull request

```bash
python -m pytest tests/
python -m ruff check honeymoon/
```

Both must pass; CI runs the same commands on every pull request. If you touched the dashboard,
also run `pnpm build` inside `dashboard/`.

Please keep pull requests focused:

- Make the smallest change that solves the problem. No drive-by refactors or renames.
- Add or update a test for behavior changes.
- Do not change signatures on the public API surface (`BaseAgent`, `AgentContext`, `AgentResult`,
  `Router`, `Workspace`, `ToolExecutor`, `EventBus`, `BoundaryEnforcer`, `SymbolIndex`,
  `TaskState`) or the defaults in `honeymoon/config.yaml` without discussing it in an issue first.
- Note user-visible changes in `CHANGELOG.md`.

## Common contributions

### Adding an agent

1. Create a module in `honeymoon/agents/`.
2. Inherit from `BaseAgent` (`honeymoon/agents/__init__.py`).
3. Implement `build_messages()` and `parse_response()`.
4. Register it and run `honeymoon doctor` to verify registry integrity.

### Adding a mission

Add a YAML profile to `honeymoon/missions/`. Missions reuse existing agent classes, so most new
security workflows need no Python changes.

### Adding an allowed tool

Tools are an explicit security boundary. Propose additions to `allowed_tools` in an issue first,
and explain why the command is safe under `shell=False` execution.

## Conventions

- Type hints everywhere, Pydantic v2 models.
- Ruff, line length 100.
- Loguru for logging; no `print()` in library code. Rich for CLI output.
- Absolute imports only (`from honeymoon...`).

## Design principles

- **Local-first.** No cloud dependencies beyond the model APIs.
- **Deterministic orchestration.** The sequence of events is explicit, not emergent.
- **Bounded.** Budget caps, tool allowlists, and circuit breakers on everything.
- **Signed everything.** Events, reports, and ledger entries are cryptographically attested.

## Security issues

Please do not file public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Code of conduct

Participation in this project is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
