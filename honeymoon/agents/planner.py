"""
👑 The Queen — Planner

Breaks down tasks into execution steps.
Identifies risks, maps impacted files, decides scope.
Never writes code. Only plans. Directs the hive.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

from honeymoon.agents import AgentContext, BaseAgent
from honeymoon.router import RouterResponse


# ---------------------------------------------------------------------------
# Strict Output Schemas
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    step_number: int
    description: str
    files: list[str] = Field(min_length=1, description="Must contain at least one valid file path")
    action: Literal["modify", "create", "delete"]
    do_not_touch: list[str] = Field(
        default_factory=list,
        description="Files or functions adjacent to this change that must NOT be modified",
    )
    code_hint: str = Field(
        default="",
        description="Pseudocode or code sketch showing the shape of the change. Not a full implementation.",
    )


class ExecutionPlan(BaseModel):
    steps: list[PlanStep]
    files_likely_affected: list[str]
    do_not_touch: list[str] = Field(
        default_factory=list,
        description="Files, functions, or code regions that are adjacent to the change but must remain untouched",
    )
    requires_core_change: bool
    risk_level: Literal["low", "medium", "high"]
    risk_notes: str
    test_strategy: list[str] = Field(default_factory=list)
    estimated_complexity: Literal["trivial", "small", "medium", "large"]
    dependencies_affected: bool
    public_api_changed: bool
    self_review_notes: str

    @field_validator("test_strategy", mode="before")
    @classmethod
    def coerce_test_strategy(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(i) for i in v]
        return []

    @field_validator("dependencies_affected", mode="before")
    @classmethod
    def coerce_dependencies_affected(cls, v: Any) -> bool:
        if isinstance(v, list):
            return len(v) > 0
        return bool(v)


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

PLANNER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Reason about the task, analyze what you've read, and draft your plan before submitting it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis": {"type": "string", "description": "Your analysis of the task and codebase"},
                    "draft_plan": {"type": "string", "description": "Your draft plan outline"}
                },
                "required": ["analysis"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_function",
            "description": "Read the complete body of a function or method. Use this to verify insertion points before including them in your plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Function or method name"},
                    "file": {"type": "string", "description": "Optional file path to restrict search"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_class",
            "description": "Get a class outline showing method signatures with bodies collapsed. Use to understand class structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "file": {"type": "string", "description": "Optional file path"}
                },
                "required": ["class_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_grep",
            "description": "Search the codebase for a pattern. Use to find where things are defined or used.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "file_type": {"type": "string", "default": "*.py"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Submit your final execution plan as JSON. This ends the planning loop. The JSON must conform to the ExecutionPlan schema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_json": {"type": "string", "description": "The complete execution plan as a JSON string"}
                },
                "required": ["plan_json"]
            }
        }
    }
]


class PlannerAgent(BaseAgent):
    role = "planner"

    system_prompt = """You are The Queen, HONEYMOON's planner. Produce a JSON execution plan.

Schema: { steps: [{ step_number, description, files: [path], action: modify|create|delete, do_not_touch: [path], code_hint: "sketch" }], files_likely_affected, do_not_touch, requires_core_change, risk_level: low|medium|high, risk_notes, test_strategy, estimated_complexity: trivial|small|medium|large, dependencies_affected, public_api_changed, self_review_notes }

Rules:
- Max 4 steps. Combine same-file edits. Every step needs files, code_hint, do_not_touch.
- No read-only or test-running steps. Only file mutations.
- Use get_function/get_class/search_grep to explore BEFORE submitting. code_hints must reference real code.
- Call submit_plan with the JSON when ready.
"""

    def run(self, context: AgentContext, **kwargs) -> dict[str, Any]:
        """Execute the planner in an agentic loop with read-only tools."""
        import subprocess
        from pathlib import Path

        messages = self.build_messages(context)
        self._plan_rejection_sent = False
        workspace_dir = Path(context.working_dir)
        symbol_index = context.extra.get("symbol_index")

        max_steps = 5

        for step in range(max_steps):
            step_kwargs = dict(kwargs)
            # Remove response_format — can't use JSON mode with tools
            step_kwargs.pop("response_format", None)

            if step == 0:
                step_kwargs["tool_choice"] = {"type": "function", "function": {"name": "think"}}

            # Circuit breaker: force submission on final step
            if step == max_steps - 1:
                messages.append({
                    "role": "user",
                    "content": "FINAL STEP. You MUST call submit_plan now with your best plan. No more reading or thinking.",
                })
                step_kwargs["tool_choice"] = {"type": "function", "function": {"name": "submit_plan"}}

            response = self.router.complete(
                role=self.role,
                messages=messages,
                tools=PLANNER_TOOLS,
                max_tokens=8192,
                **step_kwargs
            )

            # Append assistant message
            assist_msg: dict[str, Any] = {"role": "assistant"}
            if response.content:
                assist_msg["content"] = response.content
            if response.tool_calls:
                assist_msg["tool_calls"] = [
                    tc.model_dump() if hasattr(tc, "model_dump") else dict(tc)
                    for tc in response.tool_calls
                ]
            messages.append(assist_msg)

            if not response.tool_calls:
                # If the model returns plain text, try to parse it as JSON (fallback)
                if response.content:
                    return self.parse_response(response, context)
                messages.append({
                    "role": "user",
                    "content": "Use your tools to explore the codebase, then call submit_plan with your JSON plan.",
                })
                continue

            for tool_call in response.tool_calls:
                tc_id = tool_call.id
                tc_name = tool_call.function.name
                try:
                    tc_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    messages.append({"role": "tool", "tool_call_id": tc_id, "name": tc_name, "content": "Invalid JSON."})
                    continue

                if tc_name == "think":
                    messages.append({
                        "role": "tool", "tool_call_id": tc_id, "name": tc_name,
                        "content": "Analysis noted. Explore the codebase or submit your plan.",
                    })

                elif tc_name == "get_function":
                    symbol = tc_args.get("symbol")
                    file_path = tc_args.get("file")
                    if symbol_index:
                        func_data = symbol_index.get_function_body(symbol, file_path)
                        if func_data:
                            res = (
                                f"Function '{symbol}' in {func_data['file']} "
                                f"(Lines {func_data['line_start']}-{func_data['line_end']}):\n\n"
                                f"{func_data['body']}"
                            )
                        else:
                            res = f"Function '{symbol}' not found."
                    else:
                        res = "AST parser unavailable."
                    messages.append({"role": "tool", "tool_call_id": tc_id, "name": tc_name, "content": res})

                elif tc_name == "get_class":
                    class_name = tc_args.get("class_name")
                    file_path = tc_args.get("file")
                    if symbol_index:
                        class_data = symbol_index.get_class_outline(class_name, file_path)
                        if class_data:
                            res = (
                                f"Class '{class_name}' in {class_data['file']} "
                                f"(Lines {class_data['line_start']}-{class_data['line_end']}):\n\n"
                                f"{class_data['outline']}"
                            )
                        else:
                            res = f"Class '{class_name}' not found."
                    else:
                        res = "AST parser unavailable."
                    messages.append({"role": "tool", "tool_call_id": tc_id, "name": tc_name, "content": res})

                elif tc_name == "search_grep":
                    pattern = tc_args.get("pattern")
                    file_type = tc_args.get("file_type", "*.py")
                    try:
                        cmd = [
                            "grep", "-rn", f"--include={file_type}",
                            "--exclude-dir=.honeymoon", "--exclude-dir=__pycache__",
                            "--exclude-dir=.git", pattern, ".",
                        ]
                        proc = subprocess.run(cmd, cwd=workspace_dir, capture_output=True, text=True, timeout=10)
                        lines = proc.stdout.splitlines()
                        res = "\n".join(lines[:15]) if lines else "No matches."
                    except Exception as e:
                        res = f"Search failed: {e}"
                    messages.append({"role": "tool", "tool_call_id": tc_id, "name": tc_name, "content": res})

                elif tc_name == "submit_plan":
                    plan_json = tc_args.get("plan_json", "")

                    # Reject oversized plans — one chance to condense
                    try:
                        import json as _json
                        plan_data = _json.loads(plan_json)
                        plan_steps = plan_data.get("steps", [])
                        if len(plan_steps) > 4 and not self._plan_rejection_sent:
                            self._plan_rejection_sent = True
                            res = (
                                f"REJECTED: Plan has {len(plan_steps)} steps (max 4). "
                                f"Combine steps that touch the same file into a single step. "
                                f"If the task genuinely needs 5+ steps, keep only the 4 most "
                                f"critical steps and note in risk_notes that the task may need splitting. "
                                f"Re-submit with submit_plan."
                            )
                            logger.info(f"[PLANNER] Rejected {len(plan_steps)}-step plan. Asking planner to condense.")
                            messages.append({"role": "tool", "tool_call_id": tc_id, "name": tc_name, "content": res})
                            continue
                    except (ValueError, TypeError):
                        pass  # Let parse_response handle malformed JSON

                    fake_response = RouterResponse(
                        content=plan_json,
                        model=response.model,
                        tokens_used=response.tokens_used,
                        cost=response.cost,
                        latency_ms=response.latency_ms,
                    )
                    return self.parse_response(fake_response, context)

        # Fallback: loop exhausted without submit_plan
        logger.warning("[PLANNER] Planner loop exhausted without calling submit_plan.")
        return {
            "steps": [],
            "files_likely_affected": [],
            "requires_core_change": False,
            "risk_level": "high",
            "risk_notes": "Planner failed to produce a plan within step limit",
            "test_strategy": [],
            "estimated_complexity": "unknown",
            "parse_error": True,
        }

    def build_messages(self, context: AgentContext) -> list[dict[str, str]]:
        file_context = ""
        if context.file_context:
            file_context = "\n\nRelevant file contents:\n"
            for fname, content in context.file_context.items():
                file_context += f"\n--- {fname} ---\n{content}\n"

        # Prelude: inject compact project context if available
        project_context = ""
        prelude = context.extra.get("prelude")
        if prelude and hasattr(prelude, 'compact') and callable(prelude.compact):
            compact_result = prelude.compact(max_tokens=400)
            if compact_result:
                project_context = f"\n\nProject context:\n{compact_result}\n"

        user_content = f"""Task: {context.objective}

Repository: {context.repo_path}
Task ID: {context.task_id}

Constraints:
{chr(10).join(f'- {c}' for c in context.constraints) if context.constraints else '- None specified'}

Acceptance Criteria:
{chr(10).join(f'- {c}' for c in context.acceptance_criteria) if context.acceptance_criteria else '- Tests pass, clean diff'}
{file_context}{project_context}

Produce your execution plan as JSON."""

        return [self._system_msg(), self._user_msg(user_content)]

    def parse_response(self, response: RouterResponse, context: AgentContext) -> dict[str, Any]:
        """Parse and rigorously validate the JSON plan from The Queen."""
        content = response.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```") and not line.strip().lower() == "json"]
            content = "\n".join(lines)

        try:
            raw_json = json.loads(content)

            # STRICT VALIDATION: Throws ValidationError if the LLM hallucinated keys/values/actions
            validated_plan = ExecutionPlan(**raw_json)
            plan = validated_plan.model_dump()

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"[PLANNER] Failed to parse/validate plan JSON: {e}")
            logger.debug(f"[PLANNER] Raw response: {content[:500]}")
            plan = {
                "steps": [],
                "files_likely_affected": [],
                "requires_core_change": False,
                "risk_level": "high",
                "risk_notes": f"Validation failed: {e}",
                "test_strategy": [],
                "estimated_complexity": "unknown",
                "parse_error": True,
                "raw_response": content[:1000],
            }

        # Quality warnings — plan parsed but may be incomplete
        if "parse_error" not in plan:
            self._warn_on_quality_gaps(plan)

        plan["_agent"] = "planner"
        plan["_model"] = response.model
        plan["_tokens"] = response.tokens_used
        plan["_cost"] = response.cost

        logger.info(
            f"[PLANNER] Plan ready — "
            f"{len(plan.get('steps', []))} steps, "
            f"risk={plan.get('risk_level', '?')}, "
            f"core_change={plan.get('requires_core_change', False)}"
        )
        if "self_review_notes" in plan:
            logger.info(f"[PLANNER] Self-review: {plan['self_review_notes']}")

        return plan

    @staticmethod
    def _warn_on_quality_gaps(plan: dict) -> None:
        """Log warnings when the planner skips fields that improve implementer accuracy."""
        if not plan.get("do_not_touch"):
            logger.warning("[PLANNER] ⚠ Plan-level do_not_touch is empty. Implementer has no boundary guidance.")

        for step in plan.get("steps", []):
            n = step.get("step_number", "?")
            action = step.get("action", "")

            if action in ("modify", "create"):
                if not step.get("code_hint"):
                    logger.warning(f"[PLANNER] ⚠ Step {n}: missing code_hint. Implementer will have to guess the change shape.")
                if not step.get("do_not_touch"):
                    logger.warning(f"[PLANNER] ⚠ Step {n}: missing do_not_touch. Implementer may drift into adjacent code.")