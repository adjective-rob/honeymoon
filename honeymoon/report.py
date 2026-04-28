"""
HONEYMOON Report Writer — Signed investigation output.

For investigation and monitor missions, the output is a signed
markdown report instead of a git PR. Each report is:
  1. Written to .honeymoon/reports/{run_id}.md
  2. Signed with the Ed25519 keypair
  3. Signature appended to the report footer

Reports are self-contained — anyone with the public key can verify
that the investigation was produced by this Honeymoon instance
and hasn't been tampered with.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console

from honeymoon.signing import HiveSigner

console = Console()


def write_report(
    repo_path: Path,
    run_id: str,
    mission_name: str,
    objective: str,
    findings: dict[str, Any],
    verification: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
) -> Path:
    """Write a signed investigation report.

    Args:
        repo_path: Root of the target repository
        run_id: Unique run identifier
        mission_name: Mission that produced this report
        objective: The investigation objective
        findings: The analyst's structured findings
        verification: The verifier's verdict (optional)
        budget: Token/cost summary (optional)

    Returns:
        Path to the written report file
    """
    reports_dir = repo_path / ".honeymoon" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    short_id = run_id[:12]

    # --- Build the report ---
    sections = []
    finding_list = findings.get("findings", [])

    # Header
    sections.append(f"# 🍯 Investigation Report — {short_id}")
    sections.append("")
    sections.append("| Field | Value |")
    sections.append("|-------|-------|")
    sections.append(f"| **Mission** | {mission_name} |")
    sections.append(f"| **Objective** | {objective} |")
    sections.append(f"| **Timestamp** | {timestamp} |")
    sections.append(f"| **Run ID** | `{run_id}` |")
    sections.append(f"| **Findings** | {len(finding_list)} |")

    # Risk matrix
    severity_counts: dict[str, int] = {}
    for f in finding_list:
        sev = f.get("severity", "info").upper()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
    if severity_counts:
        risk_parts = []
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            if sev in severity_counts:
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "⚪"}.get(sev, "⚪")
                risk_parts.append(f"{icon} {severity_counts[sev]} {sev}")
        sections.append(f"| **Risk Profile** | {' · '.join(risk_parts)} |")

    sections.append("")
    sections.append("---")
    sections.append("")

    # Summary
    summary = findings.get("summary", "No summary provided.")
    sections.append("## Summary")
    sections.append("")
    sections.append(summary)
    sections.append("")

    # Findings
    if finding_list:
        sections.append("## Findings")
        sections.append("")

        for i, finding in enumerate(finding_list, 1):
            severity = finding.get("severity", "info").upper()
            confidence = finding.get("confidence", "medium")
            title = finding.get("title", f"Finding {i}")

            severity_icon = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🔵",
                "INFO": "⚪",
            }.get(severity, "⚪")

            sections.append(f"### {severity_icon} {i}. {title}")
            sections.append("")
            sections.append(f"**Severity:** {severity} | **Confidence:** {confidence}")
            sections.append("")

            evidence = finding.get("evidence", "")
            if evidence:
                sections.append("**Evidence:**")
                sections.append("")
                sections.append(f"```\n{evidence}\n```")
                sections.append("")

            analysis = finding.get("analysis", "")
            if analysis:
                sections.append(f"**Analysis:** {analysis}")
                sections.append("")

    # Recommendations
    recommendations = findings.get("recommendations", [])
    if recommendations:
        sections.append("## Recommendations")
        sections.append("")
        for rec in recommendations:
            sections.append(f"- {rec}")
        sections.append("")

    # Verification
    if verification:
        sections.append("## Verification")
        sections.append("")
        verdict = verification.get("verdict", "unverified")
        # Map security agent verdicts to investigation verdicts
        verdict_map = {"pass": "confirmed", "warn": "partial", "block": "disputed"}
        verdict = verdict_map.get(verdict, verdict)
        verdict_icon = {
            "confirmed": "✅",
            "partial": "⚠️",
            "disputed": "❌",
        }.get(verdict, "❓")
        sections.append(f"**Verdict:** {verdict_icon} {verdict.upper()}")
        sections.append("")
        # Include verifier summary and issues
        if verification.get("summary"):
            sections.append(verification["summary"])
            sections.append("")
        for issue in verification.get("issues", []):
            if issue.get("description") and issue.get("file") != "system":
                sections.append(f"- **{issue.get('severity', 'info').upper()}** [{issue.get('file', '?')}]: {issue['description']}")
        if verification.get("issues"):
            sections.append("")
        if verification.get("notes"):
            sections.append(verification["notes"])
            sections.append("")

    # Budget
    if budget:
        sections.append("## Cost")
        sections.append("")
        sections.append(f"- Tokens: {budget.get('total_tokens', 0):,}")
        sections.append(f"- Cost: ${budget.get('estimated_cost', 0):.4f}")
        sections.append(f"- Calls: {budget.get('call_count', 0)}")
        sections.append("")

    # Assemble report body (before signature)
    report_body = "\n".join(sections)

    # --- Sign the report ---
    signer = HiveSigner.load(repo_path)
    if signer is not None:
        signature = signer.sign(report_body.encode("utf-8"))
        report_body += "\n---\n\n"
        report_body += "## Attestation\n\n"
        report_body += "**Signed:** Ed25519\n"
        report_body += f"**Public Key:** `{signer.public_key_hex}`\n"
        report_body += f"**Signature:** `{signature}`\n"
        report_body += "\nTo verify: check the signature against everything above the `---` separator.\n"
        logger.info("[REPORT] Signed with Ed25519")
    else:
        report_body += "\n---\n\n"
        report_body += "## Attestation\n\n"
        report_body += "**Unsigned** — no Ed25519 keypair found. Run `honeymoon init` to enable signing.\n"

    # --- Write ---
    report_path = reports_dir / f"{short_id}.md"
    report_path.write_text(report_body)

    logger.info(f"[REPORT] Written to {report_path}")
    console.print(f"\n[bold green]📋 Report written: {report_path}[/]")

    # Also write structured JSON for machine consumption
    json_path = reports_dir / f"{short_id}.json"
    json_data = {
        "run_id": run_id,
        "mission": mission_name,
        "objective": objective,
        "timestamp": timestamp,
        "findings": findings,
        "verification": verification,
        "budget": budget,
    }
    if signer:
        json_data["signature"] = signature
        json_data["public_key"] = signer.public_key_hex

    json_path.write_text(json.dumps(json_data, indent=2))

    return report_path
