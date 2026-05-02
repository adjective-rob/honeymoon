"""NIST 800-53 Rev 5 — Full OSCAL catalog loader + finding-to-control mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Control:
    id: str
    title: str
    family_id: str
    family: str
    description: str
    parent: str | None = None
    evidence_keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Keyword map: family_id -> keywords that indicate evidence for that family
# Used by map_finding_to_controls to link findings to NIST controls
# ---------------------------------------------------------------------------

FAMILY_KEYWORDS: dict[str, list[str]] = {
    "ac": [
        "access control", "authorization", "authentication", "permission", "rbac",
        "role", "privilege", "allowlist", "blocklist", "403", "401", "forbidden",
        "cors", "middleware", "guard", "rate limit", "login", "brute force",
        "lockout", "throttle", "remote access", "ssh", "vpn", "api key",
        "bearer token", "session", "logout", "account",
    ],
    "at": ["training", "awareness", "security training"],
    "au": [
        "logging", "audit", "event", "log file", "audit trail", "audit record",
        "timestamp", "event type", "action", "monitoring", "anomaly", "alert",
        "tamper", "immutable", "append-only", "signed log", "non-repudiation",
        "signature", "signing", "attestation", "provenance",
    ],
    "ca": [
        "assessment", "authorization to operate", "continuous monitoring",
        "penetration test", "plan of action", "security assessment",
    ],
    "cm": [
        "configuration", "baseline", "config file", "environment variable",
        "change control", "git", "commit", "version control", "pull request",
        "hardcoded", "default password", "secret", "env var", "least functionality",
        "dead code", "debug mode", "inventory", "dependency", "package",
        "library", "sbom", "bill of materials",
    ],
    "cp": [
        "contingency", "backup", "recovery", "disaster", "failover",
        "redundancy", "availability",
    ],
    "ia": [
        "identification", "authentication", "login", "identity", "credential",
        "mfa", "token", "password", "api key", "secret", "token management",
        "rotation", "authenticator",
    ],
    "ir": [
        "incident", "response", "breach", "compromise", "forensic",
        "containment", "eradication",
    ],
    "ma": ["maintenance", "patch", "update", "upgrade"],
    "mp": ["media", "sanitization", "disposal", "storage"],
    "pe": ["physical", "facility", "badge", "lock", "cctv"],
    "pl": ["planning", "security plan", "rules of behavior"],
    "pm": ["program management", "risk management", "governance"],
    "ps": ["personnel", "screening", "termination", "transfer"],
    "pt": ["privacy", "pii", "consent", "data subject"],
    "ra": [
        "risk assessment", "vulnerability", "threat", "impact", "likelihood",
        "vulnerability scan", "cve", "security scan", "static analysis",
        "dependency audit", "pip-audit", "npm audit",
    ],
    "sa": [
        "acquisition", "developer", "supply chain", "test", "pytest",
        "unit test", "integration test", "security test", "coverage",
        "code review", "secure development",
    ],
    "sc": [
        "boundary", "firewall", "cors", "network", "ingress", "egress",
        "trust boundary", "tls", "https", "encryption", "ssl", "certificate",
        "cryptographic key", "key management", "signing key", "ed25519",
        "keypair", "hash", "sha", "aes", "encryption at rest",
        "database encryption", "file encryption", "secret storage",
    ],
    "si": [
        "flaw", "bug fix", "patch", "remediation", "vulnerability fix",
        "malware", "malicious", "injection", "xss", "sanitiz", "escap",
        "input validation", "sql injection", "command injection",
        "monitoring", "intrusion", "detection", "integrity",
    ],
    "sr": [
        "supply chain", "provenance", "component", "third-party",
        "counterfeit", "tampering",
    ],
}

# Per-control keyword overrides for more precise matching
CONTROL_KEYWORDS: dict[str, list[str]] = {
    "ac-2": ["account management", "user account", "role", "rbac"],
    "ac-3": ["access enforcement", "authorization", "permission", "forbidden"],
    "ac-6": ["least privilege", "privilege", "admin", "root", "sudo"],
    "ac-7": ["unsuccessful logon", "rate limit", "brute force", "lockout"],
    "ac-17": ["remote access", "ssh", "vpn", "api key", "bearer token"],
    "au-2": ["event logging", "audit", "logging"],
    "au-3": ["audit record", "timestamp", "event type"],
    "au-9": ["audit integrity", "tamper", "immutable", "append-only", "signed log"],
    "au-10": ["non-repudiation", "signature", "signing", "attestation", "provenance"],
    "au-12": ["audit generation", "audit log", "event logging"],
    "cm-2": ["baseline configuration", "config file", "default"],
    "cm-3": ["configuration change", "git", "commit", "version control"],
    "cm-6": ["configuration settings", "hardcoded", "default password", "env var"],
    "cm-7": ["least functionality", "dead code", "debug mode"],
    "cm-8": ["component inventory", "dependency", "sbom", "bill of materials"],
    "ia-2": ["identification", "authentication", "login", "mfa"],
    "ia-5": ["authenticator", "password", "credential", "api key", "rotation"],
    "ra-3": ["risk assessment", "vulnerability", "threat", "impact"],
    "ra-5": ["vulnerability scan", "cve", "static analysis", "dependency audit"],
    "sa-11": ["developer testing", "pytest", "unit test", "coverage"],
    "sc-7": ["boundary protection", "firewall", "cors", "trust boundary"],
    "sc-8": ["transmission", "tls", "https", "encryption", "ssl"],
    "sc-12": ["cryptographic key", "key management", "ed25519", "keypair"],
    "sc-13": ["cryptographic protection", "encryption", "hash", "signature"],
    "sc-28": ["information at rest", "encryption at rest", "secret storage"],
    "si-2": ["flaw remediation", "bug fix", "patch"],
    "si-3": ["malicious code", "malware", "injection", "xss"],
    "si-4": ["system monitoring", "intrusion", "detection", "alert"],
    "si-10": ["input validation", "sanitiz", "escap", "injection"],
}


def _load_catalog() -> dict[str, Any]:
    """Load the OSCAL catalog from the bundled JSON file."""
    catalog_path = Path(__file__).parent / "oscal_catalog.json"
    return json.loads(catalog_path.read_text())


def load_controls(baseline: str | None = None) -> list[Control]:
    """Load controls from the OSCAL catalog, optionally filtered by baseline.

    Args:
        baseline: "low", "moderate", "high", or None for all controls.

    Returns:
        List of Control objects.
    """
    catalog = _load_catalog()
    families = catalog["families"]
    baseline_ids: set[str] | None = None

    if baseline and baseline in catalog.get("baselines", {}):
        baseline_ids = set(catalog["baselines"][baseline])

    controls = []
    for entry in catalog["controls"]:
        cid = entry["id"]
        if baseline_ids is not None and cid not in baseline_ids:
            continue

        # Only use specific per-control keywords for finding mapping.
        # Controls without specific keywords get empty list — they won't
        # match findings, keeping the SSP score honest.
        keywords = CONTROL_KEYWORDS.get(cid, [])

        controls.append(Control(
            id=cid,
            title=entry["title"],
            family_id=entry["family_id"],
            family=families.get(entry["family_id"], entry["family_id"]),
            description=entry.get("description", ""),
            parent=entry.get("parent"),
            evidence_keywords=keywords,
        ))

    return controls


def get_families() -> dict[str, str]:
    """Return family_id -> family_name mapping."""
    return _load_catalog()["families"]


def get_baselines() -> dict[str, list[str]]:
    """Return baseline -> list of control IDs."""
    return _load_catalog().get("baselines", {})


def map_finding_to_controls(
    finding: dict[str, Any],
    controls: list[Control],
) -> list[str]:
    """Map a scan finding to relevant NIST 800-53 control IDs."""
    text = " ".join([
        finding.get("title", ""),
        finding.get("analysis", ""),
        finding.get("evidence", ""),
    ]).lower()

    matched = []
    for control in controls:
        for keyword in control.evidence_keywords:
            if keyword.lower() in text:
                matched.append(control.id)
                break
    return matched
