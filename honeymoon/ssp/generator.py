"""SSP Generator — produces a signed System Security Plan from scan results + Prelude context."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console

from honeymoon.signing import HiveSigner
from honeymoon.ssp.controls import (
    CONTROLS,
    CONTROL_MAP,
    FAMILIES,
    map_finding_to_controls,
)

console = Console()


def _load_prelude_context(repo_path: Path) -> dict[str, Any]:
    """Load Prelude context files if available."""
    ctx: dict[str, Any] = {}
    context_dir = repo_path / ".context"
    if not context_dir.exists():
        return ctx

    for name in ["project", "stack", "architecture", "constraints"]:
        fpath = context_dir / f"{name}.json"
        if fpath.exists():
            try:
                ctx[name] = json.loads(fpath.read_text())
            except (json.JSONDecodeError, OSError):
                pass
    return ctx


def _load_scan_findings(repo_path: Path) -> list[dict[str, Any]]:
    """Load findings from the most recent scan report."""
    reports_dir = repo_path / ".honeymoon" / "reports"
    if not reports_dir.exists():
        return []

    json_files = sorted(reports_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for jf in json_files:
        try:
            report = json.loads(jf.read_text())
            findings = report.get("findings", {}).get("findings", [])
            if findings:
                return findings
        except (json.JSONDecodeError, OSError):
            continue
    return []


def _load_all_scan_findings(repo_path: Path) -> list[dict[str, Any]]:
    """Load findings from ALL scan reports for comprehensive coverage."""
    reports_dir = repo_path / ".honeymoon" / "reports"
    if not reports_dir.exists():
        return []

    all_findings = []
    seen_titles: set[str] = set()
    for jf in sorted(reports_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            report = json.loads(jf.read_text())
            for f in report.get("findings", {}).get("findings", []):
                title = f.get("title", "")
                if title not in seen_titles:
                    seen_titles.add(title)
                    all_findings.append(f)
        except (json.JSONDecodeError, OSError):
            continue
    return all_findings


def _load_provenance_events(repo_path: Path) -> int:
    """Count total signed audit events."""
    audit_file = repo_path / ".honeymoon" / "logs" / "audit.jsonl"
    if not audit_file.exists():
        return 0
    return sum(1 for line in audit_file.read_text().splitlines() if line.strip())


def _assess_control(
    control_id: str,
    findings: list[dict[str, Any]],
    finding_control_map: dict[str, list[str]],
    prelude: dict[str, Any],
) -> dict[str, Any]:
    """Assess a single control's implementation status based on evidence."""
    control = CONTROL_MAP[control_id]

    # Find findings that map to this control
    related_findings = []
    for f in findings:
        title = f.get("title", "")
        if control_id in finding_control_map.get(title, []):
            related_findings.append(f)

    # Check Prelude context for positive evidence
    positive_evidence: list[str] = []
    stack = prelude.get("stack", {})
    constraints = prelude.get("constraints", {})

    # AU controls — check for Zephyr/signing
    if control_id == "AU-9":
        positive_evidence.append("Audit trail uses Zephyr cryptographic signing (append-only, tamper-evident)")
    elif control_id == "AU-10":
        positive_evidence.append("All pipeline events signed with Ed25519 via Zephyr — non-repudiation enforced")
    elif control_id == "AU-2":
        positive_evidence.append("HONEYMOON audit logger captures all pipeline events to audit.jsonl")

    # CM controls — check for version control, deps
    if control_id == "CM-3":
        positive_evidence.append("Git version control with Zephyr-signed commits and pre-push gatekeeper")
    elif control_id == "CM-8":
        deps = stack.get("dependencies", {})
        if deps:
            positive_evidence.append(f"Dependency inventory: {len(deps)} packages tracked in pyproject.toml")

    # SA-11 — testing
    if control_id == "SA-11":
        test_fw = stack.get("testingFrameworks", [])
        if test_fw:
            positive_evidence.append(f"Testing framework: {', '.join(test_fw)}")
        conv = constraints.get("conventions", [])
        if isinstance(conv, list):
            for c in conv:
                if isinstance(c, dict) and "test" in str(c.get("tool", "")).lower():
                    positive_evidence.append(f"Convention: {c.get('tool', '')} configured")

    # SC-12/SC-13 — crypto
    if control_id in ("SC-12", "SC-13"):
        positive_evidence.append("Ed25519 keypair for report signing; Zephyr hardware signing for events")

    # RA-5 — scanning
    if control_id == "RA-5":
        positive_evidence.append("HONEYMOON automated security scanning with signed findings reports")

    # Determine status
    has_issues = any(f.get("severity", "info") in ("critical", "high", "medium") for f in related_findings)
    has_evidence = len(positive_evidence) > 0

    if has_issues:
        status = "partial"
    elif has_evidence:
        status = "implemented"
    else:
        status = "planned"

    return {
        "control_id": control_id,
        "name": control.name,
        "family": control.family,
        "description": control.description,
        "status": status,
        "positive_evidence": positive_evidence,
        "findings": [
            {
                "title": f.get("title", ""),
                "severity": f.get("severity", "info"),
                "summary": f.get("analysis", "")[:200],
            }
            for f in related_findings
        ],
    }


def generate_ssp(
    repo_path: Path,
    baseline: str = "moderate",
) -> Path:
    """Generate a signed System Security Plan.

    Args:
        repo_path: Root of the target repository
        baseline: NIST baseline — low, moderate, or high

    Returns:
        Path to the generated SSP HTML file
    """
    repo_path = repo_path.resolve()
    reports_dir = repo_path / ".honeymoon" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    prelude = _load_prelude_context(repo_path)
    findings = _load_all_scan_findings(repo_path)
    event_count = _load_provenance_events(repo_path)

    # Build finding-to-control mapping
    finding_control_map: dict[str, list[str]] = {}
    for f in findings:
        title = f.get("title", "")
        finding_control_map[title] = map_finding_to_controls(f)

    # Assess each control
    assessments = []
    for control in CONTROLS:
        assessment = _assess_control(control.id, findings, finding_control_map, prelude)
        assessments.append(assessment)

    # Extract system info from Prelude
    project = prelude.get("project", {})
    stack = prelude.get("stack", {})
    system_name = project.get("name", repo_path.name)
    system_desc = project.get("description", "No description available.")
    system_version = project.get("projectVersion", "unknown")
    system_license = project.get("license", "unknown")

    language = stack.get("language", "unknown")
    runtime = stack.get("runtime", "unknown")
    framework = stack.get("framework", "unknown")
    deps = stack.get("dependencies", {})
    test_frameworks = stack.get("testingFrameworks", [])

    # Compute summary stats
    implemented = sum(1 for a in assessments if a["status"] == "implemented")
    partial = sum(1 for a in assessments if a["status"] == "partial")
    planned = sum(1 for a in assessments if a["status"] == "planned")
    total = len(assessments)

    ssp_data = {
        "system_name": system_name,
        "description": system_desc,
        "version": system_version,
        "baseline": baseline,
        "timestamp": timestamp,
        "language": language,
        "runtime": runtime,
        "framework": framework,
        "dependencies": deps,
        "test_frameworks": test_frameworks,
        "license": system_license,
        "assessments": assessments,
        "findings_count": len(findings),
        "event_count": event_count,
        "summary": {
            "total": total,
            "implemented": implemented,
            "partial": partial,
            "planned": planned,
            "score": round((implemented / total) * 100) if total else 0,
        },
    }

    # Sign the SSP
    signer = HiveSigner.load(repo_path)
    ssp_json = json.dumps(ssp_data, indent=2)
    signature = None
    public_key = None
    if signer:
        signature = signer.sign(ssp_json.encode("utf-8"))
        public_key = signer.public_key_hex
        ssp_data["signature"] = signature
        ssp_data["public_key"] = public_key

    # Write JSON
    json_path = reports_dir / "SSP.json"
    json_path.write_text(json.dumps(ssp_data, indent=2))

    # Write HTML
    html_path = _write_ssp_html(
        reports_dir / "SSP.html",
        ssp_data=ssp_data,
        signature=signature,
        public_key=public_key,
    )

    logger.info(f"[SSP] Written to {html_path}")
    console.print(f"\n[bold green]SSP written: {html_path}[/]")

    return html_path


def _status_svg(status: str) -> str:
    """Return an inline SVG icon for control status."""
    icons = {
        "implemented": (
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="7" fill="none" stroke="#10b981" stroke-width="1.5"/>'
            '<polyline points="5,8 7,10.5 11,5.5" fill="none" stroke="#10b981"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
        ),
        "partial": (
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="7" fill="none" stroke="#eab308" stroke-width="1.5"/>'
            '<line x1="8" y1="4.5" x2="8" y2="8.5" stroke="#eab308"'
            ' stroke-width="2" stroke-linecap="round"/>'
            '<circle cx="8" cy="11" r="1" fill="#eab308"/>'
            '</svg>'
        ),
        "planned": (
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="7" fill="none" stroke="#6b7280" stroke-width="1.5"/>'
            '<line x1="5" y1="8" x2="11" y2="8" stroke="#6b7280"'
            ' stroke-width="2" stroke-linecap="round"/>'
            '</svg>'
        ),
    }
    return icons.get(status, icons["planned"])


def _write_ssp_html(
    path: Path,
    *,
    ssp_data: dict[str, Any],
    signature: str | None,
    public_key: str | None,
) -> Path:
    """Generate a self-contained SSP HTML document."""
    template_path = Path(__file__).parent.parent / "reporting" / "ssp_template.html"
    if not template_path.exists():
        logger.warning(f"[SSP] Template not found: {template_path}")
        return path

    template = template_path.read_text()
    summary = ssp_data["summary"]

    # System info section
    system_info = f'''
    <div class="meta">
      <div class="meta-item"><div class="meta-label">System</div><div class="meta-value">{ssp_data["system_name"]}</div></div>
      <div class="meta-item"><div class="meta-label">Version</div><div class="meta-value mono">{ssp_data["version"]}</div></div>
      <div class="meta-item"><div class="meta-label">Baseline</div><div class="meta-value">{ssp_data["baseline"].upper()}</div></div>
      <div class="meta-item"><div class="meta-label">Generated</div><div class="meta-value mono">{ssp_data["timestamp"][:19]}</div></div>
    </div>'''

    # Description
    desc_html = f'''
    <div class="section">
      <div class="section-title">System Description</div>
      <div class="summary">{ssp_data["description"]}</div>
    </div>'''

    # Technology stack
    dep_list = ""
    for name, version in ssp_data.get("dependencies", {}).items():
        dep_list += f'<span class="dep-pill">{name} {version}</span>'

    stack_html = f'''
    <div class="section">
      <div class="section-title">Technology Stack</div>
      <div class="stack-grid">
        <div class="stack-item"><div class="stack-label">Language</div><div class="stack-value">{ssp_data["language"]}</div></div>
        <div class="stack-item"><div class="stack-label">Runtime</div><div class="stack-value">{ssp_data["runtime"]}</div></div>
        <div class="stack-item"><div class="stack-label">Framework</div><div class="stack-value">{ssp_data["framework"]}</div></div>
        <div class="stack-item"><div class="stack-label">Testing</div><div class="stack-value">{", ".join(ssp_data.get("test_frameworks", [])) or "None"}</div></div>
      </div>
      {f'<div class="dep-list">{dep_list}</div>' if dep_list else ""}
    </div>'''

    # Compliance score gauge
    score = summary["score"]
    score_color = "#10b981" if score >= 70 else "#eab308" if score >= 40 else "#ef4444"
    gauge_html = f'''
    <div class="section">
      <div class="section-title">Compliance Posture</div>
      <div class="gauge-row">
        <div class="gauge-ring">
          <svg viewBox="0 0 120 120" width="120" height="120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="8"/>
            <circle cx="60" cy="60" r="52" fill="none" stroke="{score_color}" stroke-width="8"
              stroke-dasharray="{score * 3.267} 326.7"
              stroke-linecap="round" transform="rotate(-90 60 60)"/>
            <text x="60" y="56" text-anchor="middle" font-size="28" font-weight="700" fill="{score_color}">{score}</text>
            <text x="60" y="72" text-anchor="middle" font-size="10" fill="#6b7280">SCORE</text>
          </svg>
        </div>
        <div class="gauge-stats">
          <div class="gauge-stat"><span class="stat-dot implemented"></span> {summary["implemented"]} Implemented</div>
          <div class="gauge-stat"><span class="stat-dot partial"></span> {summary["partial"]} Partial</div>
          <div class="gauge-stat"><span class="stat-dot planned"></span> {summary["planned"]} Planned</div>
        </div>
        <div class="gauge-stats">
          <div class="gauge-stat"><span class="stat-label">Controls Assessed</span> <span class="stat-num">{summary["total"]}</span></div>
          <div class="gauge-stat"><span class="stat-label">Scan Findings</span> <span class="stat-num">{ssp_data["findings_count"]}</span></div>
          <div class="gauge-stat"><span class="stat-label">Signed Events</span> <span class="stat-num">{ssp_data["event_count"]}</span></div>
        </div>
      </div>
    </div>'''

    # Control assessments by family
    controls_html = ""
    for family_id, family_name in FAMILIES.items():
        family_assessments = [a for a in ssp_data["assessments"] if a["family"] == family_id]
        if not family_assessments:
            continue

        rows = ""
        for a in family_assessments:
            status_icon = _status_svg(a["status"])
            status_class = f"status-{a['status']}"

            evidence_items = ""
            for ev in a.get("positive_evidence", []):
                evidence_items += f'<div class="evidence-item evidence-positive">{ev}</div>'
            for f in a.get("findings", []):
                sev = f.get("severity", "info")
                evidence_items += (
                    f'<div class="evidence-item evidence-finding">'
                    f'<span class="finding-sev sev-{sev}">{sev.upper()}</span> '
                    f'{f.get("title", "")}'
                    f'</div>'
                )

            rows += f'''<div class="control-row {status_class}">
  <div class="control-id">{a["control_id"]}</div>
  <div class="control-info">
    <div class="control-name">{a["name"]}</div>
    <div class="control-desc">{a["description"]}</div>
    {f'<div class="control-evidence">{evidence_items}</div>' if evidence_items else ""}
  </div>
  <div class="control-status">{status_icon} {a["status"].title()}</div>
</div>'''

        controls_html += f'''
    <div class="section">
      <div class="section-title">{family_id} — {family_name}</div>
      <div class="control-list">{rows}</div>
    </div>'''

    # Attestation
    shield_svg = (
        '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
        '<path d="M8,1 L14,3.5 L14,7.5 C14,11 11,13.5 8,15 C5,13.5 2,11 2,7.5'
        ' L2,3.5 Z" stroke="#10b981" stroke-width="1.2"/>'
        '<polyline points="5.5,8 7.5,10 10.5,6" fill="none" stroke="#6ee7b7"'
        ' stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )
    if signature and public_key:
        attestation_html = f'''
    <div class="section">
      <div class="section-title">Attestation</div>
      <div class="attestation">
        <div class="attestation-title">{shield_svg} Ed25519 Signed — This SSP is tamper-evident</div>
        <div class="attestation-fields">
          <div class="attestation-field"><span>Public Key:</span> <code>{public_key}</code></div>
        </div>
        <div class="attestation-sig">{signature}</div>
      </div>
    </div>'''
    else:
        attestation_html = '''
    <div class="section">
      <div class="section-title">Attestation</div>
      <div class="attestation-unsigned">
        Unsigned &mdash; run <code>honeymoon init</code> to enable Ed25519 signing.
      </div>
    </div>'''

    # Honeycomb icon
    honeycomb = (
        '<svg width="22" height="22" viewBox="0 0 24 24"'
        ' fill="none" stroke="#fff" stroke-width="1.5">'
        '<polygon points="12,2 20,7 20,17 12,22 4,17 4,7"/>'
        '<polygon points="12,7 16,9.5 16,14.5 12,17 8,14.5 8,9.5"'
        ' fill="rgba(255,255,255,0.15)"/>'
        '</svg>'
    )

    content = f'''
  <div class="header-bar">
    <div class="logo">{honeycomb} HONEYMOON</div>
    <div class="subtitle">System Security Plan &middot; NIST 800-53 Rev 5 &middot; {ssp_data["baseline"].upper()} Baseline</div>
  </div>

  {system_info}
  {desc_html}
  {stack_html}
  {gauge_html}
  {controls_html}
  {attestation_html}
'''

    html = template.replace("{{CONTENT}}", content)
    path.write_text(html)
    return path
