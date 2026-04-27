"""Tests for the Sentry — swarm cost and loop control."""

import time

from glitchlab.event_bus import bus, GlitchEvent
from glitchlab.sentry import Sentry, SentryConfig


def _emit(run_id: str, event_type: str, agent_id: str = "ant-0", payload: dict = None):
    """Helper to emit a test event directly on the bus."""
    bus.emit(
        event_type=event_type,
        payload=payload or {},
        agent_id=agent_id,
        run_id=run_id,
    )


def test_sentry_tracks_tokens():
    sentry = Sentry(run_id="test-1", max_budget_tokens=100_000)
    _emit("test-1", "llm.completed", payload={"tokens_total": 5000, "estimated_cost": 0.01})
    assert sentry._total_tokens == 5000


def test_sentry_ignores_other_runs():
    sentry = Sentry(run_id="test-2", max_budget_tokens=100_000)
    _emit("other-run", "llm.completed", payload={"tokens_total": 99999, "estimated_cost": 0.5})
    assert sentry._total_tokens == 0


def test_sentry_emits_halt_on_budget():
    sentry = Sentry(
        run_id="test-3",
        max_budget_tokens=10_000,
        config=SentryConfig(budget_halt_pct=0.90),
    )
    _emit("test-3", "llm.completed", payload={"tokens_total": 9500, "estimated_cost": 0.0})
    assert sentry.is_swarm_halted is True


def test_sentry_does_not_halt_under_threshold():
    sentry = Sentry(
        run_id="test-4",
        max_budget_tokens=100_000,
        config=SentryConfig(budget_halt_pct=0.90),
    )
    _emit("test-4", "llm.completed", payload={"tokens_total": 5000, "estimated_cost": 0.0})
    assert sentry.is_swarm_halted is False


def test_sentry_doom_loop_detection():
    sentry = Sentry(
        run_id="test-5",
        max_budget_tokens=1_000_000,
        config=SentryConfig(doom_loop_token_threshold=10_000),
    )
    # Burn tokens without any completion
    for _ in range(3):
        _emit("test-5", "llm.completed", payload={"tokens_total": 4000, "estimated_cost": 0.0})

    assert "ant-0" in sentry.halted_ants


def test_sentry_doom_loop_resets_on_completion():
    sentry = Sentry(
        run_id="test-6",
        max_budget_tokens=1_000_000,
        config=SentryConfig(doom_loop_token_threshold=10_000),
    )
    _emit("test-6", "llm.completed", payload={"tokens_total": 5000, "estimated_cost": 0.0})
    # Completion resets the counter
    _emit("test-6", "pipeline.step_completed", payload={"step": "implementer"})
    _emit("test-6", "llm.completed", payload={"tokens_total": 5000, "estimated_cost": 0.0})

    assert "ant-0" not in sentry.halted_ants


def test_sentry_consecutive_failures():
    sentry = Sentry(
        run_id="test-7",
        max_budget_tokens=1_000_000,
        config=SentryConfig(max_consecutive_failures=2),
    )
    _emit("test-7", "llm.error", agent_id="ant-1", payload={})
    assert "ant-1" not in sentry.halted_ants

    _emit("test-7", "llm.error", agent_id="ant-1", payload={})
    assert "ant-1" in sentry.halted_ants


def test_sentry_consecutive_failures_reset_on_success():
    sentry = Sentry(
        run_id="test-8",
        max_budget_tokens=1_000_000,
        config=SentryConfig(max_consecutive_failures=3),
    )
    _emit("test-8", "llm.error", agent_id="ant-0", payload={})
    _emit("test-8", "llm.error", agent_id="ant-0", payload={})
    # Success resets
    _emit("test-8", "pipeline.step_completed", agent_id="ant-0", payload={"step": "x"})
    _emit("test-8", "llm.error", agent_id="ant-0", payload={})

    assert "ant-0" not in sentry.halted_ants


def test_sentry_stall_detection():
    sentry = Sentry(
        run_id="test-9",
        max_budget_tokens=1_000_000,
        config=SentryConfig(stall_timeout_seconds=0.01),
    )
    _emit("test-9", "llm.completed", agent_id="ant-0", payload={"tokens_total": 100, "estimated_cost": 0.0})
    time.sleep(0.02)
    stalled = sentry.check_stalled()
    assert "ant-0" in stalled


def test_sentry_summary():
    sentry = Sentry(run_id="test-10", max_budget_tokens=100_000)
    _emit("test-10", "llm.completed", agent_id="ant-0", payload={"tokens_total": 1000, "estimated_cost": 0.01})
    _emit("test-10", "pipeline.step_completed", agent_id="ant-0", payload={"step": "plan"})

    summary = sentry.summary()
    assert summary["total_tokens"] == 1000
    assert summary["ants_tracked"] == 1
    assert summary["per_ant"]["ant-0"]["completions"] == 1
