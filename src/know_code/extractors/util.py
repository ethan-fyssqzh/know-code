from __future__ import annotations

from pathlib import Path
import re

from know_code.models import Evidence, GraphFact
from know_code.repo import RepoContext


def line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def snippet_at(text: str, start: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()[:240]


def make_evidence(context: RepoContext, path: Path, text: str, start: int) -> Evidence:
    return Evidence(
        repo=context.name,
        commit=context.commit,
        file=context.relative(path),
        line=line_number(text, start),
        snippet=snippet_at(text, start),
    )


def fact(
    context: RepoContext,
    subject: str,
    predicate: str,
    object_: str,
    evidence: Evidence,
    confidence: float,
    source: str,
    attributes: dict | None = None,
    source_version: str = "0.1.0",
) -> GraphFact:
    return GraphFact(
        subject=subject,
        predicate=predicate,
        object=object_,
        evidence=[evidence],
        confidence=confidence,
        source=source,
        source_version=source_version,
        repo=context.name,
        commit=context.commit,
        attributes=attributes or {},
    )


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        return "/" + path
    return path


def normalize_api(method: str, path: str) -> str:
    return f"api:{method.upper()} {normalize_path(path)}"


def normalize_operation(name: str) -> str:
    value = re.sub(r"\s+", ".", name.strip())
    value = value.replace("/", ".").replace("::", ".").replace(":", ".")
    value = value.strip(".")
    return f"operation:{value}"
