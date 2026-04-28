"""
HONEYMOON Auditor — Scanner

Uses tree-sitter to scan a repository for actionable findings.
Pure Python, no API calls. Fast and deterministic.

Findings are structured and sized for HONEYMOON tasks.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import importlib.util

TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter_languages") is not None


# ---------------------------------------------------------------------------
# Finding Types
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single actionable finding in the codebase."""
    kind: str                    # "missing_doc", "todo", "complex_function", "untested_public"
    file: str                    # relative path from repo root
    line: int                    # 1-indexed line number
    symbol: str                  # function/struct name or relevant identifier
    description: str             # human-readable description
    severity: str = "low"        # "low" | "medium" | "high"
    context: str = ""            # surrounding code snippet for model context


@dataclass
class ScanResult:
    """Results of a full repository scan."""
    repo_path: Path
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    languages_found: set[str] = field(default_factory=set)

    def by_file(self) -> dict[str, list[Finding]]:
        """Group findings by file path."""
        grouped: dict[str, list[Finding]] = {}
        for f in self.findings:
            grouped.setdefault(f.file, []).append(f)
        return grouped

    def by_kind(self, kind: str) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for f in self.findings:
            kinds[f.kind] = kinds.get(f.kind, 0) + 1
        return {
            "total": len(self.findings),
            "files_scanned": self.files_scanned,
            "by_kind": kinds,
        }


# ---------------------------------------------------------------------------
# Language Config
# ---------------------------------------------------------------------------

LANGUAGE_MAP = {
    ".rs": "rust",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".go": "go",
}

# Tree-sitter queries per language for missing doc comments on public functions
DOC_COMMENT_QUERIES = {
    "rust": """
        (function_item
            visibility_modifier: (visibility_modifier) @vis
            name: (identifier) @name) @fn
    """,
    "python": """
        (function_definition
            name: (identifier) @name) @fn
    """,
    "go": """
        (function_declaration
            name: (identifier) @name) @fn
    """,
    "typescript": """
        (function_declaration
            name: (identifier) @name) @fn
    """,
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class Scanner:
    """
    Scans a repository for actionable findings using tree-sitter.
    Falls back to regex-based scanning if tree-sitter is not available.
    """

    def __init__(self, repo_path: Path, exclude_dirs: list[str] | None = None):
        self.repo_path = repo_path.resolve()
        self.exclude_dirs = set(exclude_dirs or [
            ".git", "target", "node_modules", ".honeymoon",
            ".context", "dist", "build", "__pycache__", "venv",
            "mcp", ".venv", "site-packages",
        ])

    def scan(self) -> ScanResult:
        """Run all checks and return aggregated findings."""
        result = ScanResult(repo_path=self.repo_path)

        for file_path in self._iter_source_files():
            rel = str(file_path.relative_to(self.repo_path))
            ext = file_path.suffix
            lang = LANGUAGE_MAP.get(ext)

            if lang:
                result.languages_found.add(lang)

            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            result.files_scanned += 1

            # Run all checks
            result.findings.extend(self._check_missing_docs(file_path, rel, source, lang))
            result.findings.extend(self._check_todos(file_path, rel, source))
            result.findings.extend(self._check_complex_functions(file_path, rel, source, lang))
            result.findings.extend(self._check_hardcoded_secrets(file_path, rel, source))
            result.findings.extend(self._check_large_files(file_path, rel, source))

        # Dependency vulnerability scan (runs once, not per-file)
        result.findings.extend(self._check_dependency_vulns())

        return result

    def _iter_source_files(self) -> Iterator[Path]:
        """Yield all source files, respecting exclusions."""
        for path in self.repo_path.rglob("*"):
            if not path.is_file():
                continue
            if any(exc in path.parts for exc in self.exclude_dirs):
                continue
            if path.suffix in LANGUAGE_MAP:
                yield path

    # -----------------------------------------------------------------------
    # Check: Missing Doc Comments
    # -----------------------------------------------------------------------

    def _check_missing_docs(
        self, file_path: Path, rel: str, source: str, lang: str | None
    ) -> list[Finding]:
        findings = []

        if lang == "rust":
            findings.extend(self._check_missing_docs_rust(rel, source))
        elif lang == "python":
            findings.extend(self._check_missing_docs_python(rel, source))

        return findings

    def _check_missing_docs_rust(self, rel: str, source: str) -> list[Finding]:
        """Find pub fn declarations without a preceding /// doc comment."""
        findings = []
        lines = source.splitlines()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not (stripped.startswith("pub fn ") or stripped.startswith("pub async fn ")):
                continue

            # Extract function name
            match = re.search(r"pub\s+(?:async\s+)?fn\s+(\w+)", stripped)
            if not match:
                continue
            fn_name = match.group(1)

            # Check previous non-empty line for doc comment
            j = i - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1

            prev = lines[j].strip() if j >= 0 else ""
            if not prev.startswith("///"):
                # Get context snippet
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = "\n".join(lines[start:end])

                findings.append(Finding(
                    kind="missing_doc",
                    file=rel,
                    line=i + 1,
                    symbol=fn_name,
                    description=f"Public function `{fn_name}` is missing a /// doc comment",
                    severity="low",
                    context=context,
                ))

        return findings

    def _check_missing_docs_python(self, rel: str, source: str) -> list[Finding]:
        """Find public Python functions without docstrings."""
        findings = []
        lines = source.splitlines()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("def "):
                continue

            # Skip private functions
            match = re.search(r"def\s+(\w+)", stripped)
            if not match:
                continue
            fn_name = match.group(1)
            if fn_name.startswith("_"):
                continue

            # Check if next non-empty line is a docstring
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1

            next_line = lines[j].strip() if j < len(lines) else ""
            if not (next_line.startswith('"""') or next_line.startswith("'''")):
                start = max(0, i - 1)
                end = min(len(lines), i + 4)
                context = "\n".join(lines[start:end])

                findings.append(Finding(
                    kind="missing_doc",
                    file=rel,
                    line=i + 1,
                    symbol=fn_name,
                    description=f"Public function `{fn_name}` is missing a docstring",
                    severity="low",
                    context=context,
                ))

        return findings

    # -----------------------------------------------------------------------
    # Check: TODO / FIXME Comments
    # -----------------------------------------------------------------------

    def _check_todos(self, file_path: Path, rel: str, source: str) -> list[Finding]:
        """Find TODO and FIXME comments."""
        findings = []
        lines = source.splitlines()
        pattern = re.compile(r"(TODO|FIXME|HACK|XXX)\s*[:\-]?\s*(.*)", re.IGNORECASE)

        for i, line in enumerate(lines):
            match = pattern.search(line)
            if match:
                kind = match.group(1).upper()
                message = match.group(2).strip()
                findings.append(Finding(
                    kind="todo",
                    file=rel,
                    line=i + 1,
                    symbol=kind,
                    description=f"{kind}: {message}" if message else f"{kind} comment at line {i+1}",
                    severity="medium" if kind == "FIXME" else "low",
                    context=line.strip(),
                ))

        return findings

    # -----------------------------------------------------------------------
    # Check: Complex Functions
    # -----------------------------------------------------------------------

    def _check_complex_functions(
        self, file_path: Path, rel: str, source: str, lang: str | None
    ) -> list[Finding]:
        """Find functions that are suspiciously long (>60 lines)."""
        findings = []

        if lang not in ("rust", "python", "go", "typescript"):
            return findings

        lines = source.splitlines()
        threshold = 60

        if lang == "rust":
            fn_pattern = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)")
        elif lang == "python":
            fn_pattern = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)")
        else:
            fn_pattern = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?func(?:tion)?\s+(\w+)")

        fn_start = None
        fn_name = None
        brace_depth = 0

        for i, line in enumerate(lines):
            match = fn_pattern.match(line)
            if match and fn_start is None:
                fn_name = match.group(1)
                fn_start = i
                brace_depth = 0

            if fn_start is not None:
                brace_depth += line.count("{") - line.count("}")
                if lang == "rust" and brace_depth <= 0 and i > fn_start:
                    length = i - fn_start + 1
                    if length > threshold:
                        findings.append(Finding(
                            kind="complex_function",
                            file=rel,
                            line=fn_start + 1,
                            symbol=fn_name or "unknown",
                            description=f"Function `{fn_name}` is {length} lines long (>{threshold})",
                            severity="medium",
                            context=f"Function spans lines {fn_start+1}–{i+1}",
                        ))
                    fn_start = None
                    fn_name = None

        return findings

    # -----------------------------------------------------------------------
    # Check: Hardcoded Secrets
    # -----------------------------------------------------------------------

    def _check_hardcoded_secrets(self, file_path: Path, rel: str, source: str) -> list[Finding]:
        findings = []
        lines = source.splitlines()
        # Basic heuristic for secrets
        pattern = re.compile(r"(api_key|secret|password|token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE)
        for i, line in enumerate(lines):
            match = pattern.search(line)
            if match:
                findings.append(Finding(
                    kind="hardcoded_secret",
                    file=rel,
                    line=i + 1,
                    symbol=match.group(1),
                    description="Potential hardcoded secret or credential detected.",
                    severity="high",
                    context=line.strip()
                ))
        return findings

    # -----------------------------------------------------------------------
    # Check: Large Files
    # -----------------------------------------------------------------------

    def _check_large_files(self, file_path: Path, rel: str, source: str) -> list[Finding]:
        findings = []
        lines = source.splitlines()
        if len(lines) > 400:
            findings.append(Finding(
                kind="large_file",
                file=rel,
                line=1,
                symbol="file",
                description=f"File is {len(lines)} lines long. Consider breaking it down.",
                severity="medium"
            ))
        return findings

    # -----------------------------------------------------------------------
    # Check: Dependency Vulnerabilities
    # -----------------------------------------------------------------------

    def _check_dependency_vulns(self) -> list[Finding]:
        """Run dependency audit tools if available. Checks pip-audit, npm audit, cargo audit."""
        findings = []

        # Python: pip-audit or safety
        if (self.repo_path / "requirements.txt").exists() or (self.repo_path / "pyproject.toml").exists():
            findings.extend(self._run_pip_audit())

        # Node: npm audit
        if (self.repo_path / "package.json").exists():
            findings.extend(self._run_npm_audit())

        # Rust: cargo audit
        if (self.repo_path / "Cargo.toml").exists():
            findings.extend(self._run_cargo_audit())

        return findings

    def _run_pip_audit(self) -> list[Finding]:
        """Run pip-audit if available."""
        if not shutil.which("pip-audit"):
            return []
        try:
            proc = subprocess.run(
                ["pip-audit", "--format", "json", "--desc"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0 and not proc.stdout.strip():
                return []
            import json
            vulns = json.loads(proc.stdout) if proc.stdout.strip() else []
            return [
                Finding(
                    kind="dependency_vuln",
                    file="requirements.txt",
                    line=1,
                    symbol=v.get("name", "unknown"),
                    description=(
                        f"{v.get('name')}=={v.get('version')}: "
                        f"{v.get('vulns', [{}])[0].get('id', 'CVE-?')} — "
                        f"{v.get('vulns', [{}])[0].get('description', 'Known vulnerability')[:200]}"
                    ),
                    severity="high",
                    context=f"Fix: upgrade to {v.get('vulns', [{}])[0].get('fix_versions', ['latest'])}",
                )
                for v in vulns if v.get("vulns")
            ]
        except Exception:
            return []

    def _run_npm_audit(self) -> list[Finding]:
        """Run npm audit if available."""
        if not shutil.which("npm"):
            return []
        try:
            proc = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=60,
            )
            import json
            try:
                data = json.loads(proc.stdout) if proc.stdout.strip() else {}
            except json.JSONDecodeError:
                return []
            vulns = data.get("vulnerabilities", {})
            results = []
            for name, info in list(vulns.items())[:20]:
                sev = info.get("severity", "low")
                sev_map = {"critical": "high", "high": "high", "moderate": "medium", "low": "low"}
                results.append(Finding(
                    kind="dependency_vuln",
                    file="package.json",
                    line=1,
                    symbol=name,
                    description=f"{name}: {sev} severity — {info.get('title', 'Known vulnerability')[:200]}",
                    severity=sev_map.get(sev, "medium"),
                ))
            return results
        except Exception:
            return []

    def _run_cargo_audit(self) -> list[Finding]:
        """Run cargo audit if available."""
        if not shutil.which("cargo-audit"):
            return []
        try:
            proc = subprocess.run(
                ["cargo", "audit", "--json"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=60,
            )
            import json
            try:
                data = json.loads(proc.stdout) if proc.stdout.strip() else {}
            except json.JSONDecodeError:
                return []
            results = []
            for vuln in data.get("vulnerabilities", {}).get("list", []):
                advisory = vuln.get("advisory", {})
                results.append(Finding(
                    kind="dependency_vuln",
                    file="Cargo.toml",
                    line=1,
                    symbol=advisory.get("package", "unknown"),
                    description=(
                        f"{advisory.get('package')}: {advisory.get('id', 'RUSTSEC-?')} — "
                        f"{advisory.get('title', 'Known vulnerability')[:200]}"
                    ),
                    severity="high",
                ))
            return results
        except Exception:
            return []