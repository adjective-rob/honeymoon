"""
GLITCHLAB Sentry — Swarm Cost & Loop Control

The Sentry is an EventBus subscriber that monitors the swarm for:
  1. Doom loops — token burn rising with no progress
  2. Budget blowout — cumulative cost approaching limits
  3. Stalled ants — workers that stop emitting events

When a problem is detected, the Sentry emits a `swarm.halt` event
that the swarm runner picks up to kill runaway workers.

Design principles:
  - Passive observer (reads events, never modifies agent state)
  - Emits signals only (halt, warn) — the Queen decides what to do
  - Works on weak hardware (no LLM calls, pure arithmetic)
  - Configurable thresholds with sane defaults
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from glitchlab.event_bus import GlitchEvent, bus


# ---------------------------------------------------------------------------
# Sentry configuration
# ---------------------------------------------------------------------------

@dataclass
class SentryConfig:
    """Tunable thresholds for the Sentry."""

    # Doom loop: if an ant burns this many tokens without a completion, halt it
    doom_loop_token_threshold: int = 50_000

    # Budget: warn at this percentage of max, halt at this percentage
    budget_warn_pct: float = 0.70
    budget_halt_pct: float = 0.90

    # Stall detection: if no event from an ant for this many seconds, flag it
    stall_timeout_seconds: float = 300.0  # 5 minutes

    # Max consecutive failures before halting an ant
    max_consecutive_failures: int = 3


# ---------------------------------------------------------------------------
# Per-ant tracking state
# ---------------------------------------------------------------------------

@dataclass
class AntMetrics:
    """Tracked metrics for a single ant."""

    ant_id: str
    tokens_used: int = 0
    tokens_at_last_completion: int = 0
    completions: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_event_time: float = 0.0
    halted: bool = False


# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------

class Sentry:
    """Monitors swarm health and emits halt/warn signals.

    Usage:
        sentry = Sentry(run_id="swarm-abc123", max_budget_tokens=500_000)
        # EventBus subscription happens in __init__
        # ... swarm runs ...
        # Check sentry.halted_ants for which workers were killed
    """

    def __init__(
        self,
        run_id: str,
        max_budget_tokens: int = 1_000_000,
        max_budget_dollars: float = 10.0,
        config: SentryConfig | None = None,
    ):
        self.run_id = run_id
        self.max_budget_tokens = max_budget_tokens
        self.max_budget_dollars = max_budget_dollars
        self.config = config or SentryConfig()

        self._ants: dict[str, AntMetrics] = {}
        self._total_tokens: int = 0
        self._total_cost: float = 0.0
        self._halt_emitted: bool = False

        bus.subscribe(self._on_event)
        logger.debug(f"[SENTRY] Watching run {run_id}")

    @property
    def halted_ants(self) -> set[str]:
        """Return set of ant IDs that have been halted."""
        return {m.ant_id for m in self._ants.values() if m.halted}

    @property
    def is_swarm_halted(self) -> bool:
        """True if the entire swarm has been halted."""
        return self._halt_emitted

    # --- Event handler ---

    def _on_event(self, event: GlitchEvent) -> None:
        """Process an EventBus event and check for anomalies."""
        if event.run_id != self.run_id:
            return

        agent = event.agent_id or "unknown"
        etype = event.event_type

        # Initialize ant tracking on first sight
        if agent not in self._ants and agent != "system" and agent != "controller":
            self._ants[agent] = AntMetrics(ant_id=agent, last_event_time=time.time())

        metrics = self._ants.get(agent)
        if metrics:
            metrics.last_event_time = time.time()

        # --- Token tracking ---
        if etype == "llm.completed":
            tokens = event.payload.get("tokens_total", 0)
            cost = event.payload.get("estimated_cost", 0.0)

            self._total_tokens += tokens
            self._total_cost = max(self._total_cost, cost)  # cost is cumulative in Router

            if metrics:
                metrics.tokens_used += tokens

            self._check_budget()
            if metrics:
                self._check_doom_loop(metrics)

        # --- Completion tracking ---
        elif etype == "pipeline.step_completed":
            if metrics:
                metrics.completions += 1
                metrics.tokens_at_last_completion = metrics.tokens_used
                metrics.consecutive_failures = 0

        # --- Failure tracking ---
        elif etype in ("pipeline.step_failed", "llm.error"):
            if metrics:
                metrics.failures += 1
                metrics.consecutive_failures += 1
                self._check_consecutive_failures(metrics)

    # --- Checks ---

    def _check_budget(self) -> None:
        """Check if total budget thresholds have been crossed."""
        token_pct = self._total_tokens / self.max_budget_tokens if self.max_budget_tokens else 0

        if token_pct >= self.config.budget_halt_pct and not self._halt_emitted:
            self._emit_halt(
                reason="budget_exceeded",
                detail=f"Token usage at {token_pct:.0%} of max ({self._total_tokens:,} / {self.max_budget_tokens:,})",
            )
        elif token_pct >= self.config.budget_warn_pct:
            logger.warning(
                f"[SENTRY] Budget warning: {token_pct:.0%} of token budget used "
                f"({self._total_tokens:,} / {self.max_budget_tokens:,})"
            )

    def _check_doom_loop(self, metrics: AntMetrics) -> None:
        """Check if an ant is burning tokens without making progress."""
        tokens_since_completion = metrics.tokens_used - metrics.tokens_at_last_completion

        if tokens_since_completion >= self.config.doom_loop_token_threshold and not metrics.halted:
            self._emit_ant_halt(
                metrics,
                reason="doom_loop",
                detail=(
                    f"{metrics.ant_id} burned {tokens_since_completion:,} tokens "
                    f"since last completion (threshold: {self.config.doom_loop_token_threshold:,})"
                ),
            )

    def _check_consecutive_failures(self, metrics: AntMetrics) -> None:
        """Check if an ant has too many consecutive failures."""
        if metrics.consecutive_failures >= self.config.max_consecutive_failures and not metrics.halted:
            self._emit_ant_halt(
                metrics,
                reason="consecutive_failures",
                detail=(
                    f"{metrics.ant_id} failed {metrics.consecutive_failures} times "
                    f"in a row (max: {self.config.max_consecutive_failures})"
                ),
            )

    def check_stalled(self) -> list[str]:
        """Check for stalled ants (call periodically from Queen).

        Returns list of ant IDs that appear stalled.
        """
        now = time.time()
        stalled = []
        for metrics in self._ants.values():
            if metrics.halted:
                continue
            elapsed = now - metrics.last_event_time
            if elapsed >= self.config.stall_timeout_seconds:
                stalled.append(metrics.ant_id)
                logger.warning(
                    f"[SENTRY] {metrics.ant_id} stalled — no events for {elapsed:.0f}s"
                )
        return stalled

    # --- Signal emission ---

    def _emit_halt(self, reason: str, detail: str) -> None:
        """Emit a swarm-wide halt signal."""
        self._halt_emitted = True
        logger.error(f"[SENTRY] SWARM HALT — {reason}: {detail}")
        bus.emit(
            event_type="swarm.halt",
            payload={"reason": reason, "detail": detail, "scope": "swarm"},
            agent_id="sentry",
            run_id=self.run_id,
        )

    def _emit_ant_halt(self, metrics: AntMetrics, reason: str, detail: str) -> None:
        """Emit a halt signal for a specific ant."""
        metrics.halted = True
        logger.warning(f"[SENTRY] ANT HALT — {reason}: {detail}")
        bus.emit(
            event_type="swarm.halt",
            payload={
                "reason": reason,
                "detail": detail,
                "scope": "ant",
                "ant_id": metrics.ant_id,
            },
            agent_id="sentry",
            run_id=self.run_id,
        )

    def summary(self) -> dict[str, Any]:
        """Return a summary of sentry observations."""
        return {
            "total_tokens": self._total_tokens,
            "total_cost": round(self._total_cost, 4),
            "ants_tracked": len(self._ants),
            "ants_halted": len(self.halted_ants),
            "swarm_halted": self._halt_emitted,
            "per_ant": {
                ant_id: {
                    "tokens": m.tokens_used,
                    "completions": m.completions,
                    "failures": m.failures,
                    "halted": m.halted,
                }
                for ant_id, m in self._ants.items()
            },
        }
