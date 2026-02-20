"""
🔧 Patch — The Implementer

Writes code. Adds tests. Makes surgical diffs.
Minimal scope. No feature creep.

Energy: hoodie-wearing prodigy.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from glitchlab.agents import AgentContext, BaseAgent
from glitchlab.router import RouterResponse


class ImplementerAgent(BaseAgent):
    role = "implementer"

    system_prompt = """You are Patch, the implementation engine inside GLITCHLAB.

You receive an execution plan and produce code changes.

You MUST respond with valid JSON only. No markdown wrapping around the JSON itself.

Output schema:
{
  "changes": [
    {
      "file": "path/to/file",
      "action": "modify|create|delete",
      "content": "full file content if create, or null for delete",
      "patch": "unified diff for modify (preferred for existing files)",
      "description": "what this change does"
    }
  ],
  "tests_added": [
    {
      "file": "path/to/test_file",
      "content": "full test file content or additions",
      "description": "what this tests"
    }
  ],
  "commit_message": "feat: concise description of change",
  "summary": "Brief human-readable summary of all changes"
}

Rules:
- Follow the plan exactly. Do not add unrequested features.
- Keep diffs minimal. Surgical precision.
- Always add or update tests.
- Use idiomatic patterns for the language detected.
- If a step is unclear, implement the safest interpretation.
- Never modify files not mentioned in the plan unless absolutely necessary.
- For Rust: use proper error handling, no unwrap() in library code.
- For Python: type hints, docstrings.
- For TypeScript: strict types, no any.
- Commit message must follow conventional commits format.
"""

    def build_messages(self, context: AgentContext) -> list[dict[str, str]]:
        plan = context.previous_output
        steps_text = ""
        if plan.get("steps"):
            for step in plan["steps"]:
                steps_text += (
                    f"\nStep {step.get('step_number', '?')}: "
                    f"{step.get('description', 'no description')}\n"
                    f"  Files: {step.get('files', [])}\n"
                    f"  Action: {step.get('action', '?')}\n"
                )

        file_context = ""
        if context.file_context:
            file_context = "\n\nCurrent file contents:\n"
            for fname, content in context.file_context.items():
                file_context += f"\n--- {fname} ---\n{content}\n"

        # Inject Prelude project context if available
        prelude_section = ""
        prelude_ctx = context.extra.get("prelude_context", "")
        if prelude_ctx:
            prelude_section = f"\n\n{prelude_ctx}\n"

        user_content = f"""Task: {context.objective}
Task ID: {context.task_id}
{prelude_section}
Execution Plan:
{steps_text}

Files likely affected: {plan.get('files_likely_affected', [])}
Test strategy: {plan.get('test_strategy', [])}
{file_context}

Implement the changes as specified. Return JSON with your changes."""

        return [self._system_msg(), self._user_msg(user_content)]

    def parse_response(self, response: RouterResponse, context: AgentContext) -> dict[str, Any]:
        """Parse implementation output from Patch."""
        content = response.content.strip()

        # Strip markdown code fences
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[PATCH] Failed to parse implementation JSON: {e}")

            # Try to extract JSON from response
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    result = self._fallback_result(content, str(e))
            else:
                result = self._fallback_result(content, str(e))

        result["_agent"] = "implementer"
        result["_model"] = response.model
        result["_tokens"] = response.tokens_used
        result["_cost"] = response.cost

        n_changes = len(result.get("changes", []))
        n_tests = len(result.get("tests_added", []))
        logger.info(f"[PATCH] Implementation ready — {n_changes} changes, {n_tests} tests")

        return result

    @staticmethod
    def _fallback_result(raw: str, error: str) -> dict[str, Any]:
        return {
            "changes": [],
            "tests_added": [],
            "commit_message": "fix: implementation (parse error)",
            "summary": f"Failed to parse implementation output: {error}",
            "parse_error": True,
            "raw_response": raw[:2000],
        }
