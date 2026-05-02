"""
HONEYMOON Run Context — Per-run shared state bundle.

Replaces the pattern of threading 8+ individual parameters (scope, repo_index,
prelude, history, workspace, state, config, run_id, etc.) through every runner
and handler. A single RunContext is created at the start of each run and passed
to all pipeline components.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from honeymoon.agents import BaseAgent
from honeymoon.config_loader import HoneymoonConfig
from honeymoon.task_state import TaskState
from honeymoon.workspace.tools import ToolExecutor


@dataclass
class RunContext:
    """Immutable-ish bag of per-run state shared across pipeline components."""

    # Identity
    run_id: str
    repo_path: Path
    config: HoneymoonConfig

    # Workspace
    ws_path: Path
    workspace: Any  # honeymoon.workspace.Workspace
    tools: ToolExecutor

    # Structured state (mutated by handlers)
    state: TaskState

    # Agents
    agents: dict[str, BaseAgent]

    # Infrastructure
    router: Any           # honeymoon.router.Router
    boundary: Any         # honeymoon.governance.BoundaryEnforcer
    scope: Any            # honeymoon.scope.ScopeResolver
    repo_index: Any       # honeymoon.indexer.RepoIndex
    prelude: Any          # honeymoon.prelude.PreludeContext
    history: Any          # honeymoon.history.TaskHistory

    # Run options
    allow_core: bool = False
    auto_approve: bool = False
    surgical: bool = False
    test_command: str | None = None
    mission: Any = None  # honeymoon.mission.Mission