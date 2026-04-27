"""Tests for the native HiveContext — Prelude-free codebase understanding."""

import json
from pathlib import Path

from honeymoon.hive_context import (
    HiveContext,
    _detect_stack,
    _build_import_graph,
    _infer_constraints,
)
from honeymoon.indexer import build_index


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a fake repo with given files."""
    import subprocess
    (tmp_path / ".git").mkdir()
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    # Init git so build_index works
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    return tmp_path


def test_detect_stack_python(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\ndependencies=["fastapi"]',
        "app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    })
    index = build_index(repo)
    stack = _detect_stack(repo, index)
    assert stack["language"] == "python"
    assert stack["framework"] == "FastAPI"
    assert stack["package_manager"] == "pip"


def test_detect_stack_rust(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "Cargo.toml": '[package]\nedition = "2021"\n[dependencies]\naxum = "0.7"',
        "src/main.rs": "fn main() {}\n",
    })
    index = build_index(repo)
    stack = _detect_stack(repo, index)
    assert stack["language"] == "rust"
    assert stack["package_manager"] == "cargo"
    assert stack["framework"] == "Axum"


def test_detect_stack_typescript(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "package.json": '{"dependencies":{"react":"^18"}, "devDependencies":{"jest":"^29"}}',
        "src/App.tsx": "export default function App() { return <div/>; }\n",
    })
    index = build_index(repo)
    stack = _detect_stack(repo, index)
    assert stack["language"] == "typescript"
    assert stack["framework"] == "React"
    assert stack["test_framework"] == "jest"


def test_infer_constraints_python(tmp_path: Path):
    _make_repo(tmp_path, {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"',
        "ruff.toml": "",
    })
    constraints = _infer_constraints(tmp_path)
    assert "Python >=3.11" in constraints
    assert "Linter: ruff" in constraints


def test_infer_constraints_node(tmp_path: Path):
    _make_repo(tmp_path, {
        "package.json": '{"engines":{"node":">=18"}}',
    })
    constraints = _infer_constraints(tmp_path)
    assert "Node >=18" in constraints


def test_build_import_graph(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "honeymoon/__init__.py": "",
        "honeymoon/router.py": "class Router: pass\n",
        "honeymoon/controller.py": "from honeymoon.router import Router\n",
    })
    index = build_index(repo)
    graph = _build_import_graph(index)
    assert "honeymoon/controller.py" in graph
    assert "honeymoon/router.py" in graph["honeymoon/controller.py"]


def test_hive_context_generate(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"',
        "app.py": "def main():\n    pass\n",
    })
    ctx = HiveContext(repo)
    data = ctx.generate()

    assert data["generator"] == "honeymoon-native"
    assert data["stack"]["language"] == "python"
    assert ctx.context_path.exists()


def test_hive_context_load_from_disk(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "app.py": "def hello(): pass\n",
    })
    ctx1 = HiveContext(repo)
    ctx1.generate()

    ctx2 = HiveContext(repo)
    data = ctx2.load()
    assert data["generator"] == "honeymoon-native"


def test_hive_context_compact(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\ndependencies=["fastapi"]',
        "app.py": "class MyApp:\n    pass\ndef run():\n    pass\n",
    })
    ctx = HiveContext(repo)
    compact = ctx.compact(max_tokens=200)

    assert "[stack]" in compact
    assert "python" in compact
    assert "[files]" in compact


def test_hive_context_get_constraints(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"',
    })
    ctx = HiveContext(repo)
    constraints = ctx.get_constraints()
    assert "Python >=3.11" in constraints


def test_hive_context_available(tmp_path: Path):
    ctx = HiveContext(tmp_path)
    assert ctx.available is True
    assert ctx.cli_available is False


def test_hive_context_summary(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        "app.py": "def main(): pass\n",
    })
    ctx = HiveContext(repo)
    ctx.generate()
    summary = ctx.summary()
    assert summary["available"] is True
    assert summary["generator"] == "honeymoon-native"


def test_hive_context_compat_methods(tmp_path: Path):
    """Verify all PreludeContext-compatible methods exist and work."""
    repo = _make_repo(tmp_path, {
        "app.py": "x = 1\n",
    })
    ctx = HiveContext(repo)
    assert ctx.init() is True
    assert ctx.refresh() is True
    assert ctx.check_version() is True
    assert ctx.get_decisions() == []
    assert isinstance(ctx.export(), str)
    assert isinstance(ctx.query(), str)
