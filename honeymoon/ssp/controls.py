"""NIST 800-53 Rev 5 control families and finding-to-control mapping."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Control:
    id: str
    name: str
    family: str
    description: str
    evidence_keywords: list[str] = field(default_factory=list)


# Subset of NIST 800-53 Rev 5 controls most relevant to software systems.
# Grouped by family. Each control includes keywords that map scan findings.
CONTROLS: list[Control] = [
    # AC — Access Control
    Control("AC-2", "Account Management", "AC",
            "Manage system accounts including creating, enabling, modifying, disabling, and removing accounts.",
            ["authentication", "user account", "role", "rbac", "authorization"]),
    Control("AC-3", "Access Enforcement", "AC",
            "Enforce approved authorizations for logical access to information and system resources.",
            ["authorization", "access control", "permission", "forbidden", "401", "403", "middleware", "guard"]),
    Control("AC-6", "Least Privilege", "AC",
            "Employ the principle of least privilege, allowing only authorized accesses necessary for organizational missions.",
            ["privilege", "admin", "root", "sudo", "role", "allowlist", "permission"]),
    Control("AC-7", "Unsuccessful Logon Attempts", "AC",
            "Enforce a limit of consecutive invalid logon attempts by a user.",
            ["rate limit", "login", "brute force", "lockout", "throttle"]),
    Control("AC-17", "Remote Access", "AC",
            "Establish and document usage restrictions and implementation guidance for remote access.",
            ["remote access", "ssh", "vpn", "api key", "bearer token", "cors"]),

    # AU — Audit and Accountability
    Control("AU-2", "Event Logging", "AU",
            "Identify events that the system is capable of logging in support of the audit function.",
            ["logging", "audit", "event", "log file", "audit trail"]),
    Control("AU-3", "Content of Audit Records", "AU",
            "Ensure audit records contain sufficient information to establish what occurred.",
            ["audit record", "timestamp", "event type", "user id", "action"]),
    Control("AU-6", "Audit Record Review, Analysis, and Reporting", "AU",
            "Review and analyze system audit records for indications of inappropriate or unusual activity.",
            ["audit review", "monitoring", "anomaly", "alert"]),
    Control("AU-9", "Protection of Audit Information", "AU",
            "Protect audit information and audit logging tools from unauthorized access, modification, and deletion.",
            ["audit integrity", "tamper", "immutable", "append-only", "signed log"]),
    Control("AU-10", "Non-repudiation", "AU",
            "Provide irrefutable evidence that an individual performed specific actions.",
            ["non-repudiation", "signature", "signing", "attestation", "provenance"]),

    # CM — Configuration Management
    Control("CM-2", "Baseline Configuration", "CM",
            "Develop, document, and maintain a current baseline configuration of the system.",
            ["baseline", "configuration", "config file", "default", "environment variable"]),
    Control("CM-3", "Configuration Change Control", "CM",
            "Track, review, approve, and audit changes to the system.",
            ["change control", "git", "commit", "version control", "pull request"]),
    Control("CM-6", "Configuration Settings", "CM",
            "Establish and document mandatory configuration settings for IT products.",
            ["configuration", "settings", "hardcoded", "default password", "secret", "env var"]),
    Control("CM-7", "Least Functionality", "CM",
            "Configure the system to provide only essential capabilities and prohibit or restrict use of non-essential functions.",
            ["least functionality", "unused", "dead code", "disabled", "debug mode"]),
    Control("CM-8", "System Component Inventory", "CM",
            "Develop and document an inventory of system components.",
            ["inventory", "dependency", "package", "library", "sbom", "bill of materials"]),

    # IA — Identification and Authentication
    Control("IA-2", "Identification and Authentication (Organizational Users)", "IA",
            "Uniquely identify and authenticate organizational users.",
            ["authentication", "login", "identity", "credential", "mfa", "token"]),
    Control("IA-5", "Authenticator Management", "IA",
            "Manage system authenticators by verifying identity before issuing, revoking expired authenticators.",
            ["password", "credential", "api key", "secret", "token management", "rotation"]),

    # RA — Risk Assessment
    Control("RA-3", "Risk Assessment", "RA",
            "Conduct an assessment of risk including the likelihood and magnitude of harm.",
            ["risk assessment", "vulnerability", "threat", "impact", "likelihood"]),
    Control("RA-5", "Vulnerability Monitoring and Scanning", "RA",
            "Monitor and scan for vulnerabilities in the system and hosted applications.",
            ["vulnerability scan", "cve", "security scan", "static analysis", "dependency audit"]),

    # SA — System and Services Acquisition
    Control("SA-11", "Developer Testing and Evaluation", "SA",
            "Require the developer to create and implement a security assessment plan.",
            ["test", "pytest", "unit test", "integration test", "security test", "coverage"]),

    # SC — System and Communications Protection
    Control("SC-7", "Boundary Protection", "SC",
            "Monitor and control communications at the external managed interfaces of the system.",
            ["boundary", "firewall", "cors", "network", "ingress", "egress", "trust boundary"]),
    Control("SC-8", "Transmission Confidentiality and Integrity", "SC",
            "Protect the confidentiality and integrity of transmitted information.",
            ["tls", "https", "encryption", "ssl", "certificate"]),
    Control("SC-12", "Cryptographic Key Establishment and Management", "SC",
            "Establish and manage cryptographic keys when cryptography is employed.",
            ["cryptographic key", "key management", "signing key", "ed25519", "keypair"]),
    Control("SC-13", "Cryptographic Protection", "SC",
            "Determine the cryptographic uses and implement the required cryptography.",
            ["encryption", "hash", "signature", "cryptographic", "aes", "sha"]),
    Control("SC-28", "Protection of Information at Rest", "SC",
            "Protect the confidentiality and integrity of information at rest.",
            ["encryption at rest", "database encryption", "file encryption", "secret storage"]),

    # SI — System and Information Integrity
    Control("SI-2", "Flaw Remediation", "SI",
            "Identify, report, and correct system flaws in a timely manner.",
            ["flaw", "bug fix", "patch", "remediation", "vulnerability fix"]),
    Control("SI-3", "Malicious Code Protection", "SI",
            "Implement malicious code protection mechanisms at system entry and exit points.",
            ["malware", "malicious", "injection", "xss", "sanitiz"]),
    Control("SI-4", "System Monitoring", "SI",
            "Monitor the system to detect attacks, indicators of potential attacks, and unauthorized connections.",
            ["monitoring", "intrusion", "detection", "alert", "anomaly"]),
    Control("SI-10", "Information Input Validation", "SI",
            "Check the validity of information inputs to the system.",
            ["input validation", "sanitiz", "escap", "xss", "injection", "sql injection", "command injection"]),
]

CONTROL_MAP = {c.id: c for c in CONTROLS}
FAMILIES = {
    "AC": "Access Control",
    "AU": "Audit and Accountability",
    "CM": "Configuration Management",
    "IA": "Identification and Authentication",
    "RA": "Risk Assessment",
    "SA": "System and Services Acquisition",
    "SC": "System and Communications Protection",
    "SI": "System and Information Integrity",
}


def map_finding_to_controls(finding: dict) -> list[str]:
    """Map a scan finding to relevant NIST 800-53 control IDs."""
    text = " ".join([
        finding.get("title", ""),
        finding.get("analysis", ""),
        finding.get("evidence", ""),
    ]).lower()

    matched = []
    for control in CONTROLS:
        for keyword in control.evidence_keywords:
            if keyword.lower() in text:
                matched.append(control.id)
                break
    return matched
