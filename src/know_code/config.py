from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import textwrap


DEFAULT_CONFIG = ".know-code.yml"
DEFAULT_OUTPUT = ".know-code"


@dataclass(frozen=True)
class WorkspaceConfig:
    repos: list[Path]
    output: Path = Path(DEFAULT_OUTPUT)
    strategy: str = "hierarchical"
    min_nodes: int = 4
    adapter_config: Path | None = None
    title: str = "Know Code Workspace"
    ignore: list[str] = field(default_factory=list)


def default_config_text(repos: list[Path] | None = None, base: Path | None = None) -> str:
    repo_entries = repos_config_text(repos or [Path(".")], base or Path.cwd())
    return f"""# Know Code workspace configuration
output: .know-code
strategy: hierarchical
min_nodes: 4
title: Know Code Workspace

repos:
{repo_entries}

# adapter_config: examples/framework-adapters.json
# ignore:
#   - node_modules
#   - build
#   - dist
"""


def write_default_config(path: Path, repos: list[Path] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_text(repos, path.parent.resolve()), encoding="utf-8")


def repos_config_text(repos: list[Path], base: Path) -> str:
    lines: list[str] = []
    for repo in repos:
        resolved = repo.expanduser().resolve()
        try:
            display_path = resolved.relative_to(base).as_posix()
        except ValueError:
            display_path = str(resolved)
        if display_path == "":
            display_path = "."
        lines.append(f"  - path: {display_path}")
        lines.append(f"    name: {resolved.name or 'repo'}")
    return "\n".join(lines)


def load_workspace_config(path: Path) -> WorkspaceConfig:
    data = parse_config(path)
    base = path.parent.resolve()
    repos = parse_repos(data.get("repos", []), base)
    output = resolve_path(str(data.get("output", DEFAULT_OUTPUT)), base)
    adapter_config = data.get("adapter_config") or data.get("adapter-config")
    return WorkspaceConfig(
        repos=repos,
        output=output,
        strategy=str(data.get("strategy", "hierarchical")),
        min_nodes=int(data.get("min_nodes", data.get("min-nodes", 4))),
        adapter_config=resolve_path(str(adapter_config), base) if adapter_config else None,
        title=str(data.get("title", "Know Code Workspace")),
        ignore=[str(item) for item in data.get("ignore", [])],
    )


def parse_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return dict(json.loads(text))
    return parse_simple_yaml(text)


def parse_repos(value: Any, base: Path) -> list[Path]:
    repos: list[Path] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                raw_path = item.get("path")
            else:
                raw_path = item
            if raw_path:
                repos.append(resolve_path(str(raw_path), base))
    if not repos:
        repos.append(base)
    return repos


def resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def parse_simple_yaml(text: str) -> dict[str, Any]:
    text = textwrap.dedent(text)
    data: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = strip_comment(lines[index]).rstrip()
        index += 1
        if not raw.strip():
            continue
        if raw.startswith(" ") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = parse_scalar(value)
            continue
        block, index = parse_block(lines, index)
        data[key] = block
    return data


def parse_block(lines: list[str], index: int) -> tuple[Any, int]:
    items: list[Any] = []
    mapping: dict[str, Any] = {}
    while index < len(lines):
        raw_line = strip_comment(lines[index]).rstrip()
        if not raw_line.strip():
            index += 1
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            break
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            item_text = stripped[2:].strip()
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                item = {key.strip(): parse_scalar(value.strip())}
                index += 1
                while index < len(lines):
                    child = strip_comment(lines[index]).rstrip()
                    child_indent = len(child) - len(child.lstrip(" "))
                    if not child.strip():
                        index += 1
                        continue
                    if child_indent <= indent:
                        break
                    child_text = child.strip()
                    if ":" not in child_text:
                        break
                    child_key, child_value = child_text.split(":", 1)
                    item[child_key.strip()] = parse_scalar(child_value.strip())
                    index += 1
                items.append(item)
            else:
                items.append(parse_scalar(item_text))
                index += 1
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
            mapping[key.strip()] = parse_scalar(value.strip())
            index += 1
        else:
            index += 1
    return (items if items else mapping), index


def strip_comment(line: str) -> str:
    in_quote: str | None = None
    for index, char in enumerate(line):
        if char in {"'", '"'}:
            in_quote = None if in_quote == char else char
        if char == "#" and in_quote is None:
            return line[:index]
    return line


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.isdigit():
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value
