"""
HONEYMOON CLI — The Interface

Three modes:
  1. honeymoon run --repo <path> --issue <num>     (GitHub issue)
  2. honeymoon run --repo <path> --local-task       (YAML file)
  3. honeymoon interactive --repo <path>            (Human-in-the-loop)

Plus utilities:
  - honeymoon status        (check config + API keys)
  - honeymoon init <path>   (bootstrap .honeymoon in a repo)
  - honeymoon batch         (parallel task execution)
  - honeymoon swarm         (decompose + parallel ant colony)
  - honeymoon history       (view previous runs)
  - honeymoon audit         (scan for new tasks)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from honeymoon.identity import __codename__, __tagline__, __version__, BANNER
from honeymoon.config_loader import load_config, validate_api_keys
from honeymoon.controller import Controller, Task
from honeymoon.history import TaskHistory
from honeymoon.parallel import run_parallel
from honeymoon.prelude import PreludeContext
from honeymoon.audit_logger import AuditLogger  # <--- NEW: Import the Zephyr subscriber

# Load .env from current directory or home
load_dotenv()
load_dotenv(Path.home() / ".honeymoon" / ".env")

app = typer.Typer(
    name="honeymoon",
    help=f"{__codename__} — {__tagline__}\nThe Agentic Dev Engine.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()


def version_callback(value: bool):
    """Print the CLI version for the global --version flag and exit immediately."""
    if value:
        console.print(f"{__codename__} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
):
    """Launch the Typer application as the CLI entry point."""


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def _print_banner():
    console.print(f"[bright_green]{BANNER}[/]")
    console.print(f"  [dim]v{__version__} — {__tagline__}[/]\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def run(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    issue: Optional[int] = typer.Option(None, "--issue", "-i", help="GitHub issue number"),
    local_task: bool = typer.Option(False, "--local-task", "-l", help="Use local task YAML"),
    task_file: Optional[Path] = typer.Option(None, "--task-file", "-f", help="Path to task YAML"),
    allow_core: bool = typer.Option(False, "--allow-core", help="Allow modifications to protected core paths"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip human intervention gates"),
    surgical: bool = typer.Option(False, "--surgical", help="Run surgical pipeline"),
    auto_merge: bool = typer.Option(False, "--auto-merge", help="Automatically squash and merge the PR if successful"),
    mission_name: Optional[str] = typer.Option(None, "--mission", "-m", help="Mission profile (investigate, bulk, monitor)"),
    test_cmd: Optional[str] = typer.Option(None, "--test", "-t", help="Test command to run (e.g. 'cargo test')"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Run the main CLI workflow that resolves a task and executes the agent pipeline."""
    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    config = load_config(repo)

    if auto_merge:
        config.automation.auto_merge_pr = True

    # Load mission profile if specified
    mission = None
    if mission_name:
        from honeymoon.mission import load_mission
        mission = load_mission(mission_name, repo)
        console.print(f"[cyan]Mission: {mission.name} — {mission.description}[/]")

    # Resolve task
    if issue:
        console.print(f"[cyan]Fetching GitHub issue #{issue}...[/]")
        task = Task.from_github_issue(repo, issue)
    elif local_task or task_file:
        # Check queue first, then root tasks dir
        tf = task_file or (repo / ".honeymoon" / "tasks" / "queue" / "next.yaml")
        if not tf.exists():
            tf = (repo / ".honeymoon" / "tasks" / "next.yaml")

        if not tf.exists():
            console.print(f"[red]Task file not found: {tf}[/]")
            raise typer.Exit(1)
        task = Task.from_yaml(tf)
    else:
        console.print("[red]Specify --issue or --local-task[/]")
        raise typer.Exit(1)

    # Auto-detect test command if not provided
    if not test_cmd:
        test_cmd = _detect_test_command(repo)

    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        allow_core=allow_core,
        auto_approve=auto_approve,
        surgical=surgical,
        test_command=test_cmd,
        mission=mission,
    )

    result = controller.run(task)

    # Final status
    status = result.get("status", "unknown")
    status_color = {
        "pr_created": "green",
        "committed": "yellow",
        "interrupted": "yellow",
    }.get(status, "red")

    console.print(f"\n[bold {status_color}]Status: {status}[/]")


@app.command()
def interactive(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    allow_core: bool = typer.Option(False, "--allow-core"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip human intervention gates"),
    surgical: bool = typer.Option(False, "--surgical", help="Run surgical pipeline"),
    auto_merge: bool = typer.Option(False, "--auto-merge", help="Automatically squash and merge the PR if successful"),
    test_cmd: Optional[str] = typer.Option(None, "--test", "-t"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Interactive mode — describe what you want, review the plan, approve execution."""
    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    config = load_config(repo)

    if auto_merge:
        config.automation.auto_merge_pr = True

    console.print("[bold]Describe what you want HONEYMOON to do:[/]")
    objective = typer.prompt(">>")

    if not objective.strip():
        console.print("[red]No objective provided.[/]")
        raise typer.Exit(1)

    task = Task.from_interactive(objective)

    if not test_cmd:
        test_cmd = _detect_test_command(repo)

    # --- NEW: Initialize the Zephyr Audit Logger subscriber ---
    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        allow_core=allow_core,
        auto_approve=auto_approve,
        surgical=surgical,
        test_command=test_cmd,
    )

    result = controller.run(task)
    status = result.get("status", "unknown")
    console.print(f"\n[bold]Status: {status}[/]")


@app.command()
def status(
    repo: Optional[Path] = typer.Option(None, "--repo", "-r"),
):
    """Check HONEYMOON configuration and readiness."""
    _print_banner()

    # API Keys
    keys = validate_api_keys()
    key_table = Table(title="API Keys", border_style="cyan")
    key_table.add_column("Key")
    key_table.add_column("Status")

    for key, available in keys.items():
        status_str = "[green]✓ Available[/]" if available else "[red]✗ Missing[/]"
        key_table.add_row(key, status_str)

    console.print(key_table)

    # Config
    if repo:
        config = load_config(repo.resolve())
        console.print("\n[bold]Routing:[/]")
        console.print(f"  Planner:     {config.routing.planner}")
        console.print(f"  Implementer: {config.routing.implementer}")
        console.print(f"  Debugger:    {config.routing.debugger}")
        console.print(f"  Security:    {config.routing.security}")
        console.print(f"  Release:     {config.routing.release}")

        console.print("\n[bold]Limits:[/]")
        console.print(f"  Max fix attempts: {config.limits.max_fix_attempts}")
        console.print(f"  Max tokens/task:  {config.limits.max_tokens_per_task:,}")
        console.print(f"  Max $/task:       ${config.limits.max_dollars_per_task}")

        if config.boundaries.protected_paths:
            console.print("\n[bold]Protected paths:[/]")
            for p in config.boundaries.protected_paths:
                console.print(f"  🔒 {p}")

    # Tools
    tools_table = Table(title="System Tools", border_style="cyan")
    tools_table.add_column("Tool")
    tools_table.add_column("Status")

    import shutil
    for tool in ["git", "gh", "cargo", "python3", "node", "prelude", "zephyr"]:
        found = shutil.which(tool)
        s = f"[green]✓ {found}[/]" if found else "[dim]✗ Not found[/]"
        tools_table.add_row(tool, s)

    console.print(tools_table)

    # Prelude context
    if repo:
        prelude = PreludeContext(repo.resolve())
        prelude_table = Table(title="Prelude Context", border_style="magenta")
        prelude_table.add_column("Property")
        prelude_table.add_column("Value")

        prelude_table.add_row("CLI installed", "✓" if prelude.cli_available else "✗")
        prelude_table.add_row(".context/ exists", "✓" if prelude.context_exists else "✗")

        if prelude.context_exists:
            summary = prelude.summary()
            prelude_table.add_row("Context files", ", ".join(summary.get("files", [])))
            prelude_table.add_row("ADRs", str(summary.get("decisions_count", 0)))
            if "project_name" in summary:
                prelude_table.add_row("Project", summary["project_name"])
            if "language" in summary:
                prelude_table.add_row("Language", summary["language"])

        console.print(prelude_table)

        if not prelude.available:
            console.print(
                "[dim]Install Prelude for richer agent context: "
                "npm install -g prelude-context[/]"
            )


@app.command()
def init(
    repo: Optional[Path] = typer.Argument(None, help="Path to repository"),
):
    """Initialize .honeymoon directory in a repository."""
    _print_banner()

    repo = (repo or Path.cwd()).resolve()
    gl_dir = repo / ".honeymoon"
    gl_dir.mkdir(exist_ok=True)
    (gl_dir / "tasks").mkdir(exist_ok=True)
    (gl_dir / "tasks" / "queue").mkdir(exist_ok=True) # Permanent Fix: Ensure queue exists
    (gl_dir / "logs").mkdir(exist_ok=True)
    (gl_dir / "worktrees").mkdir(exist_ok=True)

    # Create default config
    config_path = gl_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text("""# HONEYMOON repo-level config overrides
# These merge with the built-in defaults.

# Override routing for this specific project:
# routing:
#   implementer: "anthropic/claude-sonnet-4-20250514"

# Set project-specific boundaries:
# boundaries:
#   protected_paths:
#     - "crates/zephyr-core"
#     - "crates/zephyr-envelope"

# Adjust limits:
# limits:
#   max_fix_attempts: 3
#   max_dollars_per_task: 5.0
""")

    # Create example task
    task_path = gl_dir / "tasks" / "example.yaml"
    if not task_path.exists():
        task_path.write_text("""id: example-001
objective: "Add a --verbose flag to the CLI"
constraints:
  - "No new dependencies"
  - "Must not change existing flag behavior"
acceptance:
  - "Tests pass"
  - "New test covers the flag"
  - "Help text updated"
risk: low
""")

    # Create ROADMAP template
    roadmap_path = gl_dir / "ROADMAP.md"
    if not roadmap_path.exists():
        roadmap_path.write_text("""# Project Roadmap
#
# The HONEYMOON auditor reads this file every scan to prioritize task generation.
# Tasks that advance "Now" items are boosted. "Deferred" areas are skipped.
# Edit this file as your priorities change — the auditor picks it up automatically.

## Now
- (what you're actively working on)

## Next
- (queued work, not urgent but directional)

## Deferred
- (areas where the auditor should NOT generate tasks right now)
""")

    # Generate Ed25519 signing keypair
    from honeymoon.signing import HiveSigner, SIGNING_AVAILABLE
    if SIGNING_AVAILABLE:
        key_path = gl_dir / "keys" / "signing.key"
        if not key_path.exists():
            signer = HiveSigner.generate(repo)
            console.print("[green]  🔑 Ed25519 keypair generated[/]")
            console.print(f"     Public key: {signer.public_key_hex[:16]}...")
        else:
            console.print("[dim]  🔑 Ed25519 keypair already exists[/]")
    else:
        console.print("[dim]  🔑 Install PyNaCl for signed audit trails: pip install PyNaCl[/]")

    # Add to .gitignore
    gitignore = repo / ".gitignore"
    ignore_entries = [".honeymoon/worktrees/", ".honeymoon/tasks/", ".honeymoon/logs/", ".honeymoon/keys/", ".context/"]
    if gitignore.exists():
        content = gitignore.read_text()
        additions = [e for e in ignore_entries if e not in content]
        if additions:
            with open(gitignore, "a") as f:
                f.write("\n# HONEYMOON\n")
                for e in additions:
                    f.write(f"{e}\n")
    else:
        gitignore.write_text("# HONEYMOON\n" + "\n".join(ignore_entries) + "\n")

    console.print(f"[green]✅ Initialized HONEYMOON in {gl_dir}[/]")
    console.print(f"  Config:  {config_path}")
    console.print(f"  Tasks:   {gl_dir / 'tasks'}")
    console.print(f"  Example: {task_path}")
    console.print(f"  Roadmap: {roadmap_path}")

    # Generate native context (always available, no external deps)
    from honeymoon.hive_context import HiveContext
    hive_ctx = HiveContext(repo)
    hive_ctx.generate()
    console.print("[green]  🧠 Native context generated[/]")

    # Bootstrap Prelude if available (upgrade path)
    prelude = PreludeContext(repo)
    if prelude.cli_available:
        if not prelude.context_exists:
            console.print("\n[magenta]📋 Prelude detected — initializing rich context...[/]")
            if prelude.init():
                console.print("[green]  ✅ .context/ created — agents get full project understanding[/]")
                console.print("  [dim]Add decisions: prelude decision[/]")
                console.print("  [dim]Update context: prelude update[/]")
            else:
                console.print("[yellow]  ⚠ Prelude init failed — using native context[/]")
        else:
            console.print(f"\n[dim]📋 Prelude context already exists at {prelude.context_dir}[/]")
    else:
        console.print(
            "[dim]  💡 Install Prelude for richer context: "
            "npm install -g prelude-context[/]"
        )


@app.command()
def batch(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    tasks_dir: Optional[Path] = typer.Option(None, "--tasks-dir", "-d", help="Directory of task YAMLs"),
    workers: int = typer.Option(3, "--workers", "-w", help="Max concurrent tasks"),
    allow_core: bool = typer.Option(False, "--allow-core"),
    auto_merge: bool = typer.Option(False, "--auto-merge", help="Automatically squash and merge the PRs if successful"),
    test_cmd: Optional[str] = typer.Option(None, "--test", "-t"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run multiple tasks in parallel (auto-approve mode)."""
    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    td = tasks_dir or (repo / ".honeymoon" / "tasks" / "queue")

    if not td.exists():
        console.print(f"[red]Tasks directory not found: {td}[/]")
        raise typer.Exit(1)

    raw_task_files = sorted(td.glob("*.yaml")) + sorted(td.glob("*.yml"))
    raw_task_files = [f for f in raw_task_files if "example" not in f.name.lower()]

    if not raw_task_files:
        console.print(f"[red]No task files found in {td}[/]")
        raise typer.Exit(1)

    # --- NEW: Task Priority Queue ---
    # Parse and sort tasks by risk so High Risk runs first when main is cleanest.
    tasks_with_risk = []
    for tf in raw_task_files:
        try:
            t = Task.from_yaml(tf)
            # High = 0 (first), Medium = 1, Low = 2
            weight = {"high": 0, "medium": 1, "low": 2}.get(t.risk_level, 3)
            tasks_with_risk.append((weight, tf))
        except Exception:
            tasks_with_risk.append((3, tf)) # Push parsing errors to the end
            
    tasks_with_risk.sort(key=lambda x: x[0])
    task_files = [tf for _, tf in tasks_with_risk]

    console.print(f"[cyan]Found {len(task_files)} tasks in {td} (Sorted by Risk Priority)[/]")
    for tf in task_files:
        console.print(f"  [dim]{tf.name}[/]")

    if not test_cmd:
        test_cmd = _detect_test_command(repo)

    # --- NEW: Initialize the Zephyr Audit Logger subscriber ---
    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    results = run_parallel(
        repo_path=repo,
        task_files=task_files,
        max_workers=workers,
        allow_core=allow_core,
        test_command=test_cmd,
        auto_merge=auto_merge,
    )

    # Exit code based on results
    failures = sum(1 for r in results if r.get("status") not in ("pr_created", "committed", "merged"))
    if failures:
        raise typer.Exit(1)


@app.command()
def history(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    count: int = typer.Option(10, "--count", "-n", help="Number of entries to show"),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show aggregate statistics"),
):
    """View task history and statistics."""
    _print_banner()

    repo = repo.resolve()
    hist = TaskHistory(repo)

    if stats:
        s = hist.get_stats()
        if s["total_runs"] == 0:
            console.print("[dim]No history yet.[/]")
            return

        stats_table = Table(title="HONEYMOON Statistics", border_style="cyan")
        stats_table.add_column("Metric")
        stats_table.add_column("Value")

        stats_table.add_row("Total runs", str(s["total_runs"]))
        stats_table.add_row("Success rate", f"{s['success_rate']}%")
        stats_table.add_row("Total cost", f"${s['total_cost']:.4f}")
        stats_table.add_row("Total tokens", f"{s['total_tokens']:,}")
        stats_table.add_row("Avg cost/run", f"${s['avg_cost_per_run']:.4f}")

        console.print(stats_table)

        if s.get("statuses"):
            status_table = Table(title="Status Breakdown", border_style="dim")
            status_table.add_column("Status")
            status_table.add_column("Count")
            for status_name, cnt in sorted(s["statuses"].items(), key=lambda x: -x[1]):
                status_table.add_row(status_name, str(cnt))
            console.print(status_table)

        return

    # Show recent entries
    entries = hist.get_recent(count)
    if not entries:
        console.print("[dim]No history yet. Run some tasks first.[/]")
        return

    table = Table(title=f"Recent Runs (last {count})", border_style="cyan")
    table.add_column("Time", style="dim")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Cost")
    table.add_column("Notes")

    for entry in reversed(entries):
        ts = entry.get("timestamp", "?")[:19]
        status = entry.get("status", "?")
        color = {"pr_created": "green", "committed": "yellow"}.get(status, "red")
        budget = entry.get("budget", {})
        cost = f"${budget.get('estimated_cost', 0):.4f}"

        notes = ""
        events = entry.get("events_summary", {})
        if events.get("fix_attempts", 0) > 0:
            notes += f"fixes:{events['fix_attempts']} "
        if events.get("security_verdict"):
            notes += f"sec:{events['security_verdict']} "
        if entry.get("error"):
            notes += entry["error"][:40]

        table.add_row(ts, entry.get("task_id", "?"), f"[{color}]{status}[/]", cost, notes)

    console.print(table)

# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


@app.command()
def compare(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    task_a: str = typer.Argument(..., help="First task ID to compare"),
    task_b: str = typer.Argument(..., help="Second task ID to compare"),
):
    """Compare two task runs — cost, loop steps, planner accuracy, tool divergence."""
    _configure_logging(False)
    repo = repo.resolve()
    hist = TaskHistory(repo)
    all_entries = hist.get_all()
    entry_a = next((e for e in all_entries if e.get("task_id") == task_a), None)
    entry_b = next((e for e in all_entries if e.get("task_id") == task_b), None)
    if not entry_a:
        console.print(f"[red]Task '{task_a}' not found in history.[/]")
        raise typer.Exit(1)
    if not entry_b:
        console.print(f"[red]Task '{task_b}' not found in history.[/]")
        raise typer.Exit(1)

    def _budget(e: dict) -> dict:
        return e.get("budget", {})

    def _events(e: dict) -> dict:
        return e.get("events_summary", {})

    def _quality(e: dict) -> int:
        q = e.get("quality_score", {})
        return q.get("score", 0) if isinstance(q, dict) else int(q or 0)

    def _cost(e: dict) -> float:
        return _budget(e).get("estimated_cost", 0.0)

    def _tokens(e: dict) -> int:
        return _budget(e).get("total_tokens", 0)

    def _fix_attempts(e: dict) -> int:
        return _events(e).get("fix_attempts", 0)

    def _loop_steps(e: dict) -> int:
        return _budget(e).get("role_usage", {}).get("implementer", 0)

    # --- Header ---
    console.print(Panel(
        f"[bold]Comparing:[/] [cyan]{task_a}[/] vs [cyan]{task_b}[/]",
        title="⚡ HONEYMOON Compare",
        border_style="bright_green",
    ))

    # --- Side-by-side metrics table ---
    table = Table(border_style="cyan", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column(task_a, style="cyan")
    table.add_column(task_b, style="magenta")

    def _delta(val_a: float, val_b: float, lower_is_better: bool = True) -> str:
        if val_a == val_b:
            return "="
        better = val_a < val_b if lower_is_better else val_a > val_b
        arrow = "▲" if val_a > val_b else "▼"
        color = "green" if better else "red"
        return f"[{color}]{arrow}[/]"

    cost_a, cost_b = _cost(entry_a), _cost(entry_b)
    tok_a, tok_b = _tokens(entry_a), _tokens(entry_b)
    fix_a, fix_b = _fix_attempts(entry_a), _fix_attempts(entry_b)
    q_a, q_b = _quality(entry_a), _quality(entry_b)
    status_a = entry_a.get("status", "?")
    status_b = entry_b.get("status", "?")

    table.add_row("Status", status_a, status_b)
    table.add_row("Cost", f"${cost_a:.4f} {_delta(cost_a, cost_b)}", f"${cost_b:.4f}")
    table.add_row("Tokens", f"{tok_a:,} {_delta(tok_a, tok_b)}", f"{tok_b:,}")
    table.add_row("Debug attempts", f"{fix_a} {_delta(fix_a, fix_b)}", f"{fix_b}")
    table.add_row(
        "Quality score",
        f"{q_a} {_delta(q_a, q_b, lower_is_better=False)}",
        f"{q_b}",
    )
    console.print(table)

    # --- Planner accuracy ---
    def _planner_accuracy(e: dict) -> tuple[int, int]:
        evs = e.get("events_summary", {})
        planned = evs.get("plan_steps", 0)
        return planned, evs.get("fix_attempts", 0)

    pa_a, err_a = _planner_accuracy(entry_a)
    pa_b, err_b = _planner_accuracy(entry_b)
    console.print("\n[bold]Planner:[/]")
    console.print(f"  {task_a}: {pa_a} plan steps, {err_a} fix attempt(s)")
    console.print(f"  {task_b}: {pa_b} plan steps, {err_b} fix attempt(s)")

    # --- Budget role breakdown ---
    roles_a = _budget(entry_a).get("role_usage", {})
    roles_b = _budget(entry_b).get("role_usage", {})
    all_roles = sorted(set(list(roles_a.keys()) + list(roles_b.keys())))
    if roles_a or roles_b:
        role_table = Table(title="Token usage by role", border_style="dim")
        role_table.add_column("Role")
        role_table.add_column(task_a, style="cyan")
        role_table.add_column(task_b, style="magenta")
        for role in all_roles:
            ra = roles_a.get(role, 0)
            rb = roles_b.get(role, 0)
            role_table.add_row(role, f"{ra:,}", f"{rb:,}")
        console.print(role_table)

    # --- Divergence hint ---
    console.print("\n[bold]Divergence summary:[/]")
    if cost_a > cost_b * 2:
        console.print(
            f"  [yellow]⚠  {task_a} cost {cost_a / cost_b:.1f}× more than {task_b}[/]"
        )
    if fix_a > fix_b:
        console.print(
            f"  [yellow]⚠  {task_a} needed {fix_a - fix_b} more debug attempt(s)[/]"
        )
    if fix_a == 0 and fix_b == 0 and cost_a > cost_b:
        console.print(
            "  [dim]Both converged without debug loops."
            " Cost difference likely in implementer exploration.[/]"
        )
    if q_a < 50:
        console.print(
            f"  [red]✗  {task_a} quality score is low ({q_a})"
            " — check for breaker trips or parse errors.[/]"
        )
    if q_b < 50:
        console.print(
            f"  [red]✗  {task_b} quality score is low ({q_b})"
            " — check for breaker trips or parse errors.[/]"
        )
    if q_a >= 80 and q_b >= 80:
        console.print("  [green]✓  Both runs converged cleanly.[/]")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@app.command()
def audit(
    repo: Path = typer.Option(..., help="Path to the repository to audit"),
    kind: str = typer.Option(None, help="Filter by finding kind (e.g. missing_doc, todo, dead_code, dependency_vuln)"),
    category: str = typer.Option(None, help="Filter by category: security, bug, test, refactor, cleanup, docs, feature"),
    scout: bool = typer.Option(False, "--scout", "-s", help="Enable Scout Brain — LLM-powered creative analysis for feature ideas"),
    dry_run: bool = typer.Option(False, help="Print findings without generating task files"),
    output_dir: Path = typer.Option(None, help="Directory to write task YAMLs (default: .honeymoon/tasks/queue)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """
    Scout — Autonomous codebase analysis engine.

    Scans your repository across multiple layers and generates
    prioritized, batch-ready HONEYMOON task files.
    """
    from honeymoon.auditor import Scanner, TaskWriter
    from honeymoon.router import Router

    _configure_logging(verbose)

    repo_path = repo.resolve()
    if not repo_path.exists():
        console.print(f"[red]Repository not found: {repo_path}[/]")
        raise typer.Exit(1)

    layer_desc = "static + scout" if scout else "static"
    console.print(f"\n[bold cyan]SCOUT[/] [dim]Scanning {repo_path.name} [layers: {layer_desc}]...[/]")

    scanner = Scanner(repo_path)
    result = scanner.scan()

    summary = result.summary()

    # Summary panel
    summary_lines = [
        f"Files scanned: {summary['files_scanned']}",
        f"Total findings: {summary['total']}",
    ]

    console.print(Panel(
        "\n".join(summary_lines),
        title="[bold cyan]Scout Scan Results[/]",
        border_style="cyan",
    ))

    # Apply filters
    findings = result.findings
    if kind:
        findings = [f for f in findings if getattr(f, "kind", None) == kind]
        console.print(f"  [dim]Filtered to {len(findings)} findings of kind '{kind}'[/]")
    if category:
        findings = [f for f in findings if getattr(f, "category", None) == category]
        console.print(f"  [dim]Filtered to {len(findings)} findings in category '{category}'[/]")

    if not findings and not scout:
        console.print("[green]No findings. Codebase looks clean![/]")
        return

    # Findings table
    if findings:
        table = Table(title="Findings", border_style="yellow")
        table.add_column("Cat", style="dim", width=8)
        table.add_column("Kind", style="dim", width=18)
        table.add_column("File", width=35)
        table.add_column("Line", style="dim", width=5)
        table.add_column("Description")
        table.add_column("Sev", width=6)

        # Sort for display: severity desc
        display_findings = sorted(
            findings,
            key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(getattr(f, "severity", "low"), 3)
        )

        for f in display_findings[:80]:
            sev_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(getattr(f, "severity", "low"), "dim")
            cat_color = {"security": "red", "bug": "yellow", "feature": "green", "test": "cyan"}.get(getattr(f, "category", "refactor"), "dim")
            table.add_row(
                f"[{cat_color}]{getattr(f, 'category', 'refactor')}[/]",
                getattr(f, "kind", "unknown"),
                getattr(f, "file", "unknown"),
                str(getattr(f, "line", "?")),
                getattr(f, "description", "")[:80],
                f"[{sev_color}]{getattr(f, 'severity', 'low')}[/]",
            )

        console.print(table)

        if len(findings) > 80:
            console.print(f"[dim]... and {len(findings) - 80} more findings[/]")

    if dry_run and not scout:
        console.print("\n[yellow]Dry run — no task files written.[/]")
        return

    # Generate task files
    out_dir = output_dir or (repo_path / ".honeymoon" / "tasks" / "queue")
    console.print(f"\n[bold cyan]SCOUT[/] [dim]Generating prioritized task files → {out_dir}[/]")

    config = load_config(repo_path)
    router = Router(config)

    # In scout mode, we let the LLM generate tasks even if static findings are empty
    if scout:
        console.print("[bold cyan]SCOUT[/] [dim]Activating Scout Brain (Layer 3)...[/]")

    result.findings = findings
    writer = TaskWriter(router, out_dir, dry_run=dry_run)

    with console.status("[bold cyan]Scout Brain is thinking... (this may take 15-30s)[/]", spinner="point"):
        written = writer.write_tasks(result)

    if dry_run and scout:
         console.print("\n[yellow]Dry run — simulated brain output (no files written).[/]")
         return

    if written:
        console.print(Panel(
            "\n".join(f"  {p.name}" for p in written),
            title=f"[bold green]{len(written)} task files written[/]",
            border_style="green",
        ))

    console.print("\n[bold]Next steps:[/]")
    console.print(f"  1. Run batch:        [cyan]honeymoon batch --repo {repo_path} --tasks-dir {out_dir}[/]")
    console.print(f"  2. Monitor:          [cyan]honeymoon history --repo {repo_path} --stats[/]")

@app.command()
def investigate(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    objective: str = typer.Option(..., "--objective", "-o", help="What to investigate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Investigate a codebase — read-only forensics with a signed report."""
    from honeymoon.mission import load_mission
    from honeymoon.report import write_report

    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    config = load_config(repo)
    mission = load_mission("investigate", repo)

    console.print(f"[bold cyan]Mission: {mission.name}[/]")
    console.print(f"[dim]Objective: {objective}[/]\n")

    task = Task.from_interactive(objective)

    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        auto_approve=True,
        mission=mission,
    )

    result = controller.run(task)

    # Write signed report
    findings = result.get("implementation", {})
    verification = result.get("security", {})
    budget = result.get("budget", {})

    report_path = write_report(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        mission_name=mission.name,
        objective=objective,
        findings=findings,
        verification=verification,
        budget=budget,
    )

    # Emit findings as prelude decisions for cross-session persistence
    finding_list = findings.get("findings", [])
    if finding_list:
        _emit_prelude_decisions(repo, finding_list, objective)

    console.print("\n[bold green]🍯 Investigation complete.[/]")
    console.print(f"  [bold]Report:[/]    {report_path}")
    console.print(f"  [bold]Findings:[/]  {len(finding_list)}")
    if finding_list:
        for f in finding_list:
            sev = f.get("severity", "info").upper()
            sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue", "INFO": "dim"}.get(sev, "dim")
            console.print(f"    [{sev_color}]{sev}[/] {f.get('title', '?')}")
    console.print(f"  [bold]Cost:[/]     ${budget.get('estimated_cost', 0):.4f}")
    console.print("  [bold]Verify:[/]   check .honeymoon/keys/verify.pub against report signature")


@app.command()
def swarm(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    objective: str = typer.Option(None, "--objective", "-o", help="Task objective to decompose and swarm"),
    task_file: Optional[Path] = typer.Option(None, "--task-file", "-f", help="Path to task YAML"),
    ants: int = typer.Option(3, "--ants", "-a", help="Max concurrent ant workers"),
    allow_core: bool = typer.Option(False, "--allow-core"),
    test_cmd: Optional[str] = typer.Option(None, "--test", "-t"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Swarm mode — decompose a task and run sub-tasks in parallel."""
    from honeymoon.decomposer import TaskDecomposer
    from honeymoon.router import Router
    from honeymoon.swarm import run_swarm

    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    config = load_config(repo)

    # Resolve objective
    if task_file:
        task = Task.from_yaml(task_file)
        obj = task.objective
        constraints = task.constraints
    elif objective:
        obj = objective
        constraints = []
    else:
        console.print("[red]Specify --objective or --task-file[/]")
        raise typer.Exit(1)

    if not test_cmd:
        test_cmd = _detect_test_command(repo)

    # Initialize audit + sentry
    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    console.print("[bold]Decomposing task...[/]\n")

    router = Router(config)
    decomposer = TaskDecomposer(router, config)

    subtasks = decomposer.decompose(
        objective=obj,
        repo_path=str(repo),
        working_dir=str(repo),
        constraints=constraints,
    )

    if not subtasks:
        console.print("[red]Decomposer produced no sub-tasks.[/]")
        raise typer.Exit(1)

    console.print(f"[cyan]Decomposed into {len(subtasks)} sub-tasks:[/]")
    for st in subtasks:
        dep_str = f" (depends: {', '.join(st.depends_on)})" if st.depends_on else ""
        console.print(f"  [dim]{st.subtask_id}[/]: {len(st.files)} files{dep_str}")

    results = run_swarm(
        repo_path=repo,
        subtasks=subtasks,
        max_ants=ants,
        allow_core=allow_core,
        test_command=test_cmd,
    )

    failures = sum(1 for r in results if r.status not in ("pr_created", "committed", "merged"))
    if failures:
        raise typer.Exit(1)


@app.command()
def serve(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    port: int = typer.Option(4200, "--port", "-p", help="WebSocket port"),
):
    """Start the dashboard daemon — streams live events to the Next.js dashboard."""
    from honeymoon.daemon import HoneymoonDaemon

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    daemon = HoneymoonDaemon(repo_path=repo, port=port)
    daemon.run()


@app.command()
def doctor():
    from honeymoon.registry import AGENT_REGISTRY
    from honeymoon.step_handlers import STEP_HANDLERS
    from honeymoon.config_loader import load_config
    from rich.console import Console
    from rich.table import Table
    import sys
    config = load_config()
    console = Console()
    table = Table('Role', 'Registry', 'Handler')
    failed = False
    for step in config.pipeline:
        role = step.agent_role
        in_reg = role in AGENT_REGISTRY
        in_hand = role in STEP_HANDLERS
        if not in_reg or not in_hand:
            failed = True
        table.add_row(role, '[green]✓[/green]' if in_reg else '[red]✗[/red]', '[green]✓[/green]' if in_hand else '[red]✗[/red]')
    console.print(table)
    if failed:
        sys.exit(1)


@app.command()
def harden(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    scenario: Optional[str] = typer.Option(None, "--scenario", "-s", help="Attack scenario (auto-detected if omitted)"),
    posture: bool = typer.Option(False, "--posture", "-p", help="Show posture summary only (no simulation)"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="Auto-open HTML report"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Continuous adversarial hardening — simulate, diff, track posture over time."""
    from honeymoon.ledger import append_ledger, posture_summary, read_ledger
    from honeymoon.mission import load_mission
    from honeymoon.report import write_report

    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    # Posture-only mode
    if posture:
        summary = posture_summary(repo)
        entries = read_ledger(repo)
        console.print(f"\n[bold cyan]🛡️  Security Posture — {repo.name}[/]\n")
        console.print(summary)
        if entries:
            console.print(f"\n[dim]Ledger: {repo / '.honeymoon' / 'ledger.jsonl'}[/]")
            # Show trend sparkline
            scores = [e.get("posture_score", 0) for e in entries]
            if len(scores) > 1:
                spark = " ".join(
                    f"[{'green' if s >= 70 else 'yellow' if s >= 40 else 'red'}]{s}[/]"
                    for s in scores[-10:]
                )
                console.print(f"  Trend: {spark}")
        return

    # Run simulation
    config = load_config(repo)
    mission = load_mission("simulate", repo)

    if not scenario:
        scenario = _auto_detect_attack_scenario(repo)

    # Check ledger for previous runs
    entries = read_ledger(repo)
    run_number = len(entries) + 1

    console.print(f"\n[bold red]🛡️  Hardening Run #{run_number}[/]")
    if entries:
        prev = entries[-1]
        console.print(
            f"  [dim]Previous: score={prev.get('posture_score', '?')}/100, "
            f"{prev.get('finding_count', '?')} findings[/]"
        )
    console.print(f"  [dim]Scenario: {scenario[:80]}...[/]\n")

    task = Task.from_interactive(scenario)
    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        auto_approve=True,
        mission=mission,
    )

    result = controller.run(task)

    findings = result.get("implementation", {})
    verification = result.get("security", {})
    budget = result.get("budget", {})
    finding_list = findings.get("findings", [])

    # Write report
    report_path = write_report(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        mission_name=f"harden-{run_number}",
        objective=scenario,
        findings=findings,
        verification=verification,
        budget=budget,
    )

    # Append to ledger
    ledger_entry = append_ledger(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        mission="harden",
        findings=finding_list,
        verification=verification,
        budget=budget,
    )

    # Persist to prelude
    if finding_list:
        _emit_prelude_decisions(repo, finding_list, scenario)

    # Summary
    score = ledger_entry.get("posture_score", "?")
    trend = ledger_entry.get("trend", "?")
    trend_icon = {"improving": "[green]\u2191[/]", "degrading": "[red]\u2193[/]", "stable": "[yellow]\u2192[/]"}.get(trend, "?")
    new_count = ledger_entry.get("new_count", 0)
    resolved_count = ledger_entry.get("resolved_count", 0)

    console.print(f"\n[bold]🛡️  Hardening Run #{run_number} Complete[/]")
    console.print(f"  [bold]Posture:[/]    {score}/100 {trend_icon} {trend}")
    console.print(f"  [bold]Findings:[/]   {len(finding_list)} total")
    if new_count:
        console.print(f"  [bold red]New:[/]        {new_count} new issues surfaced")
    if resolved_count:
        console.print(f"  [bold green]Resolved:[/]   {resolved_count} issues no longer present")
    console.print(f"  [bold]Report:[/]     {report_path}")
    console.print(f"  [bold]Cost:[/]       ${budget.get('estimated_cost', 0):.4f}")

    if finding_list:
        console.print("\n  [dim]Attack chains:[/]")
        for f in finding_list:
            sev = f.get("severity", "info").upper()
            sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue", "INFO": "dim"}.get(sev, "dim")
            fp = _fingerprint_display(f, ledger_entry)
            console.print(f"    [{sev_color}]{sev}[/] {f.get('title', '?')} {fp}")

    html_path = report_path.with_suffix(".html")
    if open_report and html_path.exists():
        import webbrowser
        webbrowser.open(f"file://{html_path}")


def _fingerprint_display(finding: dict, entry: dict) -> str:
    """Show whether a finding is new, persistent, or resolved."""
    from honeymoon.ledger import _fingerprint
    fp = _fingerprint(finding)
    if fp in entry.get("new_findings", []):
        return "[bold red](NEW)[/]"
    return "[dim](known)[/]"


@app.command()
def simulate(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    scenario: Optional[str] = typer.Option(None, "--scenario", "-s", help="Attack scenario to simulate"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="Auto-open HTML report in browser"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Red/Blue adversarial simulation — trace exploitation chains with signed events."""
    from honeymoon.mission import load_mission
    from honeymoon.report import write_report

    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    config = load_config(repo)
    mission = load_mission("simulate", repo)

    if not scenario:
        scenario = _auto_detect_attack_scenario(repo)
        console.print(f"[dim]Auto-detected scenario: {scenario[:100]}...[/]\n")

    console.print(f"[bold red]Mission: {mission.name}[/]")
    console.print(f"[dim]Scenario: {scenario}[/]\n")

    task = Task.from_interactive(scenario)

    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        auto_approve=True,
        mission=mission,
    )

    result = controller.run(task)

    findings = result.get("implementation", {})
    verification = result.get("security", {})
    budget = result.get("budget", {})

    report_path = write_report(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        mission_name="simulate",
        objective=scenario,
        findings=findings,
        verification=verification,
        budget=budget,
    )

    finding_list = findings.get("findings", [])
    if finding_list:
        _emit_prelude_decisions(repo, finding_list, scenario)

    console.print("\n[bold red]🎯 Simulation complete.[/]")
    console.print(f"  [bold]Report:[/]      {report_path}")
    console.print(f"  [bold]Chains:[/]      {len(finding_list)} attack chains traced")
    if finding_list:
        for f in finding_list:
            sev = f.get("severity", "info").upper()
            sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue", "INFO": "dim"}.get(sev, "dim")
            console.print(f"    [{sev_color}]{sev}[/] {f.get('title', '?')}")
    verdict = verification.get("verdict", "?") if verification else "?"
    verdict_map = {"pass": "confirmed", "warn": "partial", "block": "disputed"}
    console.print(f"  [bold]Blue Team:[/]   {verdict_map.get(verdict, verdict)}")
    console.print(f"  [bold]Cost:[/]       ${budget.get('estimated_cost', 0):.4f}")

    html_path = report_path.with_suffix(".html")
    if open_report and html_path.exists():
        import webbrowser
        webbrowser.open(f"file://{html_path}")


def _auto_detect_attack_scenario(repo: Path) -> str:
    """Auto-detect an attack scenario based on repo contents."""
    has_auth = False
    has_api = False
    has_db = False
    has_shell = False

    for f in repo.rglob("*.py"):
        if any(exc in f.parts for exc in [".git", "node_modules", ".venv", "__pycache__", ".honeymoon"]):
            continue
        try:
            content = f.read_text(errors="ignore")[:5000]
            if "auth" in content.lower() or "jwt" in content.lower() or "token" in content.lower():
                has_auth = True
            if "fastapi" in content.lower() or "flask" in content.lower() or "django" in content.lower():
                has_api = True
            if "sql" in content.lower() or "database" in content.lower() or "supabase" in content.lower():
                has_db = True
            if "subprocess" in content or "os.system" in content or "shell=True" in content:
                has_shell = True
        except Exception:
            continue

    for f in repo.rglob("*.ts"):
        if any(exc in f.parts for exc in [".git", "node_modules", ".honeymoon"]):
            continue
        try:
            content = f.read_text(errors="ignore")[:5000]
            if "auth" in content.lower() or "session" in content.lower():
                has_auth = True
            if "fetch(" in content or "axios" in content:
                has_api = True
        except Exception:
            continue

    parts = ["Simulate an attacker targeting this codebase."]
    if has_shell:
        parts.append("Focus on command injection: trace all paths from user input to subprocess/shell execution.")
    if has_auth:
        parts.append("Attempt auth bypass: find ways to access protected resources without valid credentials.")
    if has_db:
        parts.append("Test for SQL injection and data exfiltration paths.")
    if has_api:
        parts.append("Map the API attack surface: identify unprotected endpoints and input validation gaps.")
    if not any([has_shell, has_auth, has_db, has_api]):
        parts.append("Identify the primary attack surface and trace the most dangerous exploitation chain from external input to sensitive operations.")

    return " ".join(parts)


@app.command()
def deep(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    fix: bool = typer.Option(False, "--fix", help="Enable autonomous remediation (creates PRs)"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="Auto-open HTML report in browser"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Deep scan — audit + investigate + SPEC.md. Add --fix for autonomous remediation."""
    from honeymoon.auditor import Scanner
    from honeymoon.mission import load_mission
    from honeymoon.report import write_report, write_spec

    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    # Phase 1: Static audit
    console.print("\n[bold cyan]Phase 1 · AUDIT[/] [dim]Static analysis...[/]")
    scanner = Scanner(repo)
    scan_result = scanner.scan()
    console.print(
        f"  [dim]{scan_result.files_scanned} files scanned, "
        f"{len(scan_result.findings)} static findings[/]"
    )

    # Build focused objective from audit findings
    audit_summary = _build_audit_context(scan_result)

    # Phase 2: Investigation
    console.print("\n[bold cyan]Phase 2 · INVESTIGATE[/] [dim]Agent-powered forensics...[/]")
    config = load_config(repo)
    mission = load_mission("investigate", repo)

    objective = _auto_detect_objective(repo)
    if audit_summary:
        objective += f" Additionally, the static scanner found: {audit_summary}"

    task = Task.from_interactive(objective)
    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        auto_approve=True,
        mission=mission,
    )

    result = controller.run(task)

    findings = result.get("implementation", {})
    verification = result.get("security", {})
    budget = result.get("budget", {})

    # Write investigation report
    report_path = write_report(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        mission_name="deep-scan",
        objective=objective,
        findings=findings,
        verification=verification,
        budget=budget,
    )

    finding_list = findings.get("findings", [])
    if finding_list:
        _emit_prelude_decisions(repo, finding_list, objective)

    # Phase 3: SPEC.md — remediation plan
    console.print("\n[bold cyan]Phase 3 · SPEC[/] [dim]Remediation plan...[/]")
    spec_path = write_spec(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        investigation_findings=finding_list,
        audit_findings=scan_result.findings,
        verification=verification,
    )

    # Phase 4 (optional): Autonomous remediation
    if fix:
        console.print("\n[bold cyan]Phase 4 · FIX[/] [dim]Autonomous remediation...[/]")
        _run_remediation(repo, finding_list, scan_result.findings, verbose)

    # Summary
    console.print("\n[bold green]🍯 Deep scan complete.[/]")
    console.print(f"  [bold]Report:[/]    {report_path}")
    console.print(f"  [bold]SPEC:[/]      {spec_path}")
    console.print(f"  [bold]Findings:[/]  {len(finding_list)} investigation + {len(scan_result.findings)} static")
    if finding_list:
        for f in finding_list:
            sev = f.get("severity", "info").upper()
            sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue", "INFO": "dim"}.get(sev, "dim")
            console.print(f"    [{sev_color}]{sev}[/] {f.get('title', '?')}")
    console.print(f"  [bold]Cost:[/]     ${budget.get('estimated_cost', 0):.4f}")

    html_path = report_path.with_suffix(".html")
    if open_report and html_path.exists():
        import webbrowser
        webbrowser.open(f"file://{html_path}")


def _build_audit_context(scan_result) -> str:
    """Summarize audit findings into a focused context string for the investigator."""
    if not scan_result.findings:
        return ""

    # Group by severity
    by_sev: dict[str, list] = {}
    for f in scan_result.findings:
        by_sev.setdefault(f.severity, []).append(f)

    parts = []
    for sev in ["high", "medium", "low"]:
        items = by_sev.get(sev, [])
        if items:
            sample = items[:3]
            desc = "; ".join(f"{f.kind} in {f.file}:{f.line}" for f in sample)
            if len(items) > 3:
                desc += f" (+{len(items)-3} more)"
            parts.append(f"{sev.upper()}: {desc}")

    return " | ".join(parts)


def _run_remediation(repo: Path, investigation_findings: list, audit_findings: list, verbose: bool) -> None:
    """Generate task YAMLs from findings and run them through the pipeline."""
    import yaml

    tasks_dir = repo / ".honeymoon" / "tasks" / "queue"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    # Only remediate high/medium investigation findings
    actionable = [f for f in investigation_findings if f.get("severity") in ("critical", "high", "medium")]

    if not actionable:
        console.print("  [dim]No actionable findings to remediate.[/]")
        return

    written = []
    for i, finding in enumerate(actionable[:5]):  # Cap at 5 tasks
        task_id = f"fix-{finding.get('severity', 'med')}-{i+1}"
        title = finding.get("title", f"Fix finding {i+1}")
        evidence = finding.get("evidence", "")
        analysis = finding.get("analysis", "")

        task_data = {
            "id": task_id,
            "objective": f"Fix: {title}",
            "constraints": [
                "Do not break existing functionality",
                "Run tests after changes to verify nothing is broken",
                "Make the minimal change that addresses the finding",
                f"Evidence: {evidence[:300]}" if evidence else None,
                f"Analysis: {analysis[:300]}" if analysis else None,
            ],
            "acceptance": [
                "The security finding is addressed",
                "All existing tests still pass",
                "No new warnings introduced",
            ],
            "risk": "medium",
        }
        # Remove None constraints
        task_data["constraints"] = [c for c in task_data["constraints"] if c]

        task_path = tasks_dir / f"{task_id}.yaml"
        task_path.write_text(yaml.dump(task_data, default_flow_style=False, sort_keys=False))
        written.append(task_path)

    console.print(f"  [dim]Generated {len(written)} remediation tasks in {tasks_dir}[/]")
    for p in written:
        console.print(f"    [dim]{p.name}[/]")

    console.print("  [dim]Run: honeymoon batch --repo . to execute remediation[/]")


@app.command()
def scan(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the target repository"),
    objective: Optional[str] = typer.Option(None, "--objective", "-o", help="What to investigate (auto-detected if omitted)"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="Auto-open HTML report in browser"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Scan a codebase — one command, full investigation, beautiful report."""
    from honeymoon.mission import load_mission
    from honeymoon.report import write_report

    _print_banner()
    _configure_logging(verbose)

    repo = repo.resolve()
    if not repo.exists():
        console.print(f"[red]Repository not found: {repo}[/]")
        raise typer.Exit(1)

    # Auto-detect objective from repo context
    if not objective:
        objective = _auto_detect_objective(repo)
        console.print(f"[dim]Auto-detected objective: {objective}[/]\n")

    config = load_config(repo)
    mission = load_mission("investigate", repo)

    console.print(f"[bold cyan]Mission: {mission.name}[/]")
    console.print(f"[dim]Objective: {objective}[/]\n")

    task = Task.from_interactive(objective)

    AuditLogger(log_file=repo / ".honeymoon" / "logs" / "audit.jsonl")

    controller = Controller(
        repo_path=repo,
        config=config,
        auto_approve=True,
        mission=mission,
    )

    result = controller.run(task)

    findings = result.get("implementation", {})
    verification = result.get("security", {})
    budget = result.get("budget", {})

    report_path = write_report(
        repo_path=repo,
        run_id=result.get("run_id", task.task_id),
        mission_name=mission.name,
        objective=objective,
        findings=findings,
        verification=verification,
        budget=budget,
    )

    finding_list = findings.get("findings", [])
    if finding_list:
        _emit_prelude_decisions(repo, finding_list, objective)

    console.print("\n[bold green]🍯 Scan complete.[/]")
    console.print(f"  [bold]Report:[/]    {report_path}")
    console.print(f"  [bold]Findings:[/]  {len(finding_list)}")
    if finding_list:
        for f in finding_list:
            sev = f.get("severity", "info").upper()
            sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue", "INFO": "dim"}.get(sev, "dim")
            console.print(f"    [{sev_color}]{sev}[/] {f.get('title', '?')}")
    console.print(f"  [bold]Cost:[/]     ${budget.get('estimated_cost', 0):.4f}")

    # Auto-open HTML report
    html_path = report_path.with_suffix(".html")
    if open_report and html_path.exists():
        import webbrowser
        webbrowser.open(f"file://{html_path}")
        console.print(f"  [bold]Opened:[/]   {html_path}")


def _auto_detect_objective(repo: Path) -> str:
    """Auto-detect an investigation objective based on repo characteristics."""
    # Check for common patterns
    has_py = any(repo.rglob("*.py"))
    has_rs = any(repo.rglob("*.rs"))
    has_ts = any(repo.rglob("*.ts")) or any(repo.rglob("*.tsx"))
    has_docker = (repo / "Dockerfile").exists() or (repo / "docker-compose.yml").exists()

    parts = []
    parts.append("Map all security boundaries and trust zones.")

    if has_py or has_rs:
        parts.append("Trace every path from user input to shell execution or file system access.")
        parts.append("Identify any gaps in input validation or authorization checks.")
    if has_ts:
        parts.append("Check for XSS vectors, unsafe innerHTML, and unvalidated user input in components.")
    if has_docker:
        parts.append("Review container configuration for privilege escalation or exposed secrets.")

    parts.append("Flag any hardcoded credentials, API keys, or secrets.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Prelude Decision Emission
# ---------------------------------------------------------------------------

def _emit_prelude_decisions(repo: Path, findings: list[dict], objective: str) -> None:
    """Emit investigation findings as prelude decisions for cross-session persistence."""
    import shutil
    if not shutil.which("prelude"):
        return

    for finding in findings:
        title = finding.get("title", "Untitled finding")
        severity = finding.get("severity", "info").upper()
        evidence = finding.get("evidence", "")
        analysis = finding.get("analysis", "")

        # Only persist medium+ findings as decisions
        if severity in ("INFO", "LOW"):
            continue

        rationale = f"{analysis}\n\nEvidence: {evidence}" if evidence else analysis
        tags = f"honeymoon,investigate,{severity.lower()}"

        try:
            subprocess.run(
                [
                    "prelude", "decision", f"[{severity}] {title}",
                    "--rationale", rationale[:500],
                    "--status", "proposed",
                    "--author", "honeymoon-analyst",
                    "--tags", tags,
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass  # Non-fatal — prelude integration is best-effort


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_test_command(repo: Path) -> str | None:
    """Auto-detect the test command based on repo contents."""
    if (repo / "Cargo.toml").exists():
        return "cargo test"
    if (repo / "package.json").exists():
        return "npm test"
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        return "python -m pytest"
    if (repo / "go.mod").exists():
        return "go test ./..."
    if (repo / "Makefile").exists():
        return "make test"
    return None


def _configure_logging(verbose: bool) -> None:
    logger.remove()
    if verbose:
        logger.add(
            lambda msg: console.print(f"[dim]{msg}[/]", highlight=False),
            level="DEBUG",
            format="{time:HH:mm:ss} | {level:<7} | {message}",
        )
    else:
        logger.add(
            lambda msg: console.print(f"[dim]{msg}[/]", highlight=False),
            level="WARNING",
            format="{message}",
        )


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()