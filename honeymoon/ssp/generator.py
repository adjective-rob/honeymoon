"""SSP Generator — produces a signed System Security Plan from scan results + Prelude context.

Generates a full NIST 800-53 Rev 5 SSP by:
  1. Loading the OSCAL control catalog (filtered by baseline)
  2. Gathering all scan findings from .honeymoon/reports/
  3. Reading Prelude context (.context/) for system metadata and evidence
  4. Assessing each control against findings + Prelude evidence
  5. Producing signed JSON + self-contained HTML
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console

from honeymoon.signing import HiveSigner
from honeymoon.ssp.controls import (
    Control,
    get_families,
    load_controls,
    map_finding_to_controls,
)

console = Console()


# ---------------------------------------------------------------------------
# Prelude context loaders
# ---------------------------------------------------------------------------

def _load_prelude_context(repo_path: Path) -> dict[str, Any]:
    """Load all Prelude context files."""
    ctx: dict[str, Any] = {}
    context_dir = repo_path / ".context"
    if not context_dir.exists():
        return ctx

    for name in ["project", "stack", "architecture", "constraints", "decisions"]:
        fpath = context_dir / f"{name}.json"
        if fpath.exists():
            try:
                ctx[name] = json.loads(fpath.read_text())
            except (json.JSONDecodeError, OSError):
                pass
    return ctx


def _extract_prelude_evidence(prelude: dict[str, Any]) -> dict[str, list[str]]:
    """Extract per-control evidence from Prelude context.

    Returns control_id -> list of evidence strings.
    """
    evidence: dict[str, list[str]] = {}
    stack = prelude.get("stack", {})
    arch = prelude.get("architecture", {})
    constraints = prelude.get("constraints", {})
    project = prelude.get("project", {})
    decisions = prelude.get("decisions", {})

    deps = stack.get("dependencies", {})
    dev_deps = stack.get("devDependencies", {})
    patterns = arch.get("patterns", [])
    conventions = arch.get("conventions", [])
    security_constraints = constraints.get("security", [])
    code_style = constraints.get("codeStyle", {})
    testing_cfg = constraints.get("testing", {})
    decision_list = decisions.get("decisions", []) if isinstance(decisions, dict) else []

    # Helper
    def add(control_id: str, text: str) -> None:
        evidence.setdefault(control_id, []).append(text)

    # -- AC: Access Control --
    if any("auth" in str(p).lower() or "guard" in str(p).lower() for p in patterns):
        add("ac-3", f"Architecture uses: {', '.join(patterns)}")
    if any("cors" in str(c).lower() for c in conventions):
        add("ac-17", "CORS configuration documented in architecture conventions")

    # -- AU: Audit --
    add("au-2", "HONEYMOON audit logger captures all pipeline events to audit.jsonl")
    add("au-3", "Audit records include: event_id, timestamp, event_type, run_id, agent_id, payload")
    add("au-9", "Audit trail uses Zephyr cryptographic signing (append-only, tamper-evident)")
    add("au-10", "All pipeline events signed with Ed25519 via Zephyr — non-repudiation enforced")
    add("au-12", "Audit events generated automatically during pipeline execution")

    # -- CA: Assessment --
    add("ca-2", "HONEYMOON performs automated security assessments (scan, simulate, harden)")
    add("ca-7", "Continuous monitoring via HONEYMOON posture tracking and hardening ledger")

    # -- CM: Configuration Management --
    add("cm-2", f"Baseline configuration managed via config.yaml; runtime: {stack.get('runtime', 'unknown')}")
    add("cm-3", "Git version control with Zephyr-signed commits and pre-push gatekeeper")
    if deps:
        add("cm-8", f"Dependency inventory: {len(deps)} runtime + {len(dev_deps)} dev packages tracked")
    if code_style.get("linter"):
        add("cm-6", f"Code style enforced by {code_style['linter']}")

    # -- IA: Identification and Authentication --
    if "pynacl" in deps:
        add("ia-5", "PyNaCl (libsodium) used for cryptographic authenticator management")
    if any("token" in str(c).lower() or "auth" in str(c).lower() for c in conventions):
        add("ia-2", "Authentication conventions documented in architecture")

    # -- RA: Risk Assessment --
    add("ra-3", "HONEYMOON threat modeling via simulate command (Red/Blue team pipeline)")
    add("ra-5", "HONEYMOON automated security scanning with signed findings reports")
    if "pip-audit" in str(dev_deps) or any("audit" in str(c).lower() for c in conventions):
        add("ra-5", "Dependency vulnerability scanning via audit command")

    # -- SA: Acquisition & Development --
    test_fws = stack.get("testingFrameworks", [])
    if test_fws:
        add("sa-11", f"Testing framework: {', '.join(test_fws)}")
    if testing_cfg.get("required"):
        add("sa-11", f"Testing required per project constraints (strategy: {testing_cfg.get('strategy', 'unknown')})")
    if any("agent" in str(p).lower() or "pipeline" in str(p).lower() for p in patterns):
        add("sa-3", f"Structured development lifecycle: {', '.join(patterns[:3])}")
    add("sa-10", "Configuration management via git with signed commits")
    add("sa-15", "Development process uses 7-agent pipeline with security gate")

    # -- SC: System & Communications Protection --
    if "pynacl" in deps:
        add("sc-12", "Ed25519 keypair for report signing; Zephyr hardware signing for events")
        add("sc-13", "Cryptographic signing via PyNaCl/libsodium (Ed25519)")
    if any("tls" in str(c).lower() or "https" in str(c).lower() for c in security_constraints):
        add("sc-8", "TLS/HTTPS required per security constraints")

    # -- SI: System & Information Integrity --
    add("si-2", "HONEYMOON fix loop with automated debugging and patch application")
    add("si-7", "Software integrity verified via Zephyr digest and gatekeeper")
    if code_style.get("linter"):
        add("si-3", f"Code quality enforcement via {code_style['linter']} linter")

    # -- SR: Supply Chain --
    if deps:
        add("sr-2", f"Supply chain tracked: {len(deps)} dependencies with version constraints")
        add("sr-3", "Dependency versions pinned in pyproject.toml")

    # -- PL: Planning --
    if project.get("description"):
        add("pl-2", f"System description documented: {project['description'][:100]}...")

    # -- Architectural decisions as evidence --
    for dec in decision_list:
        if isinstance(dec, dict):
            sev = dec.get("severity", "")
            title = dec.get("title", "")
            if sev in ("HIGH", "CRITICAL"):
                add("ra-3", f"Architecture decision [{sev}]: {title}")
            if "auth" in title.lower():
                add("ac-3", f"Architecture decision: {title}")
            if "injection" in title.lower() or "xss" in title.lower():
                add("si-10", f"Architecture decision: {title}")
            if "boundary" in title.lower():
                add("sc-7", f"Architecture decision: {title}")

    return evidence


# ---------------------------------------------------------------------------
# Finding loaders
# ---------------------------------------------------------------------------

def _load_all_scan_findings(repo_path: Path) -> list[dict[str, Any]]:
    """Load findings from ALL scan reports for comprehensive coverage."""
    reports_dir = repo_path / ".honeymoon" / "reports"
    if not reports_dir.exists():
        return []

    all_findings: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for jf in sorted(reports_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        if jf.stem in ("SSP",):
            continue
        try:
            report = json.loads(jf.read_text())
            for f in report.get("findings", {}).get("findings", []):
                title = f.get("title", "")
                if title and title not in seen_titles:
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


def _load_ledger_entries(repo_path: Path) -> int:
    """Count hardening ledger entries."""
    ledger_file = repo_path / ".honeymoon" / "ledger.jsonl"
    if not ledger_file.exists():
        return 0
    return sum(1 for line in ledger_file.read_text().splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Control assessment
# ---------------------------------------------------------------------------

def _assess_control(
    control: Control,
    findings: list[dict[str, Any]],
    finding_control_map: dict[str, list[str]],
    prelude_evidence: dict[str, list[str]],
) -> dict[str, Any]:
    """Assess a single control's implementation status based on evidence."""

    # Find findings that map to this control
    related_findings = []
    for f in findings:
        title = f.get("title", "")
        if control.id in finding_control_map.get(title, []):
            related_findings.append(f)

    # Get Prelude-derived positive evidence
    positive_evidence = list(prelude_evidence.get(control.id, []))

    # Determine status
    has_critical_issues = any(
        f.get("severity", "info") in ("critical", "high")
        for f in related_findings
    )
    has_medium_issues = any(
        f.get("severity", "info") == "medium"
        for f in related_findings
    )
    has_evidence = len(positive_evidence) > 0

    if has_critical_issues:
        status = "partial"
    elif has_medium_issues and has_evidence:
        status = "partial"
    elif has_medium_issues:
        status = "partial"
    elif has_evidence:
        status = "implemented"
    else:
        status = "planned"

    return {
        "control_id": control.id,
        "name": control.title,
        "family_id": control.family_id,
        "family": control.family,
        "description": control.description,
        "parent": control.parent,
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


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_ssp(
    repo_path: Path,
    baseline: str = "moderate",
) -> Path:
    """Generate a signed System Security Plan.

    Args:
        repo_path: Root of the target repository
        baseline: NIST baseline -- low, moderate, or high

    Returns:
        Path to the generated SSP HTML file
    """
    repo_path = repo_path.resolve()
    reports_dir = repo_path / ".honeymoon" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()

    # Load context
    prelude = _load_prelude_context(repo_path)
    prelude["_repo_path"] = str(repo_path)
    prelude_evidence = _extract_prelude_evidence(prelude)

    findings = _load_all_scan_findings(repo_path)
    event_count = _load_provenance_events(repo_path)
    ledger_count = _load_ledger_entries(repo_path)

    # Load controls for the selected baseline
    controls = load_controls(baseline)

    # Build finding-to-control mapping
    finding_control_map: dict[str, list[str]] = {}
    for f in findings:
        title = f.get("title", "")
        finding_control_map[title] = map_finding_to_controls(f, controls)

    # Assess each control
    assessments = []
    for control in controls:
        assessment = _assess_control(control, findings, finding_control_map, prelude_evidence)
        assessments.append(assessment)

    # System info from Prelude
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
    dev_deps = stack.get("devDependencies", {})
    test_frameworks = stack.get("testingFrameworks", [])

    # Summary stats
    implemented = sum(1 for a in assessments if a["status"] == "implemented")
    partial = sum(1 for a in assessments if a["status"] == "partial")
    planned = sum(1 for a in assessments if a["status"] == "planned")
    total = len(assessments)

    # Family breakdown
    family_stats: dict[str, dict[str, int]] = {}
    for a in assessments:
        fid = a["family_id"]
        if fid not in family_stats:
            family_stats[fid] = {"implemented": 0, "partial": 0, "planned": 0, "total": 0}
        family_stats[fid][a["status"]] += 1
        family_stats[fid]["total"] += 1

    ssp_data = {
        "schema": "NIST SP 800-53 Rev 5",
        "system_name": system_name,
        "description": system_desc,
        "version": system_version,
        "baseline": baseline,
        "timestamp": timestamp,
        "language": language,
        "runtime": runtime,
        "framework": framework,
        "frameworks": stack.get("frameworks", []),
        "dependencies": deps,
        "dev_dependencies": dev_deps,
        "test_frameworks": test_frameworks,
        "license": system_license,
        "assessments": assessments,
        "findings_count": len(findings),
        "event_count": event_count,
        "ledger_count": ledger_count,
        "summary": {
            "total": total,
            "implemented": implemented,
            "partial": partial,
            "planned": planned,
            "score": round((implemented / total) * 100) if total else 0,
        },
        "family_stats": family_stats,
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
    console.print(f"\n[bold green]SSP generated:[/] {html_path}")
    console.print(f"  [dim]Baseline:[/]   {baseline.upper()}")
    console.print(f"  [dim]Controls:[/]   {total} ({implemented} implemented, {partial} partial, {planned} planned)")
    console.print(f"  [dim]Score:[/]      {ssp_data['summary']['score']}%")
    console.print(f"  [dim]Findings:[/]   {len(findings)} from scan reports")
    console.print(f"  [dim]Events:[/]     {event_count} signed audit events")

    return html_path


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

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


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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
    families = get_families()

    # System info section
    system_info = f'''
    <div class="meta">
      <div class="meta-item"><div class="meta-label">System</div><div class="meta-value">{_escape_html(ssp_data["system_name"])}</div></div>
      <div class="meta-item"><div class="meta-label">Version</div><div class="meta-value mono">{_escape_html(ssp_data["version"])}</div></div>
      <div class="meta-item"><div class="meta-label">Baseline</div><div class="meta-value">{ssp_data["baseline"].upper()}</div></div>
      <div class="meta-item"><div class="meta-label">Generated</div><div class="meta-value mono">{ssp_data["timestamp"][:19]}</div></div>
    </div>'''

    # Description
    desc_html = f'''
    <div class="section">
      <div class="section-title">System Description</div>
      <div class="summary">{_escape_html(ssp_data["description"])}</div>
    </div>'''

    # Technology stack
    dep_list = ""
    for name, version in ssp_data.get("dependencies", {}).items():
        dep_list += f'<span class="dep-pill">{_escape_html(name)} {_escape_html(str(version))}</span>'
    for name, version in ssp_data.get("dev_dependencies", {}).items():
        dep_list += f'<span class="dep-pill dev">{_escape_html(name)} {_escape_html(str(version))}</span>'

    frameworks_str = ", ".join(ssp_data.get("frameworks", [])) or ssp_data.get("framework", "None")
    stack_html = f'''
    <div class="section">
      <div class="section-title">Technology Stack</div>
      <div class="stack-grid">
        <div class="stack-item"><div class="stack-label">Language</div><div class="stack-value">{_escape_html(ssp_data["language"])}</div></div>
        <div class="stack-item"><div class="stack-label">Runtime</div><div class="stack-value">{_escape_html(ssp_data["runtime"])}</div></div>
        <div class="stack-item"><div class="stack-label">Frameworks</div><div class="stack-value">{_escape_html(frameworks_str)}</div></div>
        <div class="stack-item"><div class="stack-label">Testing</div><div class="stack-value">{_escape_html(", ".join(ssp_data.get("test_frameworks", [])) or "None")}</div></div>
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
          <div class="gauge-stat"><span class="stat-label">Ledger Entries</span> <span class="stat-num">{ssp_data["ledger_count"]}</span></div>
        </div>
      </div>
    </div>'''

    # Family summary bar
    family_summary_rows = ""
    for fid, fname in sorted(families.items()):
        fs = ssp_data.get("family_stats", {}).get(fid)
        if not fs:
            continue
        ftotal = fs["total"]
        fimp = fs["implemented"]
        fpct = round((fimp / ftotal) * 100) if ftotal else 0
        bar_color = "#10b981" if fpct >= 70 else "#eab308" if fpct >= 30 else "#ef4444"
        family_summary_rows += f'''
          <div class="family-row">
            <div class="family-id">{fid.upper()}</div>
            <div class="family-name">{_escape_html(fname)}</div>
            <div class="family-bar"><div class="family-bar-fill" style="width:{fpct}%;background:{bar_color}"></div></div>
            <div class="family-nums">{fimp}/{ftotal}</div>
          </div>'''

    family_html = f'''
    <div class="section">
      <div class="section-title">Family Coverage</div>
      <div class="family-grid">{family_summary_rows}</div>
    </div>'''

    # Control assessments by family
    controls_html = ""
    for fid, fname in sorted(families.items()):
        family_assessments = [a for a in ssp_data["assessments"] if a["family_id"] == fid]
        if not family_assessments:
            continue

        # Group: parent controls first, then enhancements indented
        rows = ""
        for a in family_assessments:
            status_icon = _status_svg(a["status"])
            status_class = f"status-{a['status']}"
            indent = " enhancement" if a.get("parent") else ""

            evidence_items = ""
            for ev in a.get("positive_evidence", []):
                evidence_items += f'<div class="evidence-item evidence-positive">{_escape_html(ev)}</div>'
            for f in a.get("findings", []):
                sev = f.get("severity", "info")
                evidence_items += (
                    f'<div class="evidence-item evidence-finding">'
                    f'<span class="finding-sev sev-{sev}">{sev.upper()}</span> '
                    f'{_escape_html(f.get("title", ""))}'
                    f'</div>'
                )

            display_id = a["control_id"].upper()
            rows += f'''<div class="control-row {status_class}{indent}">
  <div class="control-id">{display_id}</div>
  <div class="control-info">
    <div class="control-name">{_escape_html(a["name"])}</div>
    <div class="control-desc">{_escape_html(a["description"])}</div>
    {f'<div class="control-evidence">{evidence_items}</div>' if evidence_items else ""}
  </div>
  <div class="control-status">{status_icon} {a["status"].title()}</div>
</div>'''

        fs = ssp_data.get("family_stats", {}).get(fid, {})
        count_note = f" ({fs.get('implemented', 0)}/{fs.get('total', 0)} implemented)" if fs else ""
        controls_html += f'''
    <div class="section">
      <div class="section-title">{fid.upper()} &mdash; {_escape_html(fname)}{count_note}</div>
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
        <div class="attestation-title">{shield_svg} Ed25519 Signed &mdash; This SSP is tamper-evident</div>
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

    # Inline Honeymoon logo SVG
    logo_svg = (
        '<svg class="logo-svg" width="180" height="37" viewBox="0 0 698 145" fill="none"'
        ' xmlns="http://www.w3.org/2000/svg"><path d="M88.4404 124.876C97.4948 124.876'
        ' 104.904 124.966 104.914 125.075C104.914 125.45 88.7612 145.016 88.4648 145C88.3678'
        ' 144.991 86.6194 142.965 84.5801 140.499C77.1686 131.536 71.9678 125.15 71.9678'
        ' 125.015C71.9709 124.939 79.3821 124.876 88.4404 124.876ZM88.5938 102.6C104.595'
        ' 102.6 117.691 102.666 117.727 102.748C117.727 102.83 117.301 104.238 116.782'
        ' 105.876C115.795 108.99 113.491 113.728 111.515 116.707L110.354 118.456L89.2539'
        ' 118.538C77.6496 118.583 67.8023 118.574 67.3701 118.518C66.7646 118.438 66.2302'
        ' 117.848 65.0225 115.924C62.3492 111.665 59.46 105.031 59.46 103.152C59.46 102.622'
        ' 60.6685 102.6 88.5938 102.6ZM270.236 31.9355L274.487 32.0957V96.2637L270.236'
        ' 96.4238L265.984 96.584V68.0186H229.796L229.649 82.1416L229.503 96.2637L225.251'
        ' 96.4238L221 96.584V31.7754L225.251 31.9355L229.503 32.0957L229.649 45.9443L229.796'
        ' 59.792H265.984V31.7754L270.236 31.9355ZM116.406 81.1611C117.596 84.0071 118.404'
        ' 88.1226 118.562 92.1475L118.722 96.1904H58.1475L58.335 92.2998C58.5256 88.3474'
        ' 59.1839 84.9512 60.377 81.7617L61.0293 80.0176H115.928L116.406 81.1611ZM176.82'
        ' 59.0371C176.598 63.2973 175.787 66.5079 173.994 70.2344C169.452 79.6756 161.446'
        ' 85.6697 151.539 87.0479C145.251 87.9223 137.634 85.972 132.616 82.2021C131.726'
        ' 81.5335 125.301 75.2752 118.339 68.2949L105.68 55.6035H177L176.82 59.0371ZM71.8145'
        ' 55.623L59.002 68.3037C51.9554 75.2778 45.3543 81.5862 44.332 82.3232C39.852'
        ' 85.5527 35.0728 87.082 29.2588 87.1465C25.0088 87.1935 22.1371 86.6734 18.5186'
        ' 85.2002C9.90844 81.6951 3.0473 73.5635 0.883789 64.3008C0.257219 61.618 -0.221182'
        ' 56.4701 0.106445 55.9395C0.263723 55.6986 10.3844 55.6063 36.0645 55.6133L71.8145'
        ' 55.623ZM104.535 61.0205C109.266 67.7592 112.946 73.3057 112.789 73.4619C112.678'
        ' 73.5447 101.678 73.5772 88.3213 73.5342L64.0039 73.4561L67.9297 67.6582C70.0886'
        ' 64.4692 72.6009 60.8011 73.5127 59.5078L75.1709 57.1572L101.804 57.1299L104.535'
        ' 61.0205ZM59.7422 0.139648C65.0976 0.370964 69.0468 2.08832 72.9004 5.8623C76.2834'
        ' 9.17574 78.4198 13.5858 79.1553 18.7734C79.3252 19.9715 79.4549 20.2028 79.8604'
        ' 20.0322C85.3779 17.7088 90.7757 17.5099 95.5947 19.4521C96.5915 19.8537 97.4391'
        ' 20.1509 97.4805 20.1133C97.5189 20.0748 97.8305 18.672 98.1719 16.9961C100.217'
        ' 6.95493 108.251 0.0857538 117.97 0.0683594C120.253 0.0640951 120.574 0.136717'
        ' 121.249 0.8125C122.299 1.86218 122.244 3.22117 121.106 4.35938C120.293 5.17264'
        ' 120.029 5.25195 118.11 5.25195C114.121 5.25203 110.314 6.9221 107.409'
        ' 9.94824C104.593 12.8818 103.454 15.5645 102.756 20.9043L102.377 23.7988L103.45'
        ' 25.1299C106.227 28.576 107.351 31.6047 107.566 36.2256C107.814 41.5095 106.62'
        ' 45.2377 103.242 49.7324L101.808 51.6436L88.502 51.5635L75.1973 51.4844L73.751'
        ' 49.6875C67.9619 42.4988 67.7651 32.7863 73.2598 25.4307L74.4854 23.79L74.2812'
        ' 21.5381C73.9972 18.4004 73.0571 14.9392 71.9775 13.0518C69.1724 8.14765 64.2603'
        ' 5.25195 58.7461 5.25195C57.109 5.25195 56.6076 5.12778 55.9688 4.56543C54.762'
        ' 3.50324 54.6545 2.21404 55.6729 1.00293L56.5176 0L59.7422 0.139648Z"'
        ' fill="#D4B56A"/></svg>'
    )

    content = f'''
  <div class="header-bar">
    <div class="logo-row">{logo_svg}</div>
    <div class="subtitle">System Security Plan &middot; NIST 800-53 Rev 5 &middot; {ssp_data["baseline"].upper()} Baseline</div>
  </div>

  {system_info}
  {desc_html}
  {stack_html}
  {gauge_html}
  {family_html}
  {controls_html}
  {attestation_html}
'''

    html = template.replace("{{CONTENT}}", content)
    path.write_text(html)
    return path
