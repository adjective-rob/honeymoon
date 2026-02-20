"""
GLITCHLAB Governance — Boundary Enforcement + Budget Control
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Boundary Enforcement
# ---------------------------------------------------------------------------

class BoundaryViolation(Exception):
    """Raised when an agent tries to touch a protected path."""
    pass


class BoundaryEnforcer:
    """
    Prevents agents from modifying protected paths
    unless explicitly overridden.
    """

    def __init__(self, protected_paths: list[str]):
        self.protected_paths = protected_paths

    def check(self, files: list[str], allow_core: bool = False) -> list[str]:
        """
        Check a list of files against protected paths.

        Returns list of violations. Empty = clean.
        Raises BoundaryViolation if allow_core is False and violations found.
        """
        violations = []
        for f in files:
            for protected in self.protected_paths:
                if f.startswith(protected):
                    violations.append(f)

        if violations and not allow_core:
            raise BoundaryViolation(
                f"Core boundary violation! Files: {violations}\n"
                f"Protected paths: {self.protected_paths}\n"
                f"Use --allow-core to override."
            )

        return violations

    def check_plan(self, plan: dict, allow_core: bool = False) -> list[str]:
        """Check a planner output for boundary violations."""
        files = plan.get("files_likely_affected", [])
        for step in plan.get("steps", []):
            files.extend(step.get("files", []))
        return self.check(list(set(files)), allow_core)
