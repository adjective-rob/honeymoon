"""
GLITCHLAB Controller — The Brainstem

The most important piece. It is NOT smart. It is deterministic.

Responsibilities:
  - Pull next task
  - Create isolated worktree
  - Assign agent roles in order
  - Track token budget
  - Track retry attempts
  - Enforce stop conditions
  - Open PR
  - Clean up workspace

It never writes code. It only coordinates.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from glitchlab.agents import AgentContext
from glitchlab.agents.archivist import ArchivistAgent
from glitchlab.agents.debugger import DebuggerAgent
from glitchlab.agents.implementer import ImplementerAgent
from glitchlab.agents.planner import PlannerAgent
from glitchlab.agents.release import ReleaseAgent
from glitchlab.agents.security import SecurityAgent
from glitchlab.config_loader import GlitchLabConfig, load_config
from glitchlab.governance import BoundaryEnforcer, BoundaryViolation
from glitchlab.history import TaskHistory
from glitchlab.indexer import build_index
from glitchlab.router import BudgetExceededError, Router
from glitchlab.prelude import PreludeContext
from glitchlab.workspace import Workspace
from glitchlab.workspace.tools import ToolExecutor, ToolViolationError

console = Console()


# ---------------------------------------------------------------------------
# Task Definition
# ---------------------------------------------------------------------------

class Task:
    """Represents a single unit of work for GLITCHLAB."""

    def __init__(
        self,
        task_id: str,
        objective: str,
        constraints: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        risk_level: str = "low",
        source: str = "local",
    ):
        self.task_id = task_id
        self.objective = objective
        self.constraints = constraints or []
        self.acceptance_criteria = acceptance_criteria or ["Tests pass", "Clean diff"]
        self.risk_level = risk_level
        self.source = source

    @classmethod
    def from_yaml(cls, path: Path) -> "Task":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            task_id=data.get("id", path.stem),
            objective=data["objective"],
            constraints=data.get("constraints", []),
            acceptance_criteria=data.get("acceptance", []),
            risk_level=data.get("risk", "low"),
            source="local-file",
        )

    @classmethod
    def from_interactive(cls, objective: str) -> "Task":
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return cls(
            task_id=f"interactive-{ts}",
            objective=objective,
            source="interactive",
        )

    @classmethod
    def from_github_issue(cls, repo_path: Path, issue_number: int) -> "Task":
        """Fetch issue from GitHub CLI."""
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json",
             "title,body,labels,number"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to fetch issue #{issue_number}: {result.stderr}")

        data = json.loads(result.stdout)
        labels = [l["name"] for l in data.get("labels", [])]

        return cls(
            task_id=f"gh-{issue_number}",
            objective=f"{data['title']}\n\n{data.get('body', '')}",
            risk_level="high" if "core" in labels else "low",
            source="github",
        )


# ---------------------------------------------------------------------------
# File Context Builder
# ---------------------------------------------------------------------------

def gather_file_context(working_dir: Path, files: list[str], max_lines: int = 200) -> dict[str, str]:
    """Read file contents for agent context. Truncates large files."""
    context = {}
    for fpath in files:
        full = working_dir / fpath
        if full.exists() and full.is_file():
            try:
                lines = full.read_text().splitlines()
                if len(lines) > max_lines:
                    content = "\n".join(lines[:max_lines]) + f"\n\n... truncated ({len(lines)} lines total)"
                else:
                    content = "\n".join(lines)
                context[fpath] = content
            except Exception as e:
                context[fpath] = f"(could not read: {e})"
    return context


# ---------------------------------------------------------------------------
# Change Applicator (supports full content + unified diffs)
# ---------------------------------------------------------------------------

def apply_changes(working_dir: Path, changes: list[dict]) -> list[str]:
    """
    Apply implementation changes to the workspace.

    Supports three modes per change:
      - content: full file replacement
      - patch: unified diff applied via `git apply`
      - delete: remove file
    """
    applied = []
    for change in changes:
        fpath = working_dir / change["file"]
        action = change.get("action", "modify")

        if action == "create":
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(change.get("content", ""))
            applied.append(f"CREATE {change['file']}")

        elif action == "delete":
            if fpath.exists():
                fpath.unlink()
                applied.append(f"DELETE {change['file']}")

        elif action == "modify":
            # Prefer patch if available, fall back to full content
            patch = change.get("patch")
            content = change.get("content")

            if patch:
                success = _apply_patch(working_dir, patch)
                if success:
                    applied.append(f"PATCH {change['file']}")
                elif content:
                    # Patch failed, fall back to full content
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(content)
                    applied.append(f"MODIFY {change['file']} (patch failed, used full content)")
                else:
                    applied.append(f"FAIL {change['file']} (patch failed, no fallback)")
            elif content:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content)
                applied.append(f"MODIFY {change['file']}")
            else:
                applied.append(f"SKIP {change['file']} (no content or patch provided)")

    return applied


def _apply_patch(working_dir: Path, patch: str) -> bool:
    """
    Apply a unified diff via git apply.
    Returns True on success.
    """
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", dir=working_dir, delete=False
        ) as f:
            f.write(patch)
            patch_file = f.name

        result = subprocess.run(
            ["git", "apply", "--check", patch_file],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            # Check passed, apply for real
            result = subprocess.run(
                ["git", "apply", patch_file],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True

        logger.warning(f"[PATCH] git apply failed: {result.stderr}")
        return False

    except Exception as e:
        logger.warning(f"[PATCH] Exception applying patch: {e}")
        return False
    finally:
        try:
            Path(patch_file).unlink(missing_ok=True)
        except Exception:
            pass


def apply_tests(working_dir: Path, tests: list[dict]) -> list[str]:
    """Apply test file changes."""
    applied = []
    for test in tests:
        fpath = working_dir / test["file"]
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(test.get("content", ""))
        applied.append(f"TEST {test['file']}")
    return applied


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class Controller:
    """
    The GLITCHLAB brainstem.

    Deterministic orchestration of the agent pipeline:
      Plan → Implement → Test → Debug Loop → Security → Release → PR
    """

    def __init__(
        self,
        repo_path: Path,
        config: GlitchLabConfig | None = None,
        allow_core: bool = False,
        auto_approve: bool = False,
        test_command: str | None = None,
    ):
        self.repo_path = repo_path.resolve()
        self.config = config or load_config(repo_path)
        self.allow_core = allow_core
        self.auto_approve = auto_approve
        self.test_command = test_command

        # Initialize components
        self.router = Router(self.config)
        self.boundary = BoundaryEnforcer(self.config.boundaries.protected_paths)

        # Initialize agents
        self.planner = PlannerAgent(self.router)
        self.implementer = ImplementerAgent(self.router)
        self.debugger = DebuggerAgent(self.router)
        self.security = SecurityAgent(self.router)
        self.release = ReleaseAgent(self.router)
        self.archivist = ArchivistAgent(self.router)

        # Task state
        self._task: Task | None = None
        self._workspace: Workspace | None = None
        self._event_log: list[dict] = []
        self._repo_index_context: str = ""

        # History tracking
        self._history = TaskHistory(self.repo_path)

        # Prelude integration — codebase context
        self._prelude = PreludeContext(self.repo_path)
        self._prelude_prefix: str = ""

    def run(self, task: Task) -> dict[str, Any]:
        """Execute the full agent pipeline for a task."""
        self._task = task
        result: dict[str, Any] = {
            "task_id": task.task_id,
            "status": "pending",
            "events": [],
        }

        console.print(Panel(
            f"[bold green]Task:[/] {task.objective[:120]}\n"
            f"[bold]ID:[/] {task.task_id}  |  [bold]Source:[/] {task.source}  |  "
            f"[bold]Risk:[/] {task.risk_level}",
            title="⚡ GLITCHLAB",
            subtitle="Build Weird. Ship Clean.",
            border_style="bright_green",
        ))

        try:
            # 1. Create workspace
            self._workspace = Workspace(
                self.repo_path, task.task_id,
                self.config.workspace.worktree_dir,
            )
            ws_path = self._workspace.create()
            self._log_event("workspace_created", {"path": str(ws_path)})

            tools = ToolExecutor(
                allowed_tools=self.config.allowed_tools,
                blocked_patterns=self.config.blocked_patterns,
                working_dir=ws_path,
            )

            # 1.5. Gather Prelude context (codebase memory)
            if self._prelude.available:
                console.print("\n[bold dim]📋 [PRELUDE] Loading project context...[/]")
                self._prelude.refresh()
                self._prelude_prefix = self._prelude.build_agent_prefix()
                if self._prelude_prefix:
                    summary = self._prelude.summary()
                    console.print(
                        f"  [dim]Context loaded: {len(summary.get('files', []))} files, "
                        f"{summary.get('decisions_count', 0)} ADRs[/]"
                    )
                    self._log_event("prelude_loaded", summary)

                    # Merge Prelude constraints into task constraints
                    prelude_constraints = self._prelude.get_constraints()
                    if prelude_constraints:
                        task.constraints = list(set(task.constraints + prelude_constraints))

            # 1.6. Build repo index (file discovery)
            console.print("\n[bold dim]🗂  [INDEX] Scanning repository...[/]")
            repo_index = build_index(ws_path)
            self._repo_index_context = repo_index.to_agent_context(max_files=200)
            console.print(
                f"  [dim]{repo_index.total_files} files, "
                f"{len(repo_index.crates)} crates, "
                f"{len(repo_index.languages)} languages[/]"
            )
            self._log_event("repo_indexed", {
                "total_files": repo_index.total_files,
                "languages": repo_index.languages,
                "crates": repo_index.crates,
            })

            # 1.7. Load failure context from history
            failure_context = self._history.build_failure_context()
            if failure_context:
                console.print("  [dim]Loaded recent failure patterns for planner[/]")

            # 2. Plan
            plan = self._run_planner(task, ws_path, failure_context)
            if plan.get("parse_error"):
                result["status"] = "plan_failed"
                return result

            # 3. Boundary check
            try:
                violations = self.boundary.check_plan(plan, self.allow_core)
                if violations:
                    self._log_event("core_override", {"files": violations})
                    console.print(f"[yellow]⚠ Core override granted for: {violations}[/]")
            except BoundaryViolation as e:
                console.print(f"[red]🚫 {e}[/]")
                result["status"] = "boundary_violation"
                return result

            # 4. Implement
            impl = self._run_implementer(task, plan, ws_path)
            if impl.get("parse_error"):
                result["status"] = "implementation_failed"
                return result

            # Apply changes to workspace
            applied = apply_changes(ws_path, impl.get("changes", []))
            applied += apply_tests(ws_path, impl.get("tests_added", []))
            for a in applied:
                console.print(f"  [cyan]{a}[/]")

            # 5. Test + Debug Loop
            if self.test_command:
                test_ok = self._run_fix_loop(task, ws_path, tools, impl)
                if not test_ok:
                    result["status"] = "tests_failed"
                    console.print("[red]❌ Fix loop exhausted. Tests still failing.[/]")
                    if not self._confirm("Continue to PR anyway?"):
                        return result

            # 6. Security review
            sec = self._run_security(task, impl, ws_path)
            if sec.get("verdict") == "block":
                console.print("[red]🚫 Security blocked this change.[/]")
                self._print_security_issues(sec)
                if not self._confirm("Override security block?"):
                    result["status"] = "security_blocked"
                    return result

            # 7. Release assessment
            rel = self._run_release(task, impl, ws_path)

            # 7.5. Archivist Nova — document the change
            nova_result = self._run_archivist(task, impl, plan, rel, ws_path)
            if nova_result.get("should_write_adr") and nova_result.get("adr"):
                adr_applied = self._write_adr(ws_path, nova_result["adr"])
                if adr_applied:
                    console.print(f"  [cyan]{adr_applied}[/]")
            for doc in nova_result.get("doc_updates", []):
                doc_applied = self._write_doc_update(ws_path, doc)
                if doc_applied:
                    console.print(f"  [cyan]{doc_applied}[/]")

            # 8. Commit + PR
            commit_msg = impl.get("commit_message", f"glitchlab: {task.task_id}")
            self._workspace.commit(commit_msg)

            if self.config.intervention.pause_before_pr:
                diff = self._workspace.diff_stat()
                console.print(Panel(diff, title="Diff Summary", border_style="cyan"))
                if not self._confirm("Create PR?"):
                    result["status"] = "pr_cancelled"
                    return result

            # Push + PR
            try:
                self._workspace.push()
                pr_url = self._create_pr(task, impl, rel)
                result["pr_url"] = pr_url
                result["status"] = "pr_created"
                console.print(f"[bold green]✅ PR created: {pr_url}[/]")
            except Exception as e:
                logger.warning(f"PR creation failed: {e}")
                result["status"] = "committed"
                result["branch"] = self._workspace.branch_name
                console.print(f"[yellow]Changes committed to {self._workspace.branch_name}[/]")

            # Budget summary
            self._print_budget_summary()

            result["events"] = self._event_log
            result["budget"] = self.router.budget.summary()

        except BudgetExceededError as e:
            console.print(f"[red]💸 Budget exceeded: {e}[/]")
            result["status"] = "budget_exceeded"
        except KeyboardInterrupt:
            console.print("\n[yellow]⚡ Interrupted by human.[/]")
            result["status"] = "interrupted"
        except Exception as e:
            logger.exception("Controller error")
            console.print(f"[red]💥 Error: {e}[/]")
            result["status"] = "error"
            result["error"] = str(e)
        finally:
            if self._workspace:
                try:
                    self._workspace.cleanup()
                except Exception:
                    pass

            # Always record to history
            self._history.record(result)

        return result

    # -----------------------------------------------------------------------
    # Agent Runners
    # -----------------------------------------------------------------------

    def _run_planner(self, task: Task, ws_path: Path, failure_context: str = "") -> dict:
        console.print("\n[bold magenta]🧠 [ZAP] Planning...[/]")

        # Build rich objective with all available context
        objective_parts = []

        if self._prelude_prefix:
            objective_parts.append(self._prelude_prefix)

        if self._repo_index_context:
            objective_parts.append(self._repo_index_context)

        if failure_context:
            objective_parts.append(failure_context)

        objective_parts.append(f"TASK:\n{task.objective}")

        objective = "\n\n---\n\n".join(objective_parts)

        context = AgentContext(
            task_id=task.task_id,
            objective=objective,
            repo_path=str(self.repo_path),
            working_dir=str(ws_path),
            constraints=task.constraints,
            acceptance_criteria=task.acceptance_criteria,
            risk_level=task.risk_level,
        )

        plan = self.planner.run(context)
        self._log_event("plan_created", {
            "steps": len(plan.get("steps", [])),
            "risk": plan.get("risk_level"),
        })

        # Display plan
        self._print_plan(plan)

        # Human gate
        if self.config.intervention.pause_after_plan and not self.auto_approve:
            if not self._confirm("Approve plan?"):
                plan["_aborted"] = True
                plan["parse_error"] = True
                return plan

        return plan

    def _run_implementer(self, task: Task, plan: dict, ws_path: Path) -> dict:
        console.print("\n[bold blue]🔧 [PATCH] Implementing...[/]")

        file_context = gather_file_context(
            ws_path,
            plan.get("files_likely_affected", []),
        )

        # Include Prelude context so Patch knows the project's patterns
        extra = {}
        if self._prelude_prefix:
            extra["prelude_context"] = self._prelude_prefix

        context = AgentContext(
            task_id=task.task_id,
            objective=task.objective,
            repo_path=str(self.repo_path),
            working_dir=str(ws_path),
            constraints=task.constraints,
            acceptance_criteria=task.acceptance_criteria,
            file_context=file_context,
            previous_output=plan,
            extra=extra,
        )

        impl = self.implementer.run(context, max_tokens=8192)
        self._log_event("implementation_created", {
            "changes": len(impl.get("changes", [])),
            "tests": len(impl.get("tests_added", [])),
        })

        return impl

    def _run_fix_loop(
        self, task: Task, ws_path: Path, tools: ToolExecutor, impl: dict
    ) -> bool:
        """Run test → debug → fix loop. Returns True if tests pass."""
        max_attempts = self.config.limits.max_fix_attempts
        previous_fixes = []

        for attempt in range(1, max_attempts + 1):
            console.print(f"\n[bold]🧪 Test run {attempt}/{max_attempts}...[/]")

            try:
                result = tools.execute(self.test_command)
            except ToolViolationError as e:
                console.print(f"[red]Tool violation: {e}[/]")
                return False

            if result.success:
                console.print("[green]✅ Tests pass![/]")
                self._log_event("tests_passed", {"attempt": attempt})
                return True

            error_output = result.stderr or result.stdout
            console.print(f"[red]❌ Tests failed (attempt {attempt})[/]")
            self._log_event("tests_failed", {"attempt": attempt})

            if attempt >= max_attempts:
                break

            # Invoke debugger
            console.print(f"\n[bold yellow]🐛 [REROUTE] Debugging (attempt {attempt})...[/]")

            file_context = gather_file_context(
                ws_path,
                [c["file"] for c in impl.get("changes", [])],
            )

            context = AgentContext(
                task_id=task.task_id,
                objective=task.objective,
                repo_path=str(self.repo_path),
                working_dir=str(ws_path),
                file_context=file_context,
                extra={
                    "error_output": error_output[:3000],
                    "test_command": self.test_command,
                    "attempt": attempt,
                    "previous_fixes": previous_fixes,
                },
            )

            debug_result = self.debugger.run(context)
            previous_fixes.append(debug_result)

            if not debug_result.get("should_retry", False):
                console.print("[yellow]Debugger says: don't retry.[/]")
                break

            # Apply fix
            fix_changes = debug_result.get("fix", {}).get("changes", [])
            if fix_changes:
                applied = apply_changes(ws_path, fix_changes)
                for a in applied:
                    console.print(f"  [cyan]{a}[/]")

        return False

    def _run_security(self, task: Task, impl: dict, ws_path: Path) -> dict:
        console.print("\n[bold red]🔒 [FRANKIE] Security scan...[/]")

        diff = self._workspace.diff_full() if self._workspace else ""

        context = AgentContext(
            task_id=task.task_id,
            objective=task.objective,
            repo_path=str(self.repo_path),
            working_dir=str(ws_path),
            previous_output=impl,
            extra={
                "diff": diff,
                "protected_paths": self.config.boundaries.protected_paths,
            },
        )

        result = self.security.run(context)
        self._log_event("security_review", {"verdict": result.get("verdict")})
        return result

    def _run_release(self, task: Task, impl: dict, ws_path: Path) -> dict:
        console.print("\n[bold cyan]📦 [SEMVER] Release assessment...[/]")

        diff = self._workspace.diff_stat() if self._workspace else ""

        context = AgentContext(
            task_id=task.task_id,
            objective=task.objective,
            repo_path=str(self.repo_path),
            working_dir=str(ws_path),
            previous_output=impl,
            extra={"diff": diff},
        )

        result = self.release.run(context)
        self._log_event("release_assessment", {
            "bump": result.get("version_bump"),
        })
        return result

    def _run_archivist(
        self, task: Task, impl: dict, plan: dict, release: dict, ws_path: Path
    ) -> dict:
        """Run Archivist Nova to document the change."""
        console.print("\n[bold dim]📚 [NOVA] Documenting...[/]")

        # Find existing doc files for context
        existing_docs = []
        for pattern in ["*.md", "docs/**/*.md", "doc/**/*.md"]:
            existing_docs.extend(
                str(p.relative_to(ws_path))
                for p in ws_path.glob(pattern)
                if p.is_file() and ".glitchlab" not in str(p)
            )

        context = AgentContext(
            task_id=task.task_id,
            objective=task.objective,
            repo_path=str(self.repo_path),
            working_dir=str(ws_path),
            previous_output=impl,
            extra={
                "plan": plan,
                "release": release,
                "prelude_context": self._prelude_prefix,
                "existing_docs": existing_docs[:20],
            },
        )

        result = self.archivist.run(context)
        self._log_event("archivist_completed", {
            "wrote_adr": result.get("should_write_adr", False),
            "doc_updates": len(result.get("doc_updates", [])),
        })
        return result

    @staticmethod
    def _write_adr(ws_path: Path, adr: dict) -> str | None:
        """Write an ADR to the workspace."""
        # Determine ADR directory — prefer .context/decisions/ for Prelude compat
        adr_dir = ws_path / ".context" / "decisions"
        if not adr_dir.exists():
            adr_dir = ws_path / "docs" / "adr"
        adr_dir.mkdir(parents=True, exist_ok=True)

        # Find next ADR number
        existing = list(adr_dir.glob("*.md"))
        next_num = len(existing) + 1

        title = adr.get("title", f"ADR-{next_num:03d}")
        filename = f"{next_num:03d}-{title.lower().replace(' ', '-')[:50]}.md"
        filepath = adr_dir / filename

        content = f"""# {title}

**Status:** {adr.get('status', 'accepted')}
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

## Context

{adr.get('context', 'N/A')}

## Decision

{adr.get('decision', 'N/A')}

## Consequences

{adr.get('consequences', 'N/A')}
"""
        alternatives = adr.get("alternatives_considered", [])
        if alternatives:
            content += "\n## Alternatives Considered\n\n"
            for alt in alternatives:
                content += f"- {alt}\n"

        content += "\n---\n*Generated by GLITCHLAB / Archivist Nova*\n"

        filepath.write_text(content)
        return f"ADR {filepath.relative_to(ws_path)}"

    @staticmethod
    def _write_doc_update(ws_path: Path, doc: dict) -> str | None:
        """Apply a documentation update."""
        fpath = ws_path / doc["file"]
        action = doc.get("action", "create")
        content = doc.get("content", "")

        if not content:
            return None

        if action == "create":
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            return f"DOC CREATE {doc['file']}"
        elif action == "append":
            fpath.parent.mkdir(parents=True, exist_ok=True)
            existing = fpath.read_text() if fpath.exists() else ""
            fpath.write_text(existing + "\n\n" + content)
            return f"DOC APPEND {doc['file']}"
        elif action == "update" and fpath.exists():
            fpath.write_text(content)
            return f"DOC UPDATE {doc['file']}"
        return None

    # -----------------------------------------------------------------------
    # PR Creation
    # -----------------------------------------------------------------------

    def _create_pr(self, task: Task, impl: dict, release: dict) -> str:
        """Create a GitHub PR via gh CLI."""
        title = impl.get("commit_message", f"glitchlab: {task.task_id}")
        body = self._build_pr_body(task, impl, release)

        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--head", self._workspace.branch_name,
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"PR creation failed: {result.stderr}")

        return result.stdout.strip()

    @staticmethod
    def _build_pr_body(task: Task, impl: dict, release: dict) -> str:
        body = f"""## 🔬 GLITCHLAB Automated PR

**Task:** {task.task_id}
**Source:** {task.source}

### Summary
{impl.get('summary', 'No summary provided.')}

### Changes
"""
        for change in impl.get("changes", []):
            body += f"- `{change.get('action', '?')}` {change.get('file', '?')}: {change.get('description', '')}\n"

        body += f"""
### Version Impact
- **Bump:** {release.get('version_bump', 'unknown')}
- **Reasoning:** {release.get('reasoning', 'N/A')}

### Changelog
{release.get('changelog_entry', 'N/A')}

---
*Generated by GLITCHLAB — Build Weird. Ship Clean.*
"""
        return body

    # -----------------------------------------------------------------------
    # Display Helpers
    # -----------------------------------------------------------------------

    def _print_plan(self, plan: dict) -> None:
        table = Table(title="Execution Plan", border_style="magenta")
        table.add_column("#", style="dim")
        table.add_column("Action")
        table.add_column("Files")
        table.add_column("Description")

        for step in plan.get("steps", []):
            table.add_row(
                str(step.get("step_number", "?")),
                step.get("action", "?"),
                ", ".join(step.get("files", [])),
                step.get("description", ""),
            )

        console.print(table)
        console.print(f"Risk: [bold]{plan.get('risk_level', '?')}[/] | "
                      f"Core change: {plan.get('requires_core_change', False)} | "
                      f"Complexity: {plan.get('estimated_complexity', '?')}")

    def _print_security_issues(self, sec: dict) -> None:
        for issue in sec.get("issues", []):
            sev = issue.get("severity", "info")
            color = {"critical": "red", "high": "red", "medium": "yellow"}.get(sev, "dim")
            console.print(f"  [{color}]{sev.upper()}[/] {issue.get('description', '')}")

    def _print_budget_summary(self) -> None:
        summary = self.router.budget.summary()
        console.print(Panel(
            f"Tokens: {summary['total_tokens']:,} / "
            f"Cost: ${summary['estimated_cost']:.4f} / "
            f"Calls: {summary['call_count']}",
            title="💸 Budget",
            border_style="green",
        ))

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def _confirm(self, prompt: str) -> bool:
        if self.auto_approve:
            return True
        return Confirm.ask(f"[bold]{prompt}[/]")

    def _log_event(self, event_type: str, data: dict | None = None) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": self._task.task_id if self._task else None,
            "data": data or {},
        }
        self._event_log.append(event)
        logger.debug(f"[EVENT] {event_type}: {data}")
