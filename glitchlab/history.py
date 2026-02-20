"""
GLITCHLAB Task History — Append-Only Run Log

Every GLITCHLAB run is recorded in .glitchlab/logs/history.json.
This provides:
  - A record of what was attempted and what succeeded/failed
  - Failure patterns that can inform future planning
  - Cost tracking over time
  - A foundation for adaptive agent routing

The log is append-only. Each entry is one JSON object per line (JSONL).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


class TaskHistory:
    """
    Manages the append-only task history log.

    Storage: .glitchlab/logs/history.jsonl (one JSON object per line)
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.resolve()
        self.log_dir = self.repo_path / ".glitchlab" / "logs"
        self.history_file = self.log_dir / "history.jsonl"

    def record(self, result: dict[str, Any]) -> None:
        """
        Append a completed task run to the history log.

        Args:
            result: The full result dict from Controller.run()
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": result.get("task_id", "unknown"),
            "status": result.get("status", "unknown"),
            "pr_url": result.get("pr_url"),
            "branch": result.get("branch"),
            "error": result.get("error"),
            "budget": result.get("budget", {}),
            "events_summary": self._summarize_events(result.get("events", [])),
        }

        try:
            with open(self.history_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            logger.debug(f"[HISTORY] Recorded: {entry['task_id']} → {entry['status']}")
        except Exception as e:
            logger.warning(f"[HISTORY] Failed to write history: {e}")

    def get_recent(self, n: int = 10) -> list[dict]:
        """Read the most recent N history entries."""
        if not self.history_file.exists():
            return []

        try:
            lines = self.history_file.read_text().strip().splitlines()
            entries = []
            for line in lines[-n:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        except Exception as e:
            logger.warning(f"[HISTORY] Failed to read history: {e}")
            return []

    def get_failures(self, n: int = 20) -> list[dict]:
        """Read recent failures for pattern analysis."""
        recent = self.get_recent(n * 2)  # read more to filter
        return [
            e for e in recent
            if e.get("status") not in ("pr_created", "committed")
        ][:n]

    def get_stats(self) -> dict[str, Any]:
        """Compute summary statistics across all runs."""
        entries = self.get_all()
        if not entries:
            return {"total_runs": 0}

        total = len(entries)
        statuses = {}
        total_cost = 0.0
        total_tokens = 0

        for entry in entries:
            s = entry.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1

            budget = entry.get("budget", {})
            total_cost += budget.get("estimated_cost", 0)
            total_tokens += budget.get("total_tokens", 0)

        return {
            "total_runs": total,
            "statuses": statuses,
            "success_rate": round(
                statuses.get("pr_created", 0) / total * 100, 1
            ) if total > 0 else 0,
            "total_cost": round(total_cost, 4),
            "total_tokens": total_tokens,
            "avg_cost_per_run": round(total_cost / total, 4) if total > 0 else 0,
        }

    def get_all(self) -> list[dict]:
        """Read all history entries."""
        if not self.history_file.exists():
            return []
        try:
            lines = self.history_file.read_text().strip().splitlines()
            entries = []
            for line in lines:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        except Exception:
            return []

    def build_failure_context(self, max_entries: int = 5) -> str:
        """
        Build a context string from recent failures to inject into planner.
        Helps agents avoid repeating the same mistakes.
        """
        failures = self.get_failures(max_entries)
        if not failures:
            return ""

        parts = ["=== RECENT FAILURES (learn from these) ===\n"]
        for entry in failures:
            parts.append(
                f"- Task: {entry.get('task_id')} | "
                f"Status: {entry.get('status')} | "
                f"Error: {entry.get('error', 'N/A')}"
            )
            events = entry.get("events_summary", {})
            if events.get("security_verdict"):
                parts.append(f"  Security: {events['security_verdict']}")
            if events.get("fix_attempts"):
                parts.append(f"  Fix attempts: {events['fix_attempts']}")

        return "\n".join(parts)

    @staticmethod
    def _summarize_events(events: list[dict]) -> dict[str, Any]:
        """Extract key facts from the event log."""
        summary: dict[str, Any] = {}
        fix_attempts = 0

        for event in events:
            etype = event.get("type", "")
            data = event.get("data", {})

            if etype == "plan_created":
                summary["plan_steps"] = data.get("steps", 0)
                summary["plan_risk"] = data.get("risk")
            elif etype == "tests_failed":
                fix_attempts += 1
            elif etype == "tests_passed":
                summary["tests_passed_on_attempt"] = data.get("attempt", 1)
            elif etype == "security_review":
                summary["security_verdict"] = data.get("verdict")
            elif etype == "release_assessment":
                summary["version_bump"] = data.get("bump")

        summary["fix_attempts"] = fix_attempts
        return summary
