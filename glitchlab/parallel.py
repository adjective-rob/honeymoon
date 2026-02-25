"""
GLITCHLAB Parallel Runner

Executes multiple tasks concurrently, each in its own
isolated worktree with its own budget tracker.

Usage:
    from glitchlab.parallel import run_parallel
    results = run_parallel(repo_path, task_files, max_workers=3)
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()


def _run_single_task(
    task_file: Path, 
    repo_path: Path, 
    allow_core: bool, 
    test_command: str | None
) -> dict[str, Any]:
    """
    Top-level function for ProcessPoolExecutor to pickle correctly.
    Runs a single task in a completely isolated process.
    """
    try:
        # Imports are handled locally to ensure a fresh state in the spawned process
        # and prevent any cross-process pickling issues with complex objects.
        from glitchlab.config_loader import load_config
        from glitchlab.controller import Controller, Task
        
        config = load_config(repo_path)
        task = Task.from_yaml(task_file)
        
        controller = Controller(
            repo_path=repo_path,
            config=config,
            allow_core=allow_core,
            auto_approve=True,
            test_command=test_command,
        )
        return controller.run(task)
    except Exception as e:
        logger.error(f"[PARALLEL] Task failed: {task_file.name} — {e}")
        return {
            "task_id": task_file.stem,
            "status": "error",
            "error": str(e),
        }


def run_parallel(
    repo_path: Path,
    task_files: list[Path],
    max_workers: int = 3,
    allow_core: bool = False,
    auto_approve: bool = True,  # parallel mode requires auto-approve
    test_command: str | None = None,
) -> list[dict[str, Any]]:
    """
    Run multiple tasks in parallel using Process Isolation.

    Each task gets its own process, Controller, Workspace, and budget.
    Results are collected and returned together.

    Args:
        repo_path: Path to the target repository
        task_files: List of paths to task YAML files
        max_workers: Maximum concurrent tasks
        allow_core: Allow core path modifications
        auto_approve: Must be True for parallel (no human gates)
        test_command: Override test command
    """
    repo_path = repo_path.resolve()

    console.print(f"\n[bold]⚡ GLITCHLAB Parallel Mode — {len(task_files)} tasks, {max_workers} workers[/]\n")

    if not auto_approve:
        console.print("[yellow]⚠ Parallel mode requires --auto-approve. Enabling.[/]")
        auto_approve = True

    results: list[dict[str, Any]] = []

    # Using ProcessPoolExecutor to prevent Git/subprocess race conditions
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(_run_single_task, tf, repo_path, allow_core, test_command): tf
            for tf in task_files
        }

        for future in concurrent.futures.as_completed(future_to_file):
            task_file = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
                status = result.get("status", "unknown")
                task_id = result.get("task_id", task_file.stem)
                console.print(f"  [{'green' if status == 'pr_created' else 'red'}]{task_id}: {status}[/]")
            except Exception as e:
                results.append({
                    "task_id": task_file.stem,
                    "status": "error",
                    "error": str(e),
                })

    # Summary table
    _print_parallel_summary(results)

    return results


def _print_parallel_summary(results: list[dict]) -> None:
    """Print a summary table of parallel run results."""
    table = Table(title="Parallel Run Results", border_style="bright_green")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("PR / Branch")
    table.add_column("Cost")

    for r in results:
        status = r.get("status", "unknown")
        color = {"pr_created": "green", "committed": "yellow"}.get(status, "red")

        pr = r.get("pr_url", r.get("branch", "—"))
        budget = r.get("budget", {})
        cost = f"${budget.get('estimated_cost', 0):.4f}"

        table.add_row(
            r.get("task_id", "?"),
            f"[{color}]{status}[/]",
            str(pr)[:60],
            cost,
        )

    console.print(table)

    # Totals
    total_cost = sum(
        r.get("budget", {}).get("estimated_cost", 0) for r in results
    )
    successes = sum(1 for r in results if r.get("status") == "pr_created")
    console.print(
        f"\n[bold]{successes}/{len(results)} succeeded | "
        f"Total cost: ${total_cost:.4f}[/]"
    )