"""
HONEYMOON Native Context — Prelude-free codebase understanding.

Generates a lightweight `.honeymoon/context.json` using Python's own
indexer and symbol extraction. No Node.js, no external CLI.

This is the baseline context layer. When Prelude is installed, it
takes over with richer analysis. When it's not, agents still get:
  - Stack detection (language, framework, package manager)
  - File map with symbol counts
  - Import graph (who depends on what)
  - Inferred constraints from config files

The output implements the same interface as PreludeContext so agents
don't need to know which backend generated the context.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from honeymoon.indexer import build_index, RepoIndex


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

_FRAMEWORK_MARKERS = {
    # Python
    "fastapi": ("FastAPI", "python"),
    "flask": ("Flask", "python"),
    "django": ("Django", "python"),
    "typer": ("Typer CLI", "python"),
    "click": ("Click CLI", "python"),
    "pytest": ("pytest", "python"),
    # JavaScript / TypeScript
    "react": ("React", "typescript"),
    "next": ("Next.js", "typescript"),
    "express": ("Express", "javascript"),
    "vue": ("Vue", "typescript"),
    "svelte": ("Svelte", "typescript"),
    # Rust
    "actix-web": ("Actix Web", "rust"),
    "axum": ("Axum", "rust"),
    "tokio": ("Tokio", "rust"),
    "clap": ("Clap CLI", "rust"),
    # Go
    "gin": ("Gin", "go"),
    "echo": ("Echo", "go"),
}

_LANG_BY_EXTENSION = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
}


def _detect_stack(repo_path: Path, index: RepoIndex) -> dict[str, Any]:
    """Detect language, framework, and package manager from project files."""
    stack: dict[str, Any] = {
        "language": "unknown",
        "framework": None,
        "package_manager": None,
        "test_framework": None,
    }

    # Primary language by file count
    if index.languages:
        top_ext = max(index.languages, key=index.languages.get)
        stack["language"] = _LANG_BY_EXTENSION.get(top_ext, top_ext)

    # Package manager
    if (repo_path / "Cargo.toml").exists():
        stack["package_manager"] = "cargo"
        stack["language"] = "rust"
    elif (repo_path / "package.json").exists():
        stack["package_manager"] = "npm"
        if (repo_path / "pnpm-lock.yaml").exists():
            stack["package_manager"] = "pnpm"
        elif (repo_path / "yarn.lock").exists():
            stack["package_manager"] = "yarn"
        elif (repo_path / "bun.lockb").exists():
            stack["package_manager"] = "bun"
    elif (repo_path / "pyproject.toml").exists():
        stack["package_manager"] = "pip"
        if (repo_path / "poetry.lock").exists():
            stack["package_manager"] = "poetry"
        elif (repo_path / "uv.lock").exists():
            stack["package_manager"] = "uv"
    elif (repo_path / "go.mod").exists():
        stack["package_manager"] = "go modules"
        stack["language"] = "go"

    # Framework detection from dependency files
    deps_text = ""
    for dep_file in ["pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod"]:
        p = repo_path / dep_file
        if p.exists():
            try:
                deps_text += p.read_text(errors="ignore").lower()
            except Exception:
                pass

    for marker, (framework, _) in _FRAMEWORK_MARKERS.items():
        if marker in deps_text:
            stack["framework"] = framework
            break

    # Test framework
    if "pytest" in deps_text:
        stack["test_framework"] = "pytest"
    elif '"jest"' in deps_text or "'jest'" in deps_text:
        stack["test_framework"] = "jest"
    elif '"vitest"' in deps_text:
        stack["test_framework"] = "vitest"
    elif '"mocha"' in deps_text:
        stack["test_framework"] = "mocha"

    return stack


# ---------------------------------------------------------------------------
# Import graph
# ---------------------------------------------------------------------------

def _build_import_graph(index: RepoIndex) -> dict[str, list[str]]:
    """Build a simplified import graph from the index.

    Returns: { "file.py": ["dep1.py", "dep2.py"] }
    Only includes local imports (files that exist in the index).
    """
    graph: dict[str, list[str]] = {}
    all_files = set(index.files.keys())

    for rel_path, entry in index.files.items():
        if not entry.imports:
            continue

        deps = []
        for imp in entry.imports:
            # Convert dotted import to file path
            candidate = imp.replace(".", "/") + ".py"
            if candidate in all_files:
                deps.append(candidate)
            # Try as package __init__
            candidate_init = imp.replace(".", "/") + "/__init__.py"
            if candidate_init in all_files:
                deps.append(candidate_init)

        if deps:
            graph[rel_path] = sorted(set(deps))

    return graph


# ---------------------------------------------------------------------------
# Constraint inference
# ---------------------------------------------------------------------------

def _infer_constraints(repo_path: Path) -> list[str]:
    """Infer project constraints from config files."""
    constraints: list[str] = []

    # Python version constraint
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            match = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
            if match:
                constraints.append(f"Python {match.group(1)}")
        except Exception:
            pass

    # Rust edition
    cargo = repo_path / "Cargo.toml"
    if cargo.exists():
        try:
            text = cargo.read_text()
            match = re.search(r'edition\s*=\s*"(\d+)"', text)
            if match:
                constraints.append(f"Rust edition {match.group(1)}")
        except Exception:
            pass

    # Node engine constraint
    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            engines = data.get("engines", {})
            if "node" in engines:
                constraints.append(f"Node {engines['node']}")
        except Exception:
            pass

    # Linter config
    if (repo_path / "ruff.toml").exists() or (repo_path / ".ruff.toml").exists():
        constraints.append("Linter: ruff")
    elif (repo_path / ".eslintrc.json").exists() or (repo_path / "eslint.config.js").exists():
        constraints.append("Linter: eslint")
    elif (repo_path / "clippy.toml").exists():
        constraints.append("Linter: clippy")

    return constraints


# ---------------------------------------------------------------------------
# HiveContext — the native context provider
# ---------------------------------------------------------------------------

class HiveContext:
    """Native codebase context generator.

    Drop-in baseline for when Prelude is not installed.
    Implements the same interface agents expect from PreludeContext:
      - compact(max_tokens) → str
      - get_constraints() → list[str]
      - summary() → dict
      - available → bool
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.resolve()
        self.context_path = self.repo_path / ".honeymoon" / "context.json"
        self._data: dict[str, Any] | None = None

    @property
    def available(self) -> bool:
        return True  # Always available — no external deps

    @property
    def context_exists(self) -> bool:
        return self.context_path.exists()

    @property
    def cli_available(self) -> bool:
        return False  # Not a CLI tool

    def generate(self) -> dict[str, Any]:
        """Analyze the repo and generate context. Writes to .honeymoon/context.json."""
        logger.info("[HIVE-CTX] Generating native context...")

        index = build_index(self.repo_path)
        stack = _detect_stack(self.repo_path, index)
        graph = _build_import_graph(index)
        constraints = _infer_constraints(self.repo_path)

        # Build file summary (top files by symbol count)
        file_summary = {}
        sorted_files = sorted(
            index.files.values(),
            key=lambda f: (f.is_key, len(f.symbols)),
            reverse=True,
        )
        for entry in sorted_files[:100]:
            file_summary[entry.path] = {
                "symbols": entry.symbols[:20],
                "imports": entry.imports[:10],
                "is_test": entry.is_test,
            }

        self._data = {
            "version": "1.0.0",
            "generator": "honeymoon-native",
            "stack": stack,
            "files": file_summary,
            "import_graph": graph,
            "constraints": constraints,
            "stats": {
                "total_files": index.total_files,
                "languages": index.languages,
            },
        }

        # Persist
        self.context_path.parent.mkdir(parents=True, exist_ok=True)
        self.context_path.write_text(json.dumps(self._data, indent=2))
        logger.info(f"[HIVE-CTX] Context written ({index.total_files} files indexed)")

        return self._data

    def load(self) -> dict[str, Any]:
        """Load existing context from disk, or generate if missing."""
        if self._data is not None:
            return self._data

        if self.context_path.exists():
            try:
                self._data = json.loads(self.context_path.read_text())
                return self._data
            except (json.JSONDecodeError, OSError):
                pass

        return self.generate()

    def refresh(self) -> bool:
        """Regenerate context."""
        self.generate()
        return True

    def compact(self, max_tokens: int = 800, **kwargs) -> str:
        """Token-efficient context string for LLM prompt injection.

        Same interface as PreludeContext.compact() so agents
        don't need to know which backend is active.
        """
        data = self.load()
        stack = data.get("stack", {})
        constraints = data.get("constraints", [])
        stats = data.get("stats", {})
        files = data.get("files", {})

        parts = []

        # Stack
        lang = stack.get("language", "unknown")
        fw = stack.get("framework")
        pm = stack.get("package_manager")
        tf = stack.get("test_framework")
        stack_line = f"[stack] {lang}"
        if fw:
            stack_line += f" / {fw}"
        if pm:
            stack_line += f" ({pm})"
        if tf:
            stack_line += f" | tests: {tf}"
        parts.append(stack_line)

        # Stats
        langs = stats.get("languages", {})
        if langs:
            lang_str = ", ".join(f"{k}:{v}" for k, v in sorted(langs.items(), key=lambda x: -x[1]))
            parts.append(f"[files] {stats.get('total_files', 0)} total | {lang_str}")

        # Constraints
        if constraints:
            parts.append("[constraints] " + " | ".join(constraints))

        # Key files (non-test, most symbols)
        key_files = [
            (path, info) for path, info in files.items()
            if not info.get("is_test") and info.get("symbols")
        ]
        key_files.sort(key=lambda x: len(x[1]["symbols"]), reverse=True)

        # Estimate tokens — ~4 chars per token
        current_chars = sum(len(p) for p in parts)
        budget_chars = max_tokens * 4

        if key_files and current_chars < budget_chars:
            parts.append("[key files]")
            for path, info in key_files[:15]:
                syms = ", ".join(info["symbols"][:8])
                line = f"  {path}: {syms}"
                if current_chars + len(line) > budget_chars:
                    break
                parts.append(line)
                current_chars += len(line)

        return "\n".join(parts)

    def get_constraints(self) -> list[str]:
        """Return inferred constraints."""
        data = self.load()
        return data.get("constraints", [])

    def get_decisions(self) -> list[str]:
        """Native context doesn't track decisions — return empty."""
        return []

    def summary(self) -> dict[str, Any]:
        """Summary for status display."""
        data = self.load()
        return {
            "available": True,
            "cli_installed": False,
            "cli_version": None,
            "context_dir_exists": self.context_exists,
            "generator": "honeymoon-native",
            "files": list(data.get("files", {}).keys())[:10],
            "decisions_count": 0,
            "project_name": self.repo_path.name,
            "language": data.get("stack", {}).get("language", "unknown"),
        }

    def init(self, force: bool = False) -> bool:
        """Generate context (compat with PreludeContext.init)."""
        self.generate()
        return True

    def update(self, **kwargs) -> bool:
        """Regenerate context (compat with PreludeContext.update)."""
        return self.refresh()

    def export(self) -> str:
        """Export full context as readable string."""
        return self.compact(max_tokens=4000)

    def check_version(self, min_version: str = "0.0.0") -> bool:
        """Always passes — no external version to check."""
        return True

    def query(self, topic: str = "", **kwargs) -> str:
        """Native context doesn't support queries — return compact."""
        return self.compact()
