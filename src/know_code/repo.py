from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


IGNORED_DIRS = {
    ".git",
    ".gradle",
    ".idea",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
}


@dataclass(frozen=True)
class RepoContext:
    root: Path
    name: str
    commit: str

    @classmethod
    def from_path(cls, path: Path) -> "RepoContext":
        root = path.resolve()
        return cls(root=root, name=root.name, commit=read_git_commit(root))

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()


def read_git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"
    value = result.stdout.strip()
    return value if value else "working-tree"


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except UnicodeDecodeError:
            return None
