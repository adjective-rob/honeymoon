"""
GLITCHLAB Repo Indexer — File Discovery

Walks the repository and builds a lightweight file map so agents
can reference real paths instead of hallucinating them.

Produces:
  - File tree (filtered, no noise)
  - Module/crate/package structure
  - Language detection
  - Key file identification (configs, entry points, tests)

The index is cheap to build and injected into planner context.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

# Directories to always skip
SKIP_DIRS = {
    ".git", ".glitchlab", ".context", ".venv", "venv", "env",
    "node_modules", "target", "dist", "build", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".next", ".nuxt", "coverage", ".cargo", "vendor",
    ".idea", ".vscode", "out", "bin", "obj",
}

# File extensions we care about
CODE_EXTENSIONS = {
    ".rs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".swift", ".kt",
    ".toml", ".yaml", ".yml", ".json", ".md", ".txt",
    ".sql", ".graphql", ".proto", ".sh", ".bash",
    ".css", ".scss", ".html", ".svelte", ".vue",
}

# Key files that indicate project structure
KEY_FILES = {
    "Cargo.toml", "package.json", "pyproject.toml", "setup.py",
    "go.mod", "Makefile", "Dockerfile", "docker-compose.yml",
    "tsconfig.json", "vite.config.ts", "next.config.js",
    ".env.example", "README.md", "CHANGELOG.md",
    "justfile", "Taskfile.yml", "flake.nix",
}


@dataclass
class FileEntry:
    path: str
    extension: str
    size_bytes: int
    is_test: bool = False
    is_key_file: bool = False


@dataclass
class RepoIndex:
    """Lightweight index of a repository's file structure."""
    root: str
    total_files: int = 0
    languages: dict[str, int] = field(default_factory=dict)  # ext → count
    files: list[FileEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    key_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    crates: list[str] = field(default_factory=list)  # Rust workspace members
    packages: list[str] = field(default_factory=list)  # Node workspace packages

    def to_agent_context(self, max_files: int = 300) -> str:
        """
        Format the index as a string suitable for injecting into agent context.
        Prioritizes structure over exhaustive listing.
        """
        parts = []
        parts.append(f"=== REPO INDEX ({self.total_files} files) ===\n")

        # Language breakdown
        if self.languages:
            lang_str = ", ".join(
                f"{ext}: {count}" for ext, count
                in sorted(self.languages.items(), key=lambda x: -x[1])[:10]
            )
            parts.append(f"Languages: {lang_str}\n")

        # Crates / packages
        if self.crates:
            parts.append(f"Rust crates: {', '.join(self.crates)}\n")
        if self.packages:
            parts.append(f"Packages: {', '.join(self.packages)}\n")

        # Key files
        if self.key_files:
            parts.append(f"Key files: {', '.join(self.key_files)}\n")

        # Directory structure (top 2 levels)
        if self.directories:
            parts.append("\nDirectory structure:")
            for d in self.directories[:50]:
                depth = d.count("/")
                indent = "  " * depth
                name = d.split("/")[-1] if "/" in d else d
                parts.append(f"  {indent}{name}/")

        # File listing (truncated)
        parts.append(f"\nSource files ({min(len(self.files), max_files)} shown):")
        for entry in self.files[:max_files]:
            markers = []
            if entry.is_test:
                markers.append("test")
            if entry.is_key_file:
                markers.append("key")
            suffix = f"  [{', '.join(markers)}]" if markers else ""
            parts.append(f"  {entry.path}{suffix}")

        if len(self.files) > max_files:
            parts.append(f"  ... and {len(self.files) - max_files} more files")

        return "\n".join(parts)


def _is_test_file(path: str) -> bool:
    """Heuristic: is this a test file?"""
    lower = path.lower()
    parts = lower.split("/")
    name = parts[-1] if parts else ""

    return (
        "test" in name
        or "spec" in name
        or "tests/" in lower
        or "test/" in lower
        or "__tests__/" in lower
        or "spec/" in lower
        or name.startswith("test_")
        or name.endswith("_test.rs")
        or name.endswith("_test.go")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".test.js")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.js")
    )


def _detect_rust_crates(repo_path: Path) -> list[str]:
    """Detect Rust workspace members from root Cargo.toml."""
    cargo_toml = repo_path / "Cargo.toml"
    if not cargo_toml.exists():
        return []

    try:
        content = cargo_toml.read_text()
        # Simple parse — look for [workspace] members
        in_members = False
        crates = []
        for line in content.splitlines():
            if "members" in line and "[" in line:
                in_members = True
                # Handle inline: members = ["a", "b"]
                if "]" in line:
                    import re
                    crates.extend(re.findall(r'"([^"]+)"', line))
                    in_members = False
                continue
            if in_members:
                if "]" in line:
                    in_members = False
                import re
                found = re.findall(r'"([^"]+)"', line)
                crates.extend(found)

        # Also check for individual crate Cargo.tomls
        if not crates:
            for ct in repo_path.rglob("Cargo.toml"):
                rel = str(ct.parent.relative_to(repo_path))
                if rel != "." and "target" not in rel:
                    crates.append(rel)

        return sorted(set(crates))
    except Exception:
        return []


def _detect_node_packages(repo_path: Path) -> list[str]:
    """Detect Node workspace packages."""
    pkg_json = repo_path / "package.json"
    if not pkg_json.exists():
        return []

    try:
        import json
        data = json.loads(pkg_json.read_text())
        workspaces = data.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        return sorted(workspaces)
    except Exception:
        return []


def build_index(repo_path: Path, max_depth: int = 8) -> RepoIndex:
    """
    Walk the repository and build a lightweight index.

    Uses git ls-files if available (respects .gitignore),
    falls back to filesystem walk.
    """
    repo_path = repo_path.resolve()
    index = RepoIndex(root=str(repo_path))

    # Try git ls-files first (fast, respects .gitignore)
    files = _git_ls_files(repo_path)
    if not files:
        files = _walk_files(repo_path, max_depth)

    directories = set()

    for rel_path in files:
        # Skip noise
        parts = rel_path.split("/")
        if any(p in SKIP_DIRS for p in parts):
            continue

        ext = ""
        if "." in parts[-1]:
            ext = "." + parts[-1].rsplit(".", 1)[-1]

        # Only index code files
        if ext not in CODE_EXTENSIONS and parts[-1] not in KEY_FILES:
            continue

        full = repo_path / rel_path
        try:
            size = full.stat().st_size if full.exists() else 0
        except OSError:
            size = 0

        is_test = _is_test_file(rel_path)
        is_key = parts[-1] in KEY_FILES

        entry = FileEntry(
            path=rel_path,
            extension=ext,
            size_bytes=size,
            is_test=is_test,
            is_key_file=is_key,
        )
        index.files.append(entry)

        if is_key:
            index.key_files.append(rel_path)
        if is_test:
            index.test_files.append(rel_path)

        # Track language
        if ext in CODE_EXTENSIONS and ext not in {".toml", ".yaml", ".yml", ".json", ".md", ".txt"}:
            index.languages[ext] = index.languages.get(ext, 0) + 1

        # Track directories (first 2 levels)
        for i in range(1, min(len(parts), 3)):
            directories.add("/".join(parts[:i]))

    index.total_files = len(index.files)
    index.directories = sorted(directories)

    # Detect project structure
    index.crates = _detect_rust_crates(repo_path)
    index.packages = _detect_node_packages(repo_path)

    logger.info(
        f"[INDEX] Indexed {index.total_files} files, "
        f"{len(index.directories)} dirs, "
        f"{len(index.languages)} languages"
    )

    return index


def _git_ls_files(repo_path: Path) -> list[str]:
    """Use git ls-files for fast, .gitignore-aware listing."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except Exception:
        pass
    return []


def _walk_files(repo_path: Path, max_depth: int = 8) -> list[str]:
    """Fallback: walk filesystem manually."""
    files = []
    for item in repo_path.rglob("*"):
        if item.is_file():
            rel = str(item.relative_to(repo_path))
            parts = rel.split("/")
            if len(parts) <= max_depth and not any(p in SKIP_DIRS for p in parts):
                files.append(rel)
    return files
