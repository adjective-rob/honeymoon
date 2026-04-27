"""
GLITCHLAB Task Decomposer — Splits tasks into non-overlapping sub-tasks.

The decomposer is the critical capability that makes swarm mode work.
It takes a task objective and produces a list of SubTasks where:
  - Each sub-task touches different files (no overlap)
  - Each sub-task is small enough for a weak/quantized model
  - Dependencies between sub-tasks are explicit

The decomposer uses the planner agent in a special "decompose" mode:
instead of producing an ExecutionPlan for one implementer, it produces
a partition of work for multiple ants.

If the task is too small to decompose (≤2 files), it returns a single
sub-task — the swarm runner handles this gracefully.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from glitchlab.agents.planner import PlannerAgent
from glitchlab.agents import AgentContext
from glitchlab.config_loader import GlitchLabConfig
from glitchlab.router import Router
from glitchlab.swarm import SubTask


# ---------------------------------------------------------------------------
# Decomposition prompt — injected as the planner's system prompt override
# ---------------------------------------------------------------------------

DECOMPOSER_SYSTEM_PROMPT = """You are the GLITCHLAB Task Decomposer.

Your job is to take a development task and split it into INDEPENDENT sub-tasks
that can be executed in parallel by separate workers. Each worker has its own
copy of the repository and cannot see the other workers' changes.

CRITICAL RULES:
1. Sub-tasks MUST NOT overlap in files. If two sub-tasks touch the same file,
   they will conflict. Assign each file to exactly one sub-task.
2. Keep sub-tasks small. Each should be completable in 1-2 steps.
3. If a task is too small to split (≤2 files), return a single sub-task.
4. Mark dependencies explicitly. If sub-task B requires the output of A
   (e.g., B imports a function that A creates), set depends_on: ["A"].
5. Each sub-task needs a clear, self-contained objective. The worker
   will not see the other sub-tasks' objectives.

Output format — return ONLY a JSON array:
[
  {
    "subtask_id": "short-kebab-id",
    "objective": "Clear, self-contained description of what to do",
    "files": ["path/to/file1.py", "path/to/file2.py"],
    "code_hint": "Brief sketch of the change",
    "constraints": ["Don't modify X", "Keep backward compat"],
    "depends_on": []
  }
]

Rules for good decomposition:
- Group files that MUST change together into the same sub-task
- If file A imports from file B and both need changes, put them together
- Interface changes (adding a parameter) go in the same sub-task as all callers
- Test files go with the code they test
- Config changes go with the code that reads the config
"""


# ---------------------------------------------------------------------------
# Decomposer
# ---------------------------------------------------------------------------

class TaskDecomposer:
    """Splits a task into non-overlapping sub-tasks for swarm execution."""

    def __init__(self, router: Router, config: GlitchLabConfig):
        self.router = router
        self.config = config

    def decompose(
        self,
        objective: str,
        repo_path: str,
        working_dir: str,
        file_context: dict[str, str] | None = None,
        constraints: list[str] | None = None,
        symbol_index: Any | None = None,
    ) -> list[SubTask]:
        """Decompose a task into sub-tasks.

        First runs the regular planner to get an ExecutionPlan, then
        partitions the plan steps into non-overlapping sub-tasks.
        If the plan is small enough (≤2 steps), returns a single sub-task.
        """
        # Step 1: Get a regular plan from the planner
        planner = PlannerAgent(self.router)
        context = AgentContext(
            task_id="decompose",
            objective=objective,
            repo_path=repo_path,
            working_dir=working_dir,
            file_context=file_context or {},
            constraints=constraints or [],
            extra={"symbol_index": symbol_index},
        )

        plan = planner.run(context)

        if plan.get("parse_error"):
            logger.warning("[DECOMPOSER] Planner failed, returning single sub-task")
            return [SubTask(
                subtask_id="fallback-0",
                objective=objective,
                constraints=constraints or [],
            )]

        steps = plan.get("steps", [])

        # Step 2: If small enough, don't decompose
        if len(steps) <= 2:
            logger.info(f"[DECOMPOSER] Plan has {len(steps)} steps — no decomposition needed")
            all_files = []
            for s in steps:
                all_files.extend(s.get("files", []))
            return [SubTask(
                subtask_id="single-0",
                objective=objective,
                files=list(set(all_files)),
                constraints=constraints or [],
            )]

        # Step 3: Partition steps into non-overlapping sub-tasks
        return self._partition_steps(steps, objective, constraints or [])

    def _partition_steps(
        self,
        steps: list[dict],
        parent_objective: str,
        constraints: list[str],
    ) -> list[SubTask]:
        """Partition plan steps into non-overlapping sub-tasks.

        Strategy: group steps that share files into the same sub-task.
        Steps with no file overlap become independent sub-tasks.
        """
        # Build file → step mapping
        groups: list[dict] = []

        for step in steps:
            step_files = set(step.get("files", []))
            merged = False

            for group in groups:
                if step_files & group["files"]:
                    # Overlap — merge into existing group
                    group["files"] |= step_files
                    group["steps"].append(step)
                    merged = True
                    break

            if not merged:
                groups.append({
                    "files": step_files,
                    "steps": [step],
                })

        # Second pass: merge groups that now overlap due to transitive deps
        merged_groups = self._merge_overlapping(groups)

        # Convert groups to SubTasks
        subtasks = []
        for i, group in enumerate(merged_groups):
            descriptions = [s.get("description", "") for s in group["steps"]]
            code_hints = [s.get("code_hint", "") for s in group["steps"] if s.get("code_hint")]

            subtask = SubTask(
                subtask_id=f"chunk-{i}",
                objective=f"{parent_objective}\n\nSpecifically: {'; '.join(descriptions)}",
                files=sorted(group["files"]),
                code_hint="\n".join(code_hints) if code_hints else "",
                constraints=constraints + [
                    f"Only modify these files: {', '.join(sorted(group['files']))}"
                ],
            )
            subtasks.append(subtask)

        # Detect dependencies: if step B's files import from step A's files
        # (heuristic: if do_not_touch in A mentions files in B, B depends on A)
        for i, group in enumerate(merged_groups):
            for step in group["steps"]:
                dnt = set(step.get("do_not_touch", []))
                for j, other_group in enumerate(merged_groups):
                    if i != j and dnt & other_group["files"]:
                        if subtasks[j].subtask_id not in subtasks[i].depends_on:
                            subtasks[i].depends_on.append(subtasks[j].subtask_id)

        logger.info(
            f"[DECOMPOSER] Decomposed into {len(subtasks)} sub-tasks: "
            + ", ".join(f"{st.subtask_id} ({len(st.files)} files)" for st in subtasks)
        )
        return subtasks

    @staticmethod
    def _merge_overlapping(groups: list[dict]) -> list[dict]:
        """Merge groups that share files (transitive closure)."""
        changed = True
        while changed:
            changed = False
            new_groups = []
            used = set()

            for i, g1 in enumerate(groups):
                if i in used:
                    continue
                merged = {"files": set(g1["files"]), "steps": list(g1["steps"])}

                for j, g2 in enumerate(groups):
                    if j <= i or j in used:
                        continue
                    if merged["files"] & g2["files"]:
                        merged["files"] |= g2["files"]
                        merged["steps"].extend(g2["steps"])
                        used.add(j)
                        changed = True

                new_groups.append(merged)

            groups = new_groups

        return groups
