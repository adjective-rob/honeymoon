"""
HONEYMOON Mission System — Reconfigurable Agent Behavior

Missions make Honeymoon's agents adaptable to different work types.
Instead of hardcoded code-writing behavior, agents get their prompts,
tools, and output mode from a mission profile.

Three mission classes:
  - investigate: Read-only forensics with signed reports
  - bulk: High-volume mechanical code changes (default Honeymoon)
  - monitor: Continuous watch mode with signed alerts

Architecture:
  - Mission profiles live in honeymoon/missions/*.yaml
  - MissionLoader reads a profile and produces agent overrides
  - The Controller applies overrides before running the pipeline
  - The output mode determines PR vs signed report
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from honeymoon.config_loader import PipelineStep


# ---------------------------------------------------------------------------
# Mission data model
# ---------------------------------------------------------------------------

@dataclass
class AgentOverride:
    """Behavioral override for a single agent within a mission."""

    role: str
    label: str = ""                       # Display name (e.g., "The Analyst")
    read_only: bool = False               # Strip write tools
    system_prompt_override: str = ""      # Full replacement
    system_prompt_prepend: str = ""       # Prepended to existing prompt


@dataclass
class Mission:
    """A loaded mission profile."""

    name: str
    description: str = ""
    output_mode: str = "pr"               # "pr" or "report"
    pipeline: list[PipelineStep] | None = None  # None = use default
    overrides: dict[str, AgentOverride] = field(default_factory=dict)

    @property
    def is_read_only(self) -> bool:
        """True if any agent override is read-only."""
        return any(o.read_only for o in self.overrides.values())

    def get_override(self, role: str) -> AgentOverride | None:
        return self.overrides.get(role)


# ---------------------------------------------------------------------------
# Investigation tool set (read-only)
# ---------------------------------------------------------------------------

INVESTIGATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Plan your investigation strategy. Map what you need to search for and why.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy": {"type": "string", "description": "Your investigation approach"},
                    "hypotheses": {"type": "string", "description": "What you expect to find and why"},
                },
                "required": ["strategy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Use start_line/end_line for specific ranges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "description": "First line (1-indexed, optional)"},
                    "end_line": {"type": "integer", "description": "Last line (1-indexed, optional)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_function",
            "description": "Extract the full body of a function or method by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Function or method name"},
                    "file": {"type": "string", "description": "Optional file path to restrict search"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_class",
            "description": "Get a class outline — method signatures with bodies collapsed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "file": {"type": "string", "description": "Optional file path"},
                },
                "required": ["class_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_grep",
            "description": "Search the codebase for a pattern. Returns matching lines with file paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "file_type": {"type": "string", "default": "*.py"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findings",
            "description": "Submit your investigation findings. Call this when your analysis is complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Executive summary of findings",
                    },
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "evidence": {"type": "string", "description": "File:line references and code snippets"},
                                "analysis": {"type": "string", "description": "What this means"},
                                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            },
                            "required": ["title", "evidence", "analysis", "severity", "confidence"],
                        },
                        "description": "List of individual findings with evidence",
                    },
                    "recommendations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Actionable recommendations based on findings",
                    },
                },
                "required": ["summary", "findings"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

# Built-in mission directory
_MISSIONS_DIR = Path(__file__).parent / "missions"


def load_mission(name: str, repo_path: Path | None = None) -> Mission:
    """Load a mission profile by name.

    Search order:
      1. Repo-level: .honeymoon/missions/{name}.yaml
      2. Built-in: honeymoon/missions/{name}.yaml

    Returns a Mission with parsed pipeline and agent overrides.
    """
    candidates = []
    if repo_path:
        candidates.append(repo_path / ".honeymoon" / "missions" / f"{name}.yaml")
    candidates.append(_MISSIONS_DIR / f"{name}.yaml")

    profile_path = None
    for c in candidates:
        if c.exists():
            profile_path = c
            break

    if profile_path is None:
        raise ValueError(
            f"Unknown mission: {name!r}. "
            f"Available: {', '.join(list_missions())}"
        )

    raw = yaml.safe_load(profile_path.read_text())
    logger.info(f"[MISSION] Loaded profile: {name} ({profile_path})")

    # Parse pipeline
    pipeline = None
    if raw.get("pipeline") and raw["pipeline"] != "default":
        pipeline = [
            PipelineStep(**step) for step in raw["pipeline"]
        ]

    # Parse agent overrides
    overrides: dict[str, AgentOverride] = {}
    for role, override_data in (raw.get("agent_overrides") or {}).items():
        overrides[role] = AgentOverride(
            role=role,
            label=override_data.get("label", ""),
            read_only=override_data.get("read_only", False),
            system_prompt_override=override_data.get("system_prompt_override", ""),
            system_prompt_prepend=override_data.get("system_prompt_prepend", ""),
        )

    return Mission(
        name=raw.get("name", name),
        description=raw.get("description", ""),
        output_mode=raw.get("output_mode", "pr"),
        pipeline=pipeline,
        overrides=overrides,
    )


def list_missions() -> list[str]:
    """Return names of all available built-in missions."""
    return sorted(
        p.stem for p in _MISSIONS_DIR.glob("*.yaml")
        if not p.name.startswith("_")
    )


# ---------------------------------------------------------------------------
# Agent override application
# ---------------------------------------------------------------------------

def apply_mission_overrides(
    agents: dict[str, Any],
    mission: Mission,
) -> None:
    """Apply mission overrides to instantiated agents.

    Modifies agents in-place:
      - Swaps system_prompt if override/prepend specified
      - Marks read-only agents (controller checks this)
    """
    for role, override in mission.overrides.items():
        agent = agents.get(role)
        if agent is None:
            continue

        if override.system_prompt_override:
            agent.system_prompt = override.system_prompt_override
            logger.debug(f"[MISSION] {role}: system prompt replaced")
        elif override.system_prompt_prepend:
            agent.system_prompt = override.system_prompt_prepend + "\n\n" + agent.system_prompt
            logger.debug(f"[MISSION] {role}: system prompt prepended")

        if override.read_only:
            agent._mission_read_only = True
            logger.debug(f"[MISSION] {role}: marked read-only")

        if override.label:
            agent._mission_label = override.label
            logger.debug(f"[MISSION] {role}: labeled as {override.label!r}")
