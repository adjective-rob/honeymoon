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


def _load_provenance(repo_path: Path, run_id: str) -> list[dict[str, Any]]:
    """Load signed audit events for a specific run from audit.jsonl."""
    audit_file = repo_path / ".honeymoon" / "logs" / "audit.jsonl"
    if not audit_file.exists():
        return []

    events = []
    for line in audit_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            # Zephyr-signed entries have payload as a JSON string
            payload = entry.get("payload", "")
            if isinstance(payload, str):
                payload_data = json.loads(payload)
            else:
                payload_data = payload
            if payload_data.get("run_id") == run_id:
                events.append({
                    "event_type": payload_data.get("event_type", "unknown"),
                    "agent_id": payload_data.get("agent_id", "system"),
                    "timestamp": payload_data.get("timestamp", entry.get("timestamp", "")),
                    "signature": entry.get("signature", ""),
                    "signer": entry.get("signer", ""),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return events


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

    # --- Load provenance chain ---
    provenance = _load_provenance(repo_path, run_id)

    # --- HTML Report ---
    html_path = _write_html_report(
        reports_dir / f"{short_id}.html",
        run_id=run_id,
        mission_name=mission_name,
        objective=objective,
        timestamp=timestamp,
        findings=findings,
        verification=verification,
        budget=budget,
        signature=signature if signer else None,
        public_key=signer.public_key_hex if signer else None,
        provenance=provenance,
    )
    if html_path:
        logger.info(f"[REPORT] HTML report: {html_path}")

    return report_path


def _severity_svg(severity: str) -> str:
    """Return an inline SVG icon for a severity level."""
    icons = {
        "critical": (
            '<span class="icon"><svg width="14" height="14" viewBox="0 0 14 14">'
            '<circle cx="7" cy="7" r="6" fill="#ef4444"/>'
            '<text x="7" y="7" text-anchor="middle" dominant-baseline="central"'
            ' font-size="9" font-weight="700" fill="#fff">!</text>'
            '</svg></span>'
        ),
        "high": (
            '<span class="icon"><svg width="14" height="14" viewBox="0 0 14 14">'
            '<polygon points="7,1 13,13 1,13" fill="#f97316"/>'
            '</svg></span>'
        ),
        "medium": (
            '<span class="icon"><svg width="14" height="14" viewBox="0 0 14 14">'
            '<polygon points="7,1 13,7 7,13 1,7" fill="#eab308"/>'
            '</svg></span>'
        ),
        "low": (
            '<span class="icon"><svg width="14" height="14" viewBox="0 0 14 14">'
            '<circle cx="7" cy="7" r="6" fill="none" stroke="#3b82f6" stroke-width="1.5"/>'
            '<text x="7" y="7" text-anchor="middle" dominant-baseline="central"'
            ' font-size="8" font-weight="700" fill="#3b82f6">i</text>'
            '</svg></span>'
        ),
        "info": (
            '<span class="icon"><svg width="14" height="14" viewBox="0 0 14 14">'
            '<circle cx="7" cy="7" r="5" fill="none" stroke="#6b7280" stroke-width="1.5"/>'
            '</svg></span>'
        ),
    }
    return icons.get(severity.lower(), icons["info"])


def _verdict_svg(verdict: str) -> str:
    """Return an inline SVG icon for a verification verdict."""
    icons = {
        "confirmed": (
            '<svg width="20" height="20" viewBox="0 0 20 20">'
            '<circle cx="10" cy="10" r="9" fill="none" stroke="#10b981" stroke-width="1.5"/>'
            '<polyline points="6,10 9,13 14,7" fill="none" stroke="#10b981"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
        ),
        "partial": (
            '<svg width="20" height="20" viewBox="0 0 20 20">'
            '<polygon points="10,2 19,18 1,18" fill="none" stroke="#eab308" stroke-width="1.5"/>'
            '<text x="10" y="14" text-anchor="middle" font-size="11"'
            ' font-weight="700" fill="#eab308">!</text>'
            '</svg>'
        ),
        "disputed": (
            '<svg width="20" height="20" viewBox="0 0 20 20">'
            '<circle cx="10" cy="10" r="9" fill="none" stroke="#ef4444" stroke-width="1.5"/>'
            '<line x1="6" y1="6" x2="14" y2="14" stroke="#ef4444"'
            ' stroke-width="2" stroke-linecap="round"/>'
            '<line x1="14" y1="6" x2="6" y2="14" stroke="#ef4444"'
            ' stroke-width="2" stroke-linecap="round"/>'
            '</svg>'
        ),
    }
    return icons.get(verdict, icons.get("partial", ""))


def _shield_svg() -> str:
    """Return an inline SVG shield icon for the attestation section."""
    return (
        '<span class="icon"><svg width="16" height="16" viewBox="0 0 16 16">'
        '<path d="M8,1 L14,3.5 L14,7.5 C14,11 11,13.5 8,15 C5,13.5 2,11 2,7.5'
        ' L2,3.5 Z" fill="none" stroke="#10b981" stroke-width="1.2"/>'
        '<polyline points="5.5,8 7.5,10 10.5,6" fill="none" stroke="#6ee7b7"'
        ' stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg></span>'
    )


def _honeycomb_svg() -> str:
    """Return an inline SVG honeycomb icon for the header."""
    return (
        '<span class="icon"><svg width="22" height="22" viewBox="0 0 24 24"'
        ' fill="none" stroke="#fff" stroke-width="1.5">'
        '<polygon points="12,2 20,7 20,17 12,22 4,17 4,7"/>'
        '<polygon points="12,7 16,9.5 16,14.5 12,17 8,14.5 8,9.5"'
        ' fill="rgba(255,255,255,0.15)"/>'
        '</svg></span>'
    )


def _provenance_dot_svg() -> str:
    """Return an inline SVG checkmark for provenance chain nodes."""
    return (
        '<svg viewBox="0 0 14 14" fill="none" stroke="#6ee7b7" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="3,7 6,10 11,4"/>'
        '</svg>'
    )


def _build_provenance_html(provenance: list[dict[str, Any]]) -> str:
    """Build the provenance chain HTML section."""
    if not provenance:
        return ""

    # Friendly labels for event types
    labels = {
        "run.started": "Pipeline Started",
        "run.completed": "Pipeline Completed",
        "workspace_created": "Workspace Created",
        "repo_indexed": "Repository Indexed",
        "prelude_constraints_loaded": "Constraints Loaded",
        "pipeline.step_started": "Agent Step Started",
        "pipeline.step_completed": "Agent Step Completed",
        "tool.executed": "Tool Executed",
        "findings.submitted": "Findings Submitted",
        "verification.completed": "Verification Completed",
    }

    dot = _provenance_dot_svg()
    events_html = ""
    for ev in provenance:
        event_type = ev.get("event_type", "unknown")
        label = labels.get(event_type, event_type.replace(".", " ").replace("_", " ").title())
        agent = ev.get("agent_id", "system")
        sig = ev.get("signature", "")
        ts = ev.get("timestamp", "")
        # Show time portion only
        time_display = ts[11:19] if len(ts) >= 19 else ts

        sig_display = f"{sig[:24]}...{sig[-8:]}" if len(sig) > 36 else sig

        events_html += f'''<div class="provenance-event">
  <div class="provenance-dot">{dot}</div>
  <div class="provenance-info">
    <div class="provenance-type">{label}</div>
    <div class="provenance-agent">{agent}</div>
    <div class="provenance-sig">{sig_display}</div>
  </div>
  <div class="provenance-time">{time_display}</div>
</div>'''

    signer = provenance[0].get("signer", "") if provenance else ""
    signer_display = f"{signer[:16]}..." if len(signer) > 20 else signer
    summary = (
        f'<div class="provenance-summary">'
        f'<strong>{len(provenance)}</strong> events signed by '
        f'<span class="mono">{signer_display}</span> via Zephyr'
        f'</div>'
    )

    return f'''<div class="section">
  <div class="section-title">Provenance Chain</div>
  <div class="provenance-chain">{events_html}</div>
  {summary}
</div>'''


def _write_html_report(
    path: Path,
    *,
    run_id: str,
    mission_name: str,
    objective: str,
    timestamp: str,
    findings: dict[str, Any],
    verification: dict[str, Any] | None,
    budget: dict[str, Any] | None,
    signature: str | None,
    public_key: str | None,
    provenance: list[dict[str, Any]] | None = None,
) -> Path | None:
    """Generate a self-contained HTML report."""
    template_path = Path(__file__).parent / "reporting" / "report_template.html"
    if not template_path.exists():
        return None

    template = template_path.read_text()
    finding_list = findings.get("findings", [])
    short_id = run_id[:12]

    # Build severity counts
    sev_counts: dict[str, int] = {}
    for f in finding_list:
        s = f.get("severity", "info").lower()
        sev_counts[s] = sev_counts.get(s, 0) + 1

    risk_pills = ""
    for sev in ["critical", "high", "medium", "low", "info"]:
        if sev in sev_counts:
            icon = _severity_svg(sev)
            risk_pills += (
                f'<span class="risk-pill risk-{sev}">'
                f'{icon} {sev_counts[sev]} {sev.upper()}'
                f'</span>'
            )

    # Build findings HTML
    findings_html = ""
    for i, f in enumerate(finding_list, 1):
        sev = f.get("severity", "info").lower()
        conf = f.get("confidence", "medium")
        sev_class = f"risk-{sev}"
        sev_icon = _severity_svg(sev)

        evidence_html = ""
        if f.get("evidence"):
            ev = f["evidence"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            evidence_html = f'<div class="evidence">{ev}</div>'

        analysis_html = ""
        if f.get("analysis"):
            analysis_html = (
                f'<div class="analysis-label">Analysis</div>\n'
                f'<div class="analysis">{f["analysis"]}</div>'
            )

        findings_html += f'''<div class="finding sev-{sev}">
  <div class="finding-header">
    <span class="finding-number">{i}</span>
    <span class="finding-title">{f.get("title", f"Finding {i}")}</span>
    <div class="finding-badges">
      <span class="badge badge-severity {sev_class}">{sev_icon} {sev.upper()}</span>
      <span class="badge badge-confidence">{conf}</span>
    </div>
  </div>
  <div class="finding-body">
    {evidence_html}
    {analysis_html}
  </div>
</div>'''

    # Build recommendations HTML
    recs_html = ""
    for rec in findings.get("recommendations", []):
        recs_html += f"<li>{rec}</li>"

    # Build verification HTML
    verification_html = ""
    if verification:
        verdict = verification.get("verdict", "unverified")
        verdict_map = {"pass": "confirmed", "warn": "partial", "block": "disputed"}
        verdict = verdict_map.get(verdict, verdict)
        v_class = f"verdict-{verdict}" if verdict in ("confirmed", "partial", "disputed") else ""
        v_icon = _verdict_svg(verdict)

        v_summary = verification.get("summary", "")
        v_issues = ""
        for issue in verification.get("issues", []):
            if issue.get("description") and issue.get("file") != "system":
                v_issues += (
                    f'<div class="verifier-issue">'
                    f'<strong>{issue.get("severity", "info").upper()}</strong>'
                    f' [{issue.get("file", "?")}] {issue["description"]}'
                    f'</div>'
                )

        verification_html = f'''<div class="verdict-box {v_class}">
  <span class="verdict-icon">{v_icon}</span>
  <div class="verdict-text">
    <span class="verdict-label">{verdict.upper()}</span>
    {f"<div>{v_summary}</div>" if v_summary else ""}
  </div>
</div>
{f'<div class="verifier-issues">{v_issues}</div>' if v_issues else ""}'''

    # Build cost HTML
    cost_html = ""
    if budget:
        cost_html = f'''<div class="cost-row">
  <div class="cost-item"><div class="cost-label">Tokens</div><div class="cost-value mono">{budget.get("total_tokens", 0):,}</div></div>
  <div class="cost-item"><div class="cost-label">Cost</div><div class="cost-value mono">${budget.get("estimated_cost", 0):.4f}</div></div>
  <div class="cost-item"><div class="cost-label">API Calls</div><div class="cost-value mono">{budget.get("call_count", 0)}</div></div>
</div>'''

    # Build attestation HTML
    shield = _shield_svg()
    if signature and public_key:
        attestation_html = f'''<div class="attestation">
  <div class="attestation-title">{shield} Ed25519 Signed</div>
  <div class="attestation-fields">
    <div class="attestation-field"><span>Public Key:</span> <code>{public_key}</code></div>
  </div>
  <div class="attestation-sig">{signature}</div>
</div>'''
    else:
        attestation_html = (
            '<div class="attestation-unsigned">'
            'Unsigned &mdash; run <code>honeymoon init</code> to enable Ed25519 signing.'
            '</div>'
        )

    honeycomb_icon = _honeycomb_svg()

    # Assemble
    content = f'''
  <div class="header-bar">
    <div class="logo">{honeycomb_icon} HONEYMOON</div>
    <div class="subtitle">Investigation Report &middot; {short_id}</div>
  </div>

  <div class="meta">
    <div class="meta-item"><div class="meta-label">Mission</div><div class="meta-value">{mission_name}</div></div>
    <div class="meta-item"><div class="meta-label">Findings</div><div class="meta-value">{len(finding_list)}</div></div>
    <div class="meta-item"><div class="meta-label">Timestamp</div><div class="meta-value mono">{timestamp[:19]}</div></div>
    <div class="meta-item"><div class="meta-label">Run ID</div><div class="meta-value mono">{short_id}</div></div>
  </div>

  {f'<div class="section"><div class="section-title">Risk Profile</div><div class="risk-profile">{risk_pills}</div></div>' if risk_pills else ""}

  <div class="section">
    <div class="section-title">Objective</div>
    <div class="summary">{objective}</div>
  </div>

  <div class="section">
    <div class="section-title">Summary</div>
    <div class="summary">{findings.get("summary", "No summary provided.")}</div>
  </div>

  {f'<div class="section"><div class="section-title">Findings</div>{findings_html}</div>' if findings_html else ""}

  {f'<div class="section"><div class="section-title">Recommendations</div><ul class="rec-list">{recs_html}</ul></div>' if recs_html else ""}

  {f'<div class="section"><div class="section-title">Verification</div>{verification_html}</div>' if verification_html else ""}

  {f'<div class="section"><div class="section-title">Cost</div>{cost_html}</div>' if cost_html else ""}

  {_build_provenance_html(provenance or [])}

  <div class="section">
    <div class="section-title">Attestation</div>
    {attestation_html}
  </div>
'''

    html = template.replace("{{CONTENT}}", content)
    path.write_text(html)
    return path


def write_spec(
    repo_path: Path,
    run_id: str,
    investigation_findings: list[dict[str, Any]],
    audit_findings: list[Any],
    verification: dict[str, Any] | None = None,
) -> Path:
    """Write a signed SPEC.md — remediation plan from investigation + audit findings.

    This is the deliverable: a document the user can hand to their own agent,
    their team, or use as the basis for honeymoon batch --fix.
    """
    from honeymoon.signing import HiveSigner

    reports_dir = repo_path / ".honeymoon" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    short_id = run_id[:12]
    timestamp = datetime.now(timezone.utc).isoformat()

    sections = []
    sections.append("# SPEC.md — Remediation Plan")
    sections.append("")
    sections.append("**Generated by:** HONEYMOON deep scan")
    sections.append(f"**Repository:** {repo_path.name}")
    sections.append(f"**Timestamp:** {timestamp}")
    sections.append(f"**Run ID:** `{run_id}`")
    sections.append("")

    # Risk summary
    sev_counts: dict[str, int] = {}
    for f in investigation_findings:
        s = f.get("severity", "info").upper()
        sev_counts[s] = sev_counts.get(s, 0) + 1

    if sev_counts:
        risk_parts = []
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            if sev in sev_counts:
                risk_parts.append(f"{sev_counts[sev]} {sev}")
        sections.append(f"**Risk Profile:** {' · '.join(risk_parts)}")
        sections.append(f"**Static Findings:** {len(audit_findings)}")
        sections.append("")

    sections.append("---")
    sections.append("")

    # Remediation tasks — prioritized by severity
    sections.append("## Remediation Tasks")
    sections.append("")
    sections.append("Each task below is scoped to a single finding. They can be executed independently.")
    sections.append("")

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_findings = sorted(
        investigation_findings,
        key=lambda f: priority_order.get(f.get("severity", "info"), 4)
    )

    for i, finding in enumerate(sorted_findings, 1):
        sev = finding.get("severity", "info").upper()
        title = finding.get("title", f"Finding {i}")
        evidence = finding.get("evidence", "")
        analysis = finding.get("analysis", "")
        icon = {"CRITICAL": "P0", "HIGH": "P1", "MEDIUM": "P2", "LOW": "P3", "INFO": "P4"}.get(sev, "P4")

        sections.append(f"### [{icon}] {title}")
        sections.append("")
        sections.append(f"**Severity:** {sev} | **Confidence:** {finding.get('confidence', 'medium')}")
        sections.append("")

        if analysis:
            sections.append(f"**Problem:** {analysis}")
            sections.append("")

        if evidence:
            sections.append("**Evidence:**")
            sections.append("```")
            sections.append(evidence)
            sections.append("```")
            sections.append("")

        # Generate actionable fix instructions
        sections.append("**Remediation:**")
        if sev in ("CRITICAL", "HIGH"):
            sections.append(f"- [ ] Address immediately — this is a {sev.lower()}-severity finding")
        else:
            sections.append(f"- [ ] Schedule for next sprint — {sev.lower()} severity")
        sections.append("- [ ] Verify fix does not break existing functionality")
        sections.append("- [ ] Add regression test covering this case")
        sections.append("")

    # Static audit summary
    if audit_findings:
        sections.append("## Static Analysis Summary")
        sections.append("")
        sections.append(f"{len(audit_findings)} findings from automated scanning:")
        sections.append("")

        by_kind: dict[str, int] = {}
        for f in audit_findings:
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1

        for kind, count in sorted(by_kind.items(), key=lambda x: -x[1]):
            sections.append(f"- **{kind}**: {count}")
        sections.append("")

    # Verification status
    if verification:
        verdict = verification.get("verdict", "unverified")
        verdict_map = {"pass": "confirmed", "warn": "partial", "block": "disputed"}
        verdict = verdict_map.get(verdict, verdict)
        sections.append("## Verification")
        sections.append("")
        sections.append(f"**Verdict:** {verdict.upper()}")
        if verification.get("summary"):
            sections.append(f"\n{verification['summary']}")
        sections.append("")

    # Usage instructions
    sections.append("## Next Steps")
    sections.append("")
    sections.append("**Option A — Manual remediation:**")
    sections.append("Hand this SPEC.md to your development team or AI coding assistant.")
    sections.append("Each task is self-contained with evidence and remediation steps.")
    sections.append("")
    sections.append("**Option B — Automated remediation:**")
    sections.append("```bash")
    sections.append(f"honeymoon deep --repo {repo_path} --fix")
    sections.append("```")
    sections.append("This generates task YAMLs and queues them for `honeymoon batch`.")
    sections.append("")

    spec_body = "\n".join(sections)

    # Sign
    signer = HiveSigner.load(repo_path)
    if signer:
        signature = signer.sign(spec_body.encode("utf-8"))
        spec_body += "\n---\n\n"
        spec_body += "## Attestation\n\n"
        spec_body += "**Signed:** Ed25519\n"
        spec_body += f"**Public Key:** `{signer.public_key_hex}`\n"
        spec_body += f"**Signature:** `{signature}`\n"
    else:
        spec_body += "\n---\n\n**Unsigned** — run `honeymoon init` to enable signing.\n"

    spec_path = reports_dir / f"SPEC-{short_id}.md"
    spec_path.write_text(spec_body)
    logger.info(f"[REPORT] SPEC written to {spec_path}")

    return spec_path
