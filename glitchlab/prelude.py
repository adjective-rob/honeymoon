"""
GLITCHLAB ← Prelude Integration

Bridges prelude-context (machine-readable codebase context)
into the GLITCHLAB agent pipeline so every agent understands
the project's stack, architecture, patterns, constraints, and
decisions before it plans or writes a single line.

Prelude is the memory. GLITCHLAB is the muscle.

Usage:
    prelude = PreludeContext(repo_path)
    if prelude.available:
        prelude.refresh()           # re-export context
        context_md = prelude.export()  # get markdown for agents
        summary = prelude.summary()    # get structured summary
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger


class PreludeContext:
    """
    Interface to Prelude's .context/ directory and CLI.

    Three modes of operation:
      1. Full CLI available → can init, export, update, watch
      2. .context/ exists but no CLI → read-only (uses cached files)
      3. Neither → gracefully disabled, agents get no project context
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.resolve()
        self.context_dir = self.repo_path / ".context"
        self._cli_path = shutil.which("prelude")
        self._cached_export: str | None = None

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def cli_available(self) -> bool:
        """Is the prelude CLI installed?"""
        return self._cli_path is not None

    @property
    def context_exists(self) -> bool:
        """Does a .context/ directory exist in this repo?"""
        return self.context_dir.is_dir()

    @property
    def available(self) -> bool:
        """Can we get any context at all?"""
        return self.cli_available or self.context_exists

    # ------------------------------------------------------------------
    # CLI Operations
    # ------------------------------------------------------------------

    def init(self) -> bool:
        """Run `prelude init` to analyze the repo and create .context/."""
        if not self.cli_available:
            logger.warning("[PRELUDE] CLI not installed. Run: npm install -g prelude-context")
            return False

        result = self._run("init")
        if result.returncode == 0:
            logger.info("[PRELUDE] Initialized .context/ directory")
            return True
        else:
            logger.error(f"[PRELUDE] Init failed: {result.stderr}")
            return False

    def update(self) -> bool:
        """Run `prelude update` to refresh inferred context while preserving manual edits."""
        if not self.cli_available:
            return False

        result = self._run("update")
        if result.returncode == 0:
            logger.info("[PRELUDE] Context updated")
            self._cached_export = None  # invalidate cache
            return True
        else:
            logger.warning(f"[PRELUDE] Update failed: {result.stderr}")
            return False

    def refresh(self) -> bool:
        """
        Ensure context is fresh before a GLITCHLAB run.
        If .context/ exists, update it. If not, init it.
        """
        if not self.cli_available:
            if self.context_exists:
                logger.debug("[PRELUDE] Using existing .context/ (CLI not available)")
                return True
            return False

        if self.context_exists:
            return self.update()
        else:
            return self.init()

    # ------------------------------------------------------------------
    # Context Extraction
    # ------------------------------------------------------------------

    def export(self) -> str:
        """
        Get the full Prelude context as markdown.

        Reads .context/ files directly (fastest, no hang risk).
        Only falls back to CLI export if no .context/ directory exists.
        """
        if self._cached_export:
            return self._cached_export

        # Prefer direct file reading — no subprocess, no hang risk
        if self.context_exists:
            self._cached_export = self._read_context_files()
            if self._cached_export:
                logger.info(f"[PRELUDE] Read context from files ({len(self._cached_export)} chars)")
                return self._cached_export

        # Fallback: try CLI export with short timeout
        if self.cli_available:
            try:
                result = self._run("export", "--no-clipboard")
                if result.returncode == 0 and result.stdout.strip():
                    self._cached_export = result.stdout.strip()
                    logger.info(f"[PRELUDE] Exported context via CLI ({len(self._cached_export)} chars)")
                    return self._cached_export
            except Exception as e:
                logger.warning(f"[PRELUDE] CLI export failed: {e}")

        return ""

    def summary(self) -> dict[str, Any]:
        """
        Get structured summary of project context.
        Useful for logging and status display.
        """
        summary: dict[str, Any] = {
            "available": self.available,
            "cli_installed": self.cli_available,
            "context_dir_exists": self.context_exists,
            "files": [],
        }

        if self.context_exists:
            summary["files"] = [
                f.name for f in self.context_dir.iterdir()
                if f.is_file() and not f.name.endswith(".session.json")
            ]

            # Try to extract key metadata
            project_file = self.context_dir / "project.json"
            if project_file.exists():
                try:
                    data = json.loads(project_file.read_text())
                    summary["project_name"] = data.get("name", "unknown")
                    summary["language"] = data.get("language", "unknown")
                    summary["framework"] = data.get("framework", "unknown")
                except (json.JSONDecodeError, KeyError):
                    pass

            stack_file = self.context_dir / "stack.json"
            if stack_file.exists():
                try:
                    data = json.loads(stack_file.read_text())
                    summary["stack"] = data
                except json.JSONDecodeError:
                    pass

            decisions_dir = self.context_dir / "decisions"
            if decisions_dir.is_dir():
                summary["decisions_count"] = len(list(decisions_dir.glob("*.md")))

        return summary

    def get_decisions(self) -> list[str]:
        """Read all Architecture Decision Records as text."""
        decisions = []
        decisions_dir = self.context_dir / "decisions"

        if decisions_dir.is_dir():
            for md_file in sorted(decisions_dir.glob("*.md")):
                decisions.append(md_file.read_text())

        return decisions

    def get_constraints(self) -> list[str]:
        """Extract project constraints from .context/ if available."""
        constraints_file = self.context_dir / "constraints.json"
        if constraints_file.exists():
            try:
                data = json.loads(constraints_file.read_text())
                if isinstance(data, list):
                    return [str(c) for c in data]
                elif isinstance(data, dict):
                    return [
                        f"{k}: {v}" for k, v in data.items()
                        if isinstance(v, str)
                    ]
            except json.JSONDecodeError:
                pass
        return []

    # ------------------------------------------------------------------
    # Agent Context Builder
    # ------------------------------------------------------------------

    def build_agent_prefix(self, max_chars: int = 8000) -> str:
        """
        Build a context prefix suitable for injecting into agent prompts.

        This is the key integration point — this string gets prepended
        to agent context so every agent understands the project.

        Args:
            max_chars: Truncate to this length to manage token budget.
        """
        context = self.export()
        if not context:
            return ""

        prefix = (
            "=== PROJECT CONTEXT (via Prelude) ===\n"
            "The following is machine-readable context about this project's "
            "stack, architecture, patterns, constraints, and decisions. "
            "Respect all constraints and decisions when planning or implementing.\n\n"
        )

        # Truncate if needed, preserving the beginning (most important: stack + arch)
        remaining = max_chars - len(prefix)
        if len(context) > remaining:
            context = context[:remaining] + "\n\n[... context truncated for token budget ...]"

        return prefix + context

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        """Run a prelude CLI command."""
        cmd = ["prelude", *args]
        return subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _read_context_files(self) -> str:
        """Read .context/ files directly as a fallback when CLI isn't available."""
        parts = []

        # Priority order for context assembly
        file_order = [
            "project.json",
            "stack.json",
            "architecture.md",
            "constraints.json",
            "changelog.md",
        ]

        for fname in file_order:
            fpath = self.context_dir / fname
            if fpath.exists():
                content = fpath.read_text().strip()
                if content:
                    parts.append(f"## {fname}\n\n{content}")

        # ADRs
        decisions_dir = self.context_dir / "decisions"
        if decisions_dir.is_dir():
            for md_file in sorted(decisions_dir.glob("*.md")):
                content = md_file.read_text().strip()
                if content:
                    parts.append(f"## Decision: {md_file.stem}\n\n{content}")

        # Any other files not yet captured
        seen = set(file_order)
        for fpath in sorted(self.context_dir.iterdir()):
            if (
                fpath.is_file()
                and fpath.name not in seen
                and not fpath.name.endswith(".session.json")
            ):
                content = fpath.read_text().strip()
                if content:
                    parts.append(f"## {fpath.name}\n\n{content}")

        return "\n\n---\n\n".join(parts)
