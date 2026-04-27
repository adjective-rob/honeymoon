"""Tests for the mission system — profiles, loader, and overrides."""

from pathlib import Path
from types import SimpleNamespace

from honeymoon.mission import (
    Mission,
    AgentOverride,
    INVESTIGATION_TOOLS,
    apply_mission_overrides,
    list_missions,
    load_mission,
)


def test_list_missions():
    missions = list_missions()
    assert "investigate" in missions
    assert "bulk" in missions
    assert "monitor" in missions


def test_load_investigate_mission():
    mission = load_mission("investigate")
    assert mission.name == "investigate"
    assert mission.output_mode == "report"
    assert mission.pipeline is not None
    assert len(mission.pipeline) == 3  # planner, analyst, verifier
    assert "implementer" in mission.overrides
    assert mission.overrides["implementer"].read_only is True
    assert mission.overrides["implementer"].label == "The Analyst"


def test_load_bulk_mission():
    mission = load_mission("bulk")
    assert mission.name == "bulk"
    assert mission.output_mode == "pr"
    assert mission.pipeline is None  # uses default
    assert mission.overrides == {}


def test_load_monitor_mission():
    mission = load_mission("monitor")
    assert mission.name == "monitor"
    assert mission.output_mode == "report"
    assert mission.pipeline is not None
    assert mission.overrides["implementer"].read_only is True


def test_load_unknown_mission_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown mission"):
        load_mission("nonexistent")


def test_mission_is_read_only():
    mission = Mission(
        name="test",
        overrides={"implementer": AgentOverride(role="implementer", read_only=True)},
    )
    assert mission.is_read_only is True


def test_mission_not_read_only():
    mission = Mission(name="test", overrides={})
    assert mission.is_read_only is False


def test_apply_overrides_replaces_system_prompt():
    agent = SimpleNamespace(system_prompt="original prompt")
    agents = {"implementer": agent}
    mission = Mission(
        name="test",
        overrides={
            "implementer": AgentOverride(
                role="implementer",
                system_prompt_override="new prompt",
            ),
        },
    )
    apply_mission_overrides(agents, mission)
    assert agent.system_prompt == "new prompt"


def test_apply_overrides_prepends_system_prompt():
    agent = SimpleNamespace(system_prompt="original prompt")
    agents = {"planner": agent}
    mission = Mission(
        name="test",
        overrides={
            "planner": AgentOverride(
                role="planner",
                system_prompt_prepend="INVESTIGATION MODE.\n",
            ),
        },
    )
    apply_mission_overrides(agents, mission)
    assert agent.system_prompt.startswith("INVESTIGATION MODE.")
    assert "original prompt" in agent.system_prompt


def test_apply_overrides_marks_read_only():
    agent = SimpleNamespace(system_prompt="prompt")
    agents = {"implementer": agent}
    mission = Mission(
        name="test",
        overrides={
            "implementer": AgentOverride(role="implementer", read_only=True),
        },
    )
    apply_mission_overrides(agents, mission)
    assert agent._mission_read_only is True


def test_apply_overrides_sets_label():
    agent = SimpleNamespace(system_prompt="prompt")
    agents = {"implementer": agent}
    mission = Mission(
        name="test",
        overrides={
            "implementer": AgentOverride(role="implementer", label="The Analyst"),
        },
    )
    apply_mission_overrides(agents, mission)
    assert agent._mission_label == "The Analyst"


def test_apply_overrides_skips_missing_agent():
    agents = {}
    mission = Mission(
        name="test",
        overrides={
            "nonexistent": AgentOverride(role="nonexistent", label="Ghost"),
        },
    )
    # Should not raise
    apply_mission_overrides(agents, mission)


def test_investigation_tools_are_read_only():
    tool_names = {t["function"]["name"] for t in INVESTIGATION_TOOLS}
    assert "read_file" in tool_names
    assert "search_grep" in tool_names
    assert "submit_findings" in tool_names
    # Must NOT have write tools
    assert "write_file" not in tool_names
    assert "replace_in_file" not in tool_names
    assert "create_file" not in tool_names


def test_repo_level_mission_takes_priority(tmp_path: Path):
    """Repo-level mission profiles override built-in ones."""
    missions_dir = tmp_path / ".honeymoon" / "missions"
    missions_dir.mkdir(parents=True)
    (missions_dir / "custom.yaml").write_text("""
name: custom
description: "Custom repo mission"
output_mode: report
pipeline: default
agent_overrides: {}
""")
    mission = load_mission("custom", tmp_path)
    assert mission.name == "custom"
    assert mission.description == "Custom repo mission"
