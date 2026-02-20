"""
🐛 Reroute — The Debugger

Only appears when things break.
Laser-focused. No feature creep.

Energy: quiet gremlin that only appears when things break.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from glitchlab.agents import AgentContext, BaseAgent
from glitchlab.router import RouterResponse


class DebuggerAgent(BaseAgent):
    role = "debugger"

    system_prompt = """You are Reroute, the debug engine inside GLITCHLAB.

You are invoked ONLY when tests fail or builds break.
Your job is to produce a MINIMAL fix. Nothing more.

You MUST respond with valid JSON only.

Output schema:
{
  "diagnosis": "What went wrong and why",
  "root_cause": "The specific root cause",
  "fix": {
    "changes": [
      {
        "file": "path/to/file",
        "action": "modify",
        "patch": "unified diff of the fix",
        "description": "what this fixes"
      }
    ]
  },
  "confidence": "high|medium|low",
  "should_retry": true,
  "notes": "Any additional context"
}

Rules:
- Fix the EXACT failure. Nothing else.
- Do not refactor. Do not improve. Do not add features.
- If you cannot fix it with confidence, set should_retry=false.
- Keep patches as small as humanly possible.
- Analyze the error output carefully before proposing changes.
"""

    def build_messages(self, context: AgentContext) -> list[dict[str, str]]:
        error_output = context.extra.get("error_output", "No error output provided")
        test_command = context.extra.get("test_command", "unknown")
        attempt = context.extra.get("attempt", 1)
        previous_fixes = context.extra.get("previous_fixes", [])

        prev_fixes_text = ""
        if previous_fixes:
            prev_fixes_text = "\n\nPrevious fix attempts that did NOT work:\n"
            for i, fix in enumerate(previous_fixes, 1):
                prev_fixes_text += f"\nAttempt {i}: {fix.get('diagnosis', 'unknown')}\n"

        file_context = ""
        if context.file_context:
            file_context = "\n\nCurrent file contents:\n"
            for fname, content in context.file_context.items():
                file_context += f"\n--- {fname} ---\n{content}\n"

        user_content = f"""Test/build failure detected.

Task: {context.objective}
Task ID: {context.task_id}
Fix attempt: {attempt}

Command that failed: {test_command}

Error output:
```
{error_output}
```
{prev_fixes_text}
{file_context}

Diagnose the failure and produce a minimal fix as JSON."""

        return [self._system_msg(), self._user_msg(user_content)]

    def parse_response(self, response: RouterResponse, context: AgentContext) -> dict[str, Any]:
        """Parse debug output from Reroute."""
        content = response.content.strip()

        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[REROUTE] Failed to parse debug JSON: {e}")
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    result = {
                        "diagnosis": "Failed to parse debugger output",
                        "root_cause": str(e),
                        "fix": {"changes": []},
                        "confidence": "low",
                        "should_retry": False,
                        "parse_error": True,
                    }
            else:
                result = {
                    "diagnosis": "Failed to parse debugger output",
                    "root_cause": str(e),
                    "fix": {"changes": []},
                    "confidence": "low",
                    "should_retry": False,
                    "parse_error": True,
                }

        result["_agent"] = "debugger"
        result["_model"] = response.model
        result["_tokens"] = response.tokens_used
        result["_cost"] = response.cost

        logger.info(
            f"[REROUTE] Diagnosis: {result.get('diagnosis', '?')[:80]} — "
            f"confidence={result.get('confidence', '?')}, "
            f"retry={result.get('should_retry', False)}"
        )

        return result
