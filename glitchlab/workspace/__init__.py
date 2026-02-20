"""
GLITCHLAB Workspace Isolation

Creates ephemeral git worktrees per task so agents
never touch the main branch directly. All work happens
in isolation and only merges via PR.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger


class WorkspaceError(Exception):
    pass


class Workspace:
    """
    Manages an isolated git worktree for a single task.

    Lifecycle:
        ws = Workspace(repo, task_id)
        ws.create(base_branch="main")
        # ... agents work inside ws.path ...
        ws.cleanup()
    """

    def __init__(self, repo_path: Path, task_id: str, worktree_base: str = ".glitchlab/worktrees"):
        self.repo_path = repo_path.resolve()
        self.task_id = task_id
        self.branch_name = f"glitchlab/{task_id}"
        self.worktree_path = self.repo_path / worktree_base / task_id
        self._created = False

    @property
    def path(self) -> Path:
        return self.worktree_path

    def create(self, base_branch: str = "main") -> Path:
        """Create isolated worktree + branch for this task."""
        if self.worktree_path.exists():
            logger.warning(f"[WORKSPACE] Worktree already exists: {self.worktree_path}")
            self._created = True
            return self.worktree_path

        # Ensure parent dir exists
        self.worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Create branch
        self._git("branch", self.branch_name, base_branch, check=False)

        # Create worktree
        self._git("worktree", "add", str(self.worktree_path), self.branch_name)

        self._created = True
        logger.info(f"[WORKSPACE] Created: {self.worktree_path} on branch {self.branch_name}")
        return self.worktree_path

    def commit(self, message: str, add_all: bool = True) -> str | None:
        """Stage and commit changes inside the worktree."""
        if add_all:
            self._worktree_git("add", "-A")

        # Check if there's anything to commit
        result = self._worktree_git("status", "--porcelain", capture=True)
        if not result.strip():
            logger.info("[WORKSPACE] Nothing to commit.")
            return None

        self._worktree_git("commit", "-m", message)
        sha = self._worktree_git("rev-parse", "HEAD", capture=True).strip()
        logger.info(f"[WORKSPACE] Committed: {sha[:8]} — {message}")
        return sha

    def diff_stat(self) -> str:
        """Return diff --stat against base branch."""
        return self._worktree_git("diff", "--stat", "main", capture=True)

    def diff_full(self) -> str:
        """Return full diff against base branch."""
        return self._worktree_git("diff", "main", capture=True)

    def push(self) -> None:
        """Push the task branch to origin."""
        self._worktree_git("push", "-u", "origin", self.branch_name)
        logger.info(f"[WORKSPACE] Pushed: {self.branch_name}")

    def cleanup(self) -> None:
        """Remove worktree and optionally the branch."""
        if not self._created:
            return

        try:
            self._git("worktree", "remove", str(self.worktree_path), "--force", check=False)
        except Exception as e:
            logger.warning(f"[WORKSPACE] Worktree remove failed: {e}")

        # Fallback: delete directory
        if self.worktree_path.exists():
            shutil.rmtree(self.worktree_path, ignore_errors=True)

        # Prune worktree list
        self._git("worktree", "prune", check=False)
        logger.info(f"[WORKSPACE] Cleaned up: {self.task_id}")

    def _git(self, *args: str, check: bool = True, capture: bool = False) -> str:
        """Run git command in the main repo."""
        return self._run_cmd(["git", *args], cwd=self.repo_path, check=check, capture=capture)

    def _worktree_git(self, *args: str, check: bool = True, capture: bool = False) -> str:
        """Run git command inside the worktree."""
        return self._run_cmd(
            ["git", *args], cwd=self.worktree_path, check=check, capture=capture
        )

    @staticmethod
    def _run_cmd(
        cmd: list[str], cwd: Path, check: bool = True, capture: bool = False
    ) -> str:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check and result.returncode != 0:
            raise WorkspaceError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stderr: {result.stderr}\n"
                f"stdout: {result.stdout}"
            )
        if capture:
            return result.stdout
        return result.stdout
