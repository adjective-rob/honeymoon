# Contributing to ⚡ HONEYMOON

First off, thank you for considering contributing to HONEYMOON! It’s people like you that make HONEYMOON a better tool for everyone.

As an agentic dev engine, HONEYMOON has unique architectural patterns that you should understand before diving in.

## 🧠 Architectural Overview

HONEYMOON is built as a **deterministic orchestrator** (the Controller) that manages a pipeline of **stateless agents**.

1. **The Controller (`honeymoon/controller.py`)**: The brainstem. It manages the linear pipeline: Index → Plan → Implement → Test → Security → Release → PR.


2. 
**Stateless Agents (`honeymoon/agents/`)**: Each agent is a specialized module with its own system prompt and JSON output schema.


3. 
**Governance (`honeymoon/governance/`)**: Enforces safety boundaries and protected paths.


4. 
**Workspace (`honeymoon/workspace/`)**: Uses git worktrees to ensure that agent experimentation never touches your main branch directly.



## 🛠 Getting Started

### Prerequisites

* Python 3.11+
* Git
* API Keys for Gemini (Google) and/or Claude (Anthropic) 



### Local Setup

1. Fork the repository and clone it locally.
2. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3. Install in editable mode with dev dependencies:
```bash
pip install -e ".[dev]"

```


4. Configure your environment:
```bash
cp .env.example .env
# Add your real keys to .env

```



## 🧪 Running Tests

Before submitting a Pull Request, ensure all tests pass:

```bash
python -m pytest

```

We use **Ruff** for linting and formatting. Please run it to keep the code "clean":

```bash
python -m ruff check .

```

## 🤝 How to Contribute

### 🤖 Adding a New Agent

If you want to add a new specialist (e.g., a "Documentation Auditor" or "Performance Profiler"):

1. Create a new module in `honeymoon/agents/`.
2. Inherit from `BaseAgent` in `honeymoon/agents/__init__.py`.
3. Define a clear `system_prompt` and implement `parse_response`.
4. Register the agent in the `Controller`.

### 🛠 Adding a New Tool

To give agents more capabilities (e.g., `docker` or `sql-lint` support):

1. Add the base command to the `allowed_tools` list in `honeymoon/config.yaml`.
2. Ensure it is safe and does not allow arbitrary shell injection.

## 📜 Development Principles

* Build Weird. Ship Clean.: Agents can be chaotic, but the output must be surgical and high-quality.


* **Local-First**: We avoid cloud dependencies other than the model APIs.


* **Deterministic Orchestration**: The sequence of events should be explicit, not governed by "emergent behavior".


* **Under 2k Lines**: Keep the core engine lean. If a feature adds significant bloat, consider making it an optional plugin.