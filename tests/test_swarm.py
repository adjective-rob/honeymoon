"""Tests for the swarm runner — wave building and sub-task partitioning."""

from honeymoon.swarm import SubTask, _build_waves, _subtask_to_dict


def test_no_subtasks_returns_empty():
    assert _build_waves([]) == []


def test_independent_subtasks_single_wave():
    subtasks = [
        SubTask(subtask_id="a", objective="do A", files=["x.py"]),
        SubTask(subtask_id="b", objective="do B", files=["y.py"]),
    ]
    waves = _build_waves(subtasks)
    assert len(waves) == 1
    assert len(waves[0]) == 2


def test_dependent_subtasks_two_waves():
    subtasks = [
        SubTask(subtask_id="a", objective="do A"),
        SubTask(subtask_id="b", objective="do B", depends_on=["a"]),
    ]
    waves = _build_waves(subtasks)
    assert len(waves) == 2
    assert waves[0][0].subtask_id == "a"
    assert waves[1][0].subtask_id == "b"


def test_chain_dependency_three_waves():
    subtasks = [
        SubTask(subtask_id="c", objective="do C", depends_on=["b"]),
        SubTask(subtask_id="a", objective="do A"),
        SubTask(subtask_id="b", objective="do B", depends_on=["a"]),
    ]
    waves = _build_waves(subtasks)
    assert len(waves) == 3
    ids_by_wave = [[st.subtask_id for st in w] for w in waves]
    assert ids_by_wave == [["a"], ["b"], ["c"]]


def test_diamond_dependency():
    subtasks = [
        SubTask(subtask_id="a", objective="root"),
        SubTask(subtask_id="b", objective="left", depends_on=["a"]),
        SubTask(subtask_id="c", objective="right", depends_on=["a"]),
        SubTask(subtask_id="d", objective="merge", depends_on=["b", "c"]),
    ]
    waves = _build_waves(subtasks)
    assert len(waves) == 3
    # Wave 0: a
    assert [st.subtask_id for st in waves[0]] == ["a"]
    # Wave 1: b and c (parallel)
    wave1_ids = {st.subtask_id for st in waves[1]}
    assert wave1_ids == {"b", "c"}
    # Wave 2: d
    assert [st.subtask_id for st in waves[2]] == ["d"]


def test_unresolvable_deps_fall_through():
    subtasks = [
        SubTask(subtask_id="a", objective="do A", depends_on=["nonexistent"]),
    ]
    waves = _build_waves(subtasks)
    # Should still produce a wave (dumps unresolvable into final wave)
    assert len(waves) == 1
    assert waves[0][0].subtask_id == "a"


def test_subtask_to_dict_round_trip():
    st = SubTask(
        subtask_id="abc",
        objective="fix bug",
        files=["a.py", "b.py"],
        code_hint="change the return value",
        constraints=["no new deps"],
    )
    d = _subtask_to_dict(st)
    assert d["subtask_id"] == "abc"
    assert d["files"] == ["a.py", "b.py"]
    assert d["code_hint"] == "change the return value"
    assert d["constraints"] == ["no new deps"]
