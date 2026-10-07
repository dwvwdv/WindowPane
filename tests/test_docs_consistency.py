"""Docs ↔ code consistency guards (rules in AGENTS.md, section 文件維護).

Docs that restate the code (paths, file names, versions) drift silently when the code moves on.
These checks make that drift fail CI instead. Run from the repository root:
``python3 -m pytest tests``. Standard library + pytest only.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Codex reads at most 32 KiB of AGENTS.md (project_doc_max_bytes) and silently drops the rest;
# Claude loads the whole file into every session. Keep 2 KiB of headroom; details go to docs/.
AGENTS_MD_MAX_BYTES = 30 * 1024

# Documents that describe the current state. docs/changelog.md is history: it may name files
# that no longer exist, so it is not scanned for paths.
CURRENT_STATE_DOCS = [
    "AGENTS.md",
    "README.md",
    "docs/architecture.md",
    "docs/ui-conventions.md",
]

# Paths in docs are written from the repository root, relative to the document, or as the short
# form inside a package or directory the sentence already names (`repositories/base.py`,
# `offbeat.css`, `memory.py`, `seeds.py`, `seed.sql`).
PATH_ROOTS = [
    "",
    "supabase/",
    "worldpane-server/",
    "worldpane-server/src/",
    "worldpane-server/src/worldpane_server/",
    "worldpane-server/src/worldpane_server/static/",
    "worldpane-server/src/worldpane_server/repositories/",
    "worldpane-server/scripts/",
    "worldpane-core/",
    "worldpane-core/src/",
    "worldpane-core/src/worldpane_core/",
    "worldpane-core/scripts/",
    "worldpane-core/tests/",
    "worldpane-server/tests/",
    ".github/workflows/",
]

PACKAGES = {
    "core": ("worldpane-core", "worldpane-core/src/worldpane_core/__init__.py"),
    "server": ("worldpane-server", "worldpane-server/src/worldpane_server/__init__.py"),
}

FILE_SUFFIXES = (".py", ".md", ".sql", ".yml", ".yaml", ".html", ".css", ".json", ".sh", ".toml")
LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE = re.compile(r"`([^`\n]+)`")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_agents_md_fits_what_codex_reads():
    size = (ROOT / "AGENTS.md").stat().st_size
    assert size <= AGENTS_MD_MAX_BYTES, (
        f"AGENTS.md is {size} bytes; Codex only reads the first 32 KiB. Move details to the docs/ "
        "file its 改 X 前先讀 Y table points to and keep a link here."
    )


def test_claude_md_only_imports_agents_md():
    # Two files each holding some rules is how they drifted apart before; Claude Code reads
    # CLAUDE.md, Codex reads AGENTS.md, so CLAUDE.md just imports the one source.
    assert _read("CLAUDE.md").strip() == "@AGENTS.md"


def _exists(candidate: str, doc: Path) -> bool:
    candidate = candidate.split("#", 1)[0].rstrip("/")
    if not candidate:
        return True
    if (doc.parent / candidate).exists():
        return True
    return any((ROOT / root / candidate).exists() for root in PATH_ROOTS)


def _mentioned_paths(text: str) -> set[str]:
    found = set()
    for target in LINK.findall(text):
        if not re.match(r"^(https?:|mailto:|#)", target):
            found.add(target)
    for code in CODE.findall(text):
        code = code.strip()
        # Only things that look like a file or directory in this repo: no commands, globs,
        # placeholders, URLs or API routes.
        if any(ch in code for ch in " *<>{}$=|") or code.startswith(("/", "@", "http", "-", "~")):
            continue
        if code.endswith(FILE_SUFFIXES) or code.endswith("/"):
            found.add(code)
    return found


@pytest.mark.parametrize("doc", CURRENT_STATE_DOCS)
def test_paths_mentioned_in_docs_exist(doc):
    path = ROOT / doc
    missing = sorted(p for p in _mentioned_paths(path.read_text(encoding="utf-8")) if not _exists(p, path))
    assert not missing, f"{doc} mentions paths that do not exist: {missing}"


def _versions(package: str) -> tuple[str, str]:
    directory, init = PACKAGES[package]
    project = tomllib.loads(_read(f"{directory}/pyproject.toml"))["project"]["version"]
    match = re.search(r'^__version__ = "([^"]+)"', _read(init), re.M)
    assert match, f"{init} has no __version__"
    return project, match.group(1)


@pytest.mark.parametrize("package", sorted(PACKAGES))
def test_package_version_is_written_once(package):
    project, module = _versions(package)
    assert project == module, f"{package}: pyproject.toml says {project}, __version__ says {module}"


@pytest.mark.parametrize("package", sorted(PACKAGES))
def test_current_version_has_a_changelog_entry(package):
    version, _ = _versions(package)
    headings = re.findall(r"^### (.+?) \(\d{4}-\d{2}-\d{2}\)$", _read("docs/changelog.md"), re.M)
    assert any(re.search(rf"\b{package} {re.escape(version)}\b", h) for h in headings), (
        f"docs/changelog.md has no entry for {package} {version}; add one when bumping the version"
    )
