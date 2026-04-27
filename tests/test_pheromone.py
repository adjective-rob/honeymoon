"""Tests for the pheromone trail — GLITCHLAB swarm awareness layer."""

import json
from pathlib import Path

from glitchlab.pheromone import PheromoneWriter, PheromoneReader, PheromoneTrail


def test_writer_creates_trail_file(tmp_path: Path):
    trail_path = tmp_path / ".glitchlab" / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    writer.claim("ant-0", "run-1", "src/main.py")
    assert trail_path.exists()
    lines = trail_path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["ptype"] == "claim"
    assert record["ant_id"] == "ant-0"
    assert record["target"] == "src/main.py"


def test_reader_active_claims(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.claim("ant-0", "run-1", "src/a.py")
    writer.claim("ant-1", "run-1", "src/b.py")

    claims = reader.active_claims("run-1")
    assert claims == {"src/a.py": "ant-0", "src/b.py": "ant-1"}


def test_release_removes_claim(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.claim("ant-0", "run-1", "src/a.py")
    writer.release("ant-0", "run-1", "src/a.py")

    claims = reader.active_claims("run-1")
    assert claims == {}


def test_release_only_affects_own_claim(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.claim("ant-0", "run-1", "src/a.py")
    # ant-1 tries to release ant-0's claim — should have no effect
    writer.release("ant-1", "run-1", "src/a.py")

    claims = reader.active_claims("run-1")
    assert claims == {"src/a.py": "ant-0"}


def test_is_claimed_returns_holder(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.claim("ant-0", "run-1", "src/a.py")
    assert reader.is_claimed("run-1", "src/a.py") == "ant-0"
    assert reader.is_claimed("run-1", "src/b.py") is None


def test_completed_subtasks(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.complete("ant-0", "run-1", "task-001")
    writer.complete("ant-1", "run-1", "task-002")

    completed = reader.completed_subtasks("run-1")
    assert completed == {"task-001", "task-002"}


def test_failed_subtasks_newest_first(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.fail("ant-0", "run-1", "task-001", "import error")
    writer.fail("ant-1", "run-1", "task-002", "test failed")

    failures = reader.failed_subtasks("run-1")
    assert len(failures) == 2
    # Newest first
    assert failures[0].subtask_id == "task-002"
    assert failures[0].data["error"] == "test failed"


def test_recent_tool_errors(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    for i in range(7):
        writer.tool_error("ant-0", "run-1", f"cmd-{i}", f"err-{i}")

    errors = reader.recent_tool_errors("run-1", limit=3)
    assert len(errors) == 3
    assert errors[0]["command"] == "cmd-4"
    assert errors[2]["command"] == "cmd-6"


def test_run_id_isolation(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.claim("ant-0", "run-1", "src/a.py")
    writer.claim("ant-0", "run-2", "src/b.py")

    assert reader.active_claims("run-1") == {"src/a.py": "ant-0"}
    assert reader.active_claims("run-2") == {"src/b.py": "ant-0"}


def test_trail_claim_rejects_if_held(tmp_path: Path):
    trail = PheromoneTrail(tmp_path, "run-1", subscribe=False)

    assert trail.claim("ant-0", "src/a.py") is True
    assert trail.claim("ant-1", "src/a.py") is False  # ant-0 holds it
    assert trail.claim("ant-0", "src/a.py") is True   # re-claim by same ant is fine


def test_trail_clear(tmp_path: Path):
    trail = PheromoneTrail(tmp_path, "run-1", subscribe=False)
    trail.claim("ant-0", "src/a.py")
    assert trail.active_claims() == {"src/a.py": "ant-0"}

    trail.clear()
    assert trail.active_claims() == {}


def test_ant_progress(tmp_path: Path):
    trail_path = tmp_path / "pheromones.jsonl"
    writer = PheromoneWriter(trail_path)
    reader = PheromoneReader(trail_path)

    writer.claim("ant-0", "run-1", "src/a.py")
    writer.complete("ant-0", "run-1", "task-001")
    writer.fail("ant-1", "run-1", "task-002", "oops")

    progress = reader.ant_progress("run-1")
    assert progress["ant-0"]["claims"] == 1
    assert progress["ant-0"]["completions"] == 1
    assert progress["ant-1"]["failures"] == 1


def test_empty_trail_returns_empty(tmp_path: Path):
    reader = PheromoneReader(tmp_path / "nonexistent.jsonl")
    assert reader.active_claims("run-1") == {}
    assert reader.completed_subtasks("run-1") == set()
    assert reader.failed_subtasks("run-1") == []
    assert reader.recent_tool_errors("run-1") == []
