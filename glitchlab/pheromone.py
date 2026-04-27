"""
GLITCHLAB Pheromone Trail — Shared Swarm Awareness Layer

The pheromone trail is the communication backbone of the ant colony.
It's a structured, append-only log that enables:
  - Symbol-level locking (who's editing what)
  - Failure propagation (what went wrong, don't repeat it)
  - Progress awareness (what's done, what's in flight)

Architecture:
  - PheromoneWriter: EventBus subscriber that serializes events to disk
  - PheromoneReader: Query interface for agents and the swarm scheduler
  - PheromoneTrail: Combined read/write interface

Events are stored in .glitchlab/pheromones.jsonl (one JSON object per line).
The file is designed for concurrent append by multiple worker processes.
"""

from __future__ import annotations

import fcntl
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from glitchlab.event_bus import GlitchEvent, bus


# ---------------------------------------------------------------------------
# Pheromone record types
# ---------------------------------------------------------------------------

PHEROMONE_TYPES = {
    "claim",        # Ant claims a symbol/file for editing
    "release",      # Ant releases a claim
    "progress",     # Ant reports progress on a sub-task
    "completion",   # Ant finished a sub-task
    "failure",      # Ant failed a sub-task (with context)
    "tool_error",   # A tool call failed (for ancestral memory)
}


@dataclass
class PheromoneRecord:
    """A single entry in the pheromone trail."""

    ptype: str                    # One of PHEROMONE_TYPES
    ant_id: str                   # Worker identifier (e.g., "ant-0", "ant-1")
    run_id: str                   # Parent swarm run ID
    timestamp: float              # time.time()
    target: str = ""              # File path or symbol being claimed/worked
    subtask_id: str = ""          # Which sub-task this relates to
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ptype": self.ptype,
            "ant_id": self.ant_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "target": self.target,
            "subtask_id": self.subtask_id,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PheromoneRecord:
        return cls(
            ptype=d["ptype"],
            ant_id=d["ant_id"],
            run_id=d["run_id"],
            timestamp=d["timestamp"],
            target=d.get("target", ""),
            subtask_id=d.get("subtask_id", ""),
            data=d.get("data", {}),
        )


# ---------------------------------------------------------------------------
# Writer — appends pheromone records to the trail file
# ---------------------------------------------------------------------------

class PheromoneWriter:
    """Append-only writer for the pheromone trail.

    Uses file-level locking (fcntl.flock) to allow safe concurrent
    appends from multiple worker processes.
    """

    def __init__(self, trail_path: Path):
        self.trail_path = trail_path
        self.trail_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: PheromoneRecord) -> None:
        """Append a single record with file-level locking."""
        line = json.dumps(record.to_dict()) + "\n"
        with open(self.trail_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def claim(self, ant_id: str, run_id: str, target: str, subtask_id: str = "") -> None:
        """Record that an ant is claiming a file/symbol for editing."""
        self.write(PheromoneRecord(
            ptype="claim",
            ant_id=ant_id,
            run_id=run_id,
            timestamp=time.time(),
            target=target,
            subtask_id=subtask_id,
        ))

    def release(self, ant_id: str, run_id: str, target: str) -> None:
        """Record that an ant is releasing a claim."""
        self.write(PheromoneRecord(
            ptype="release",
            ant_id=ant_id,
            run_id=run_id,
            timestamp=time.time(),
            target=target,
        ))

    def complete(self, ant_id: str, run_id: str, subtask_id: str, data: dict | None = None) -> None:
        """Record that an ant completed a sub-task."""
        self.write(PheromoneRecord(
            ptype="completion",
            ant_id=ant_id,
            run_id=run_id,
            timestamp=time.time(),
            subtask_id=subtask_id,
            data=data or {},
        ))

    def fail(self, ant_id: str, run_id: str, subtask_id: str, error: str,
             tool_calls: list[dict] | None = None) -> None:
        """Record that an ant failed a sub-task."""
        self.write(PheromoneRecord(
            ptype="failure",
            ant_id=ant_id,
            run_id=run_id,
            timestamp=time.time(),
            subtask_id=subtask_id,
            data={"error": error, "failed_tool_calls": tool_calls or []},
        ))

    def tool_error(self, ant_id: str, run_id: str, command: str, error: str) -> None:
        """Record a tool call failure for ancestral memory."""
        self.write(PheromoneRecord(
            ptype="tool_error",
            ant_id=ant_id,
            run_id=run_id,
            timestamp=time.time(),
            data={"command": command, "error": error},
        ))


# ---------------------------------------------------------------------------
# Reader — queries the pheromone trail
# ---------------------------------------------------------------------------

class PheromoneReader:
    """Read-only query interface over the pheromone trail."""

    def __init__(self, trail_path: Path):
        self.trail_path = trail_path

    def _read_all(self, run_id: str | None = None) -> list[PheromoneRecord]:
        """Read all records, optionally filtered by run_id."""
        if not self.trail_path.exists():
            return []

        records = []
        with open(self.trail_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    rec = PheromoneRecord.from_dict(d)
                    if run_id is None or rec.run_id == run_id:
                        records.append(rec)
                except (json.JSONDecodeError, KeyError):
                    continue
        return records

    def active_claims(self, run_id: str) -> dict[str, str]:
        """Return a map of target → ant_id for all currently held claims.

        A claim is active if there's no subsequent release for the same
        ant_id + target combination.
        """
        claims: dict[str, str] = {}
        for rec in self._read_all(run_id):
            if rec.ptype == "claim":
                claims[rec.target] = rec.ant_id
            elif rec.ptype == "release" and rec.target in claims:
                if claims[rec.target] == rec.ant_id:
                    del claims[rec.target]
        return claims

    def is_claimed(self, run_id: str, target: str) -> str | None:
        """Check if a target is claimed. Returns ant_id if claimed, None otherwise."""
        claims = self.active_claims(run_id)
        return claims.get(target)

    def completed_subtasks(self, run_id: str) -> set[str]:
        """Return set of completed subtask IDs."""
        return {
            rec.subtask_id
            for rec in self._read_all(run_id)
            if rec.ptype == "completion" and rec.subtask_id
        }

    def failed_subtasks(self, run_id: str) -> list[PheromoneRecord]:
        """Return failure records for this run, newest first."""
        failures = [
            rec for rec in self._read_all(run_id)
            if rec.ptype == "failure"
        ]
        return sorted(failures, key=lambda r: r.timestamp, reverse=True)

    def recent_tool_errors(self, run_id: str, limit: int = 5) -> list[dict]:
        """Return the last N tool errors for ancestral failure memory."""
        errors = [
            rec.data for rec in self._read_all(run_id)
            if rec.ptype == "tool_error"
        ]
        return errors[-limit:]

    def ant_progress(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Return per-ant progress summary."""
        progress: dict[str, dict[str, Any]] = {}
        for rec in self._read_all(run_id):
            if rec.ant_id not in progress:
                progress[rec.ant_id] = {
                    "claims": 0,
                    "completions": 0,
                    "failures": 0,
                    "last_seen": rec.timestamp,
                }
            info = progress[rec.ant_id]
            info["last_seen"] = max(info["last_seen"], rec.timestamp)
            if rec.ptype == "claim":
                info["claims"] += 1
            elif rec.ptype == "completion":
                info["completions"] += 1
            elif rec.ptype == "failure":
                info["failures"] += 1
        return progress


# ---------------------------------------------------------------------------
# Trail — combined read/write interface + EventBus bridge
# ---------------------------------------------------------------------------

class PheromoneTrail:
    """Combined pheromone read/write interface.

    Also acts as an EventBus subscriber, converting relevant GlitchEvents
    into pheromone records automatically.
    """

    def __init__(self, repo_path: Path, run_id: str, subscribe: bool = True):
        self.trail_path = repo_path / ".glitchlab" / "pheromones.jsonl"
        self.run_id = run_id
        self.writer = PheromoneWriter(self.trail_path)
        self.reader = PheromoneReader(self.trail_path)

        if subscribe:
            bus.subscribe(self._on_event)
            logger.debug("[PHEROMONE] Subscribed to EventBus")

    def _on_event(self, event: GlitchEvent) -> None:
        """Bridge EventBus events into pheromone records.

        Converts tool failures and action completions into pheromone
        entries so the swarm has awareness of what happened.
        """
        if event.run_id != self.run_id:
            return

        etype = event.event_type
        agent = event.agent_id or "unknown"

        if etype == "action.completed":
            # Record tool errors for ancestral memory
            rc = event.payload.get("returncode", 0)
            if rc != 0:
                self.writer.tool_error(
                    ant_id=agent,
                    run_id=self.run_id,
                    command=event.payload.get("command", ""),
                    error=event.payload.get("stderr", "")[:500],
                )

        elif etype == "pipeline.step_completed":
            self.writer.write(PheromoneRecord(
                ptype="progress",
                ant_id=agent,
                run_id=self.run_id,
                timestamp=time.time(),
                data={"step": event.payload.get("step", "")},
            ))

    # --- Delegate to reader/writer ---

    def claim(self, ant_id: str, target: str, subtask_id: str = "") -> bool:
        """Attempt to claim a target. Returns False if already claimed by another ant."""
        holder = self.reader.is_claimed(self.run_id, target)
        if holder is not None and holder != ant_id:
            logger.debug(f"[PHEROMONE] {target} already claimed by {holder}, skipping")
            return False
        self.writer.claim(ant_id, self.run_id, target, subtask_id)
        return True

    def release(self, ant_id: str, target: str) -> None:
        self.writer.release(ant_id, self.run_id, target)

    def complete(self, ant_id: str, subtask_id: str, data: dict | None = None) -> None:
        self.writer.complete(ant_id, self.run_id, subtask_id, data)

    def fail(self, ant_id: str, subtask_id: str, error: str,
             tool_calls: list[dict] | None = None) -> None:
        self.writer.fail(ant_id, self.run_id, subtask_id, error, tool_calls)

    def active_claims(self) -> dict[str, str]:
        return self.reader.active_claims(self.run_id)

    def is_claimed(self, target: str) -> str | None:
        return self.reader.is_claimed(self.run_id, target)

    def completed_subtasks(self) -> set[str]:
        return self.reader.completed_subtasks(self.run_id)

    def failed_subtasks(self) -> list[PheromoneRecord]:
        return self.reader.failed_subtasks(self.run_id)

    def recent_tool_errors(self, limit: int = 5) -> list[dict]:
        return self.reader.recent_tool_errors(self.run_id, limit)

    def ant_progress(self) -> dict[str, dict[str, Any]]:
        return self.reader.ant_progress(self.run_id)

    def clear(self) -> None:
        """Wipe the trail (typically at swarm start)."""
        if self.trail_path.exists():
            self.trail_path.unlink()
            logger.debug("[PHEROMONE] Trail cleared")
