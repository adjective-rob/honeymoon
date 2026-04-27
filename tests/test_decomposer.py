"""Tests for the TaskDecomposer — step partitioning and overlap detection."""

from glitchlab.decomposer import TaskDecomposer


def test_partition_independent_steps():
    """Steps with no file overlap become separate sub-tasks."""
    decomposer = TaskDecomposer.__new__(TaskDecomposer)
    steps = [
        {"description": "Fix A", "files": ["a.py"], "code_hint": "fix", "do_not_touch": []},
        {"description": "Fix B", "files": ["b.py"], "code_hint": "fix", "do_not_touch": []},
        {"description": "Fix C", "files": ["c.py"], "code_hint": "fix", "do_not_touch": []},
    ]
    subtasks = decomposer._partition_steps(steps, "parent task", [])
    assert len(subtasks) == 3
    assert subtasks[0].files == ["a.py"]
    assert subtasks[1].files == ["b.py"]
    assert subtasks[2].files == ["c.py"]


def test_partition_overlapping_steps_merge():
    """Steps that share files get merged into one sub-task."""
    decomposer = TaskDecomposer.__new__(TaskDecomposer)
    steps = [
        {"description": "Fix A", "files": ["shared.py", "a.py"], "code_hint": "", "do_not_touch": []},
        {"description": "Fix B", "files": ["shared.py", "b.py"], "code_hint": "", "do_not_touch": []},
        {"description": "Fix C", "files": ["c.py"], "code_hint": "", "do_not_touch": []},
    ]
    subtasks = decomposer._partition_steps(steps, "parent task", [])
    assert len(subtasks) == 2
    # First group should have a.py, b.py, shared.py merged
    merged_files = set(subtasks[0].files)
    assert "shared.py" in merged_files
    assert "a.py" in merged_files
    assert "b.py" in merged_files
    # Second group is independent
    assert subtasks[1].files == ["c.py"]


def test_partition_transitive_overlap():
    """A-B overlap and B-C overlap should merge all three."""
    decomposer = TaskDecomposer.__new__(TaskDecomposer)
    steps = [
        {"description": "A", "files": ["x.py", "y.py"], "code_hint": "", "do_not_touch": []},
        {"description": "B", "files": ["y.py", "z.py"], "code_hint": "", "do_not_touch": []},
        {"description": "C", "files": ["z.py", "w.py"], "code_hint": "", "do_not_touch": []},
    ]
    subtasks = decomposer._partition_steps(steps, "parent", [])
    assert len(subtasks) == 1
    assert set(subtasks[0].files) == {"w.py", "x.py", "y.py", "z.py"}


def test_partition_adds_file_constraint():
    """Each sub-task gets a constraint limiting it to its files."""
    decomposer = TaskDecomposer.__new__(TaskDecomposer)
    steps = [
        {"description": "A", "files": ["a.py"], "code_hint": "", "do_not_touch": []},
    ]
    subtasks = decomposer._partition_steps(steps, "parent", ["no new deps"])
    assert len(subtasks) == 1
    assert "no new deps" in subtasks[0].constraints
    assert any("Only modify these files" in c for c in subtasks[0].constraints)


def test_partition_detects_dependencies_via_do_not_touch():
    """If step A's do_not_touch mentions files in step B, A depends on B."""
    decomposer = TaskDecomposer.__new__(TaskDecomposer)
    steps = [
        {"description": "A", "files": ["a.py"], "code_hint": "", "do_not_touch": ["b.py"]},
        {"description": "B", "files": ["b.py"], "code_hint": "", "do_not_touch": []},
    ]
    subtasks = decomposer._partition_steps(steps, "parent", [])
    assert len(subtasks) == 2
    # subtask 0 (a.py) should depend on subtask 1 (b.py)
    assert subtasks[0].depends_on == [subtasks[1].subtask_id]


def test_merge_overlapping_idempotent():
    """Merging already non-overlapping groups should be a no-op."""
    groups = [
        {"files": {"a.py"}, "steps": [{"description": "A"}]},
        {"files": {"b.py"}, "steps": [{"description": "B"}]},
    ]
    result = TaskDecomposer._merge_overlapping(groups)
    assert len(result) == 2


def test_merge_overlapping_chain():
    """Chain overlap: A∩B and B∩C should merge into one group."""
    groups = [
        {"files": {"a.py", "b.py"}, "steps": [{"description": "A"}]},
        {"files": {"b.py", "c.py"}, "steps": [{"description": "B"}]},
        {"files": {"c.py", "d.py"}, "steps": [{"description": "C"}]},
    ]
    result = TaskDecomposer._merge_overlapping(groups)
    assert len(result) == 1
    assert result[0]["files"] == {"a.py", "b.py", "c.py", "d.py"}
