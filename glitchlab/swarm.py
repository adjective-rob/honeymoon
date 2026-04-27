"""
GLITCHLAB Swarm Runner — Parallel Ant Colony Execution

The swarm runner takes a task, decomposes it into non-overlapping sub-tasks
via the planner, then dispatches N worker ants in parallel worktrees.

Each ant:
  1. Gets its own git worktree (full filesystem isolation)
  2. Reads the pheromone trail for awareness (what's claimed, what failed)
  3. Claims its files via pheromone locking before editing
  4. Runs a focused pipeline (plan is pre-computed, just implement + test)
  5. Reports success/failure to the trail

The Queen (this module) then:
  - Collects results from all ants
  - Picks the consensus merge strategy
  - Stitches non-overlapping changes or picks the best branch

Design constraints:
  - Works on weak hardware (sub-tasks are small, low token budgets)
  - No LLM-based conflict resolution (locking prevents conflicts)
  - Controller stays as scheduler (deterministic spine)
"""

from __future__ import annotations

import concurrent.futures
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console
from rich.table import Table

from glitchlab.pheromone import PheromoneTrail

console = Console()


# ---------------------------------------------------------------------------
# Sub-task definition
# ---------------------------------------------------------------------------

@dataclass
class SubTask:
    """A decomposed unit of work for a single ant."""

    subtask_id: str
    objective: str
    files: list[str] = field(default_factory=list)
    code_hint: str = ""
    constraints: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class AntResult:
    """Result from a single ant worker."""

    ant_id: str
    subtask_id: str
    status: str  # "success" | "error" | "skipped" | "locked"
    branch: str = ""
    files_modified: list[str] = field(default_factory=list)
    test_passing: bool = False
    error: str = ""
    tokens_used: int = 0
    cost: float = 0.0


# ---------------------------------------------------------------------------
# Ant worker — runs in a subprocess via ProcessPoolExecutor
# ---------------------------------------------------------------------------

def _run_ant(
    ant_id: str,
    subtask: dict[str, Any],
    repo_path: Path,
    run_id: str,
    allow_core: bool,
    test_command: str | None,
) -> dict[str, Any]:
    """Execute a single sub-task in an isolated worktree.

    This function runs in a worker process. It must be picklable,
    so it takes dicts/paths instead of complex objects.
    """
    try:
        from glitchlab.config_loader import load_config
        from glitchlab.controller import Controller
        from glitchlab.pheromone import PheromoneTrail
        from glitchlab.task import Task

        trail = PheromoneTrail(repo_path, run_id, subscribe=False)

        subtask_id = subtask["subtask_id"]
        target_files = subtask.get("files", [])

        # --- Pheromone locking: claim all target files ---
        for fpath in target_files:
            holder = trail.is_claimed(fpath)
            if holder is not None and holder != ant_id:
                logger.info(f"[ANT-{ant_id}] {fpath} claimed by {holder}, skipping subtask")
                return {
                    "ant_id": ant_id,
                    "subtask_id": subtask_id,
                    "status": "locked",
                    "error": f"File {fpath} locked by {holder}",
                }
            trail.claim(ant_id, fpath, subtask_id)

        # --- Build a focused task from the sub-task ---
        task = Task(
            task_id=f"swarm-{subtask_id}",
            objective=subtask["objective"],
            constraints=subtask.get("constraints", []),
            acceptance_criteria=[],
            risk_level="low",
        )

        # --- Run the controller in focused mode ---
        config = load_config(repo_path)
        controller = Controller(
            repo_path=repo_path,
            config=config,
            allow_core=allow_core,
            auto_approve=True,
            test_command=test_command,
        )

        result = controller.run(task)

        # --- Report results to trail ---
        status = result.get("status", "error")
        if status in ("pr_created", "committed", "merged"):
            trail.complete(ant_id, subtask_id, {
                "files_modified": result.get("files_modified", []),
                "branch": result.get("branch", ""),
            })
        else:
            trail.fail(ant_id, subtask_id, result.get("error", "unknown"))

        # --- Release claims ---
        for fpath in target_files:
            trail.release(ant_id, fpath)

        return {
            "ant_id": ant_id,
            "subtask_id": subtask_id,
            "status": status,
            "branch": result.get("branch", ""),
            "files_modified": result.get("files_modified", []),
            "test_passing": result.get("test_passing", False),
            "tokens_used": result.get("budget", {}).get("total_tokens", 0),
            "cost": result.get("budget", {}).get("estimated_cost", 0.0),
        }

    except Exception as e:
        logger.error(f"[ANT-{ant_id}] Crashed: {e}")
        return {
            "ant_id": ant_id,
            "subtask_id": subtask.get("subtask_id", "?"),
            "status": "error",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Queen — swarm scheduler
# ---------------------------------------------------------------------------

def run_swarm(
    repo_path: Path,
    subtasks: list[SubTask],
    max_ants: int = 3,
    allow_core: bool = False,
    test_command: str | None = None,
) -> list[AntResult]:
    """Dispatch sub-tasks to parallel ant workers.

    The Queen:
      1. Initializes the pheromone trail
      2. Dispatches ants to non-overlapping sub-tasks
      3. Collects results
      4. Reports consensus

    Sub-tasks with dependencies are held until their deps complete.
    """
    run_id = f"swarm-{uuid.uuid4().hex[:8]}"
    repo_path = repo_path.resolve()

    trail = PheromoneTrail(repo_path, run_id, subscribe=False)
    trail.clear()

    _print_swarm_header(len(subtasks), max_ants, run_id)

    # --- Partition into waves (respecting depends_on) ---
    waves = _build_waves(subtasks)
    all_results: list[AntResult] = []

    for wave_idx, wave in enumerate(waves):
        if len(waves) > 1:
            console.print(f"\n[bold]Wave {wave_idx + 1}/{len(waves)} — {len(wave)} ants[/]")

        wave_results = _dispatch_wave(
            wave=wave,
            repo_path=repo_path,
            run_id=run_id,
            max_ants=max_ants,
            allow_core=allow_core,
            test_command=test_command,
        )
        all_results.extend(wave_results)

        # Check for failures that should halt subsequent waves
        failed = [r for r in wave_results if r.status == "error"]
        if failed:
            logger.warning(
                f"[SWARM] {len(failed)} ants failed in wave {wave_idx + 1}. "
                f"Subsequent waves may be affected."
            )

    _print_swarm_summary(all_results, run_id)
    return all_results


def _dispatch_wave(
    wave: list[SubTask],
    repo_path: Path,
    run_id: str,
    max_ants: int,
    allow_core: bool,
    test_command: str | None,
) -> list[AntResult]:
    """Run a single wave of non-dependent sub-tasks in parallel."""
    results: list[AntResult] = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=min(max_ants, len(wave))) as executor:
        future_to_subtask = {}
        for i, st in enumerate(wave):
            ant_id = f"ant-{i}"
            future = executor.submit(
                _run_ant,
                ant_id=ant_id,
                subtask=_subtask_to_dict(st),
                repo_path=repo_path,
                run_id=run_id,
                allow_core=allow_core,
                test_command=test_command,
            )
            future_to_subtask[future] = st

        for future in concurrent.futures.as_completed(future_to_subtask):
            subtask = future_to_subtask[future]
            try:
                raw = future.result()
                result = AntResult(
                    ant_id=raw.get("ant_id", "?"),
                    subtask_id=raw.get("subtask_id", subtask.subtask_id),
                    status=raw.get("status", "error"),
                    branch=raw.get("branch", ""),
                    files_modified=raw.get("files_modified", []),
                    test_passing=raw.get("test_passing", False),
                    error=raw.get("error", ""),
                    tokens_used=raw.get("tokens_used", 0),
                    cost=raw.get("cost", 0.0),
                )
            except Exception as e:
                result = AntResult(
                    ant_id="?",
                    subtask_id=subtask.subtask_id,
                    status="error",
                    error=str(e),
                )
            results.append(result)
            _log_ant_result(result)

    return results


# ---------------------------------------------------------------------------
# Wave builder — topological sort on depends_on
# ---------------------------------------------------------------------------

def _build_waves(subtasks: list[SubTask]) -> list[list[SubTask]]:
    """Partition subtasks into dependency-ordered waves.

    Wave 0: subtasks with no dependencies
    Wave 1: subtasks whose deps are all in wave 0
    ...and so on.

    Subtasks with unresolvable deps go in the final wave.
    """
    if not subtasks:
        return []

    placed: set[str] = set()
    waves: list[list[SubTask]] = []

    remaining = list(subtasks)
    max_iterations = len(subtasks) + 1

    for _ in range(max_iterations):
        if not remaining:
            break

        wave = []
        still_remaining = []

        for st in remaining:
            deps_met = all(d in placed for d in st.depends_on)
            if deps_met:
                wave.append(st)
            else:
                still_remaining.append(st)

        if not wave:
            # Unresolvable deps — dump everything into final wave
            wave = still_remaining
            still_remaining = []

        waves.append(wave)
        placed.update(st.subtask_id for st in wave)
        remaining = still_remaining

    return waves


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _subtask_to_dict(st: SubTask) -> dict[str, Any]:
    """Convert SubTask to a picklable dict for the worker process."""
    return {
        "subtask_id": st.subtask_id,
        "objective": st.objective,
        "files": st.files,
        "code_hint": st.code_hint,
        "constraints": st.constraints,
    }


def _print_swarm_header(count: int, ants: int, run_id: str) -> None:
    console.print("\n[bold bright_green]🐝 GLITCHLAB Swarm Mode[/]")
    console.print(f"[dim]   {count} sub-tasks, {ants} max ants, run {run_id}[/]\n")


def _log_ant_result(result: AntResult) -> None:
    color = "green" if result.status in ("pr_created", "committed", "merged") else (
        "yellow" if result.status == "locked" else "red"
    )
    console.print(
        f"  [{color}]{result.ant_id} ({result.subtask_id}): "
        f"{result.status}[/]"
    )


def _print_swarm_summary(results: list[AntResult], run_id: str) -> None:
    table = Table(title=f"Swarm Results — {run_id}", border_style="bright_green")
    table.add_column("Ant")
    table.add_column("SubTask")
    table.add_column("Status")
    table.add_column("Tests")
    table.add_column("Files")
    table.add_column("Cost")

    for r in results:
        color = "green" if r.status in ("pr_created", "committed", "merged") else (
            "yellow" if r.status in ("locked", "skipped") else "red"
        )
        tests = "[green]pass[/]" if r.test_passing else "[red]fail[/]"
        table.add_row(
            r.ant_id,
            r.subtask_id,
            f"[{color}]{r.status}[/]",
            tests,
            str(len(r.files_modified)),
            f"${r.cost:.4f}",
        )

    console.print(table)

    total_cost = sum(r.cost for r in results)
    successes = sum(1 for r in results if r.status in ("pr_created", "committed", "merged"))
    console.print(f"\n[bold]{successes}/{len(results)} ants succeeded | Total: ${total_cost:.4f}[/]")
