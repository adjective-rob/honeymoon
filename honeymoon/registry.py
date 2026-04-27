"""Centralised agent registry for HONEYMOON.

Maps role names to agent classes and provides a factory function for
instantiating agents by role.
"""

from __future__ import annotations

from honeymoon.agents import BaseAgent
from honeymoon.agents.archivist import ArchivistAgent
from honeymoon.agents.debugger import DebuggerAgent
from honeymoon.agents.implementer import ImplementerAgent
from honeymoon.agents.planner import PlannerAgent
from honeymoon.agents.release import ReleaseAgent
from honeymoon.agents.security import SecurityAgent
from honeymoon.agents.testgen import TestGenAgent
from honeymoon.router import Router

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "planner": PlannerAgent,
    "implementer": ImplementerAgent,
    "debugger": DebuggerAgent,
    "security": SecurityAgent,
    "release": ReleaseAgent,
    "archivist": ArchivistAgent,
    "testgen": TestGenAgent,
}


def get_agent(role: str, router: Router) -> BaseAgent:
    """Instantiate an agent by role name.

    Raises ``ValueError`` if *role* is not present in the registry.
    """
    cls = AGENT_REGISTRY.get(role)
    if not cls:
        raise ValueError(f"Unknown agent role: {role}")
    return cls(router)
