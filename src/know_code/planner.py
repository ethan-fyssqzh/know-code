from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

from .models import GraphFact


@dataclass(frozen=True)
class OperationImpact:
    operation: str
    providers: list[GraphFact]
    callers: list[GraphFact]
    api_mappings: list[GraphFact]
    rpc_methods: list[GraphFact]
    events: list[GraphFact]


def generate_plan(prd_path: Path, facts: list[GraphFact]) -> str:
    prd = prd_path.read_text(encoding="utf-8")
    operations = match_operations(prd, facts)
    api_hits = match_apis(prd, facts)
    rpc_hits = match_rpcs(prd, facts)

    lines: list[str] = [
        "# Technical Plan",
        "",
        f"Source PRD: `{prd_path}`",
        "",
        "## Summary",
        "",
    ]
    if operations:
        lines.append(f"- Matched {len(operations)} operation candidate(s).")
    if api_hits:
        lines.append(f"- Matched {len(api_hits)} API candidate(s).")
    if rpc_hits:
        lines.append(f"- Matched {len(rpc_hits)} RPC candidate(s).")
    if not operations and not api_hits and not rpc_hits:
        lines.append("- No strong graph match was found. Extend framework adapters or add contract extraction.")

    lines.extend(["", "## Repository Impact", ""])
    repo_reasons = repository_reasons(operations, api_hits, rpc_hits)
    if not repo_reasons:
        lines.append("- Unknown. No repository could be mapped from current graph facts.")
    else:
        for repo, reasons in sorted(repo_reasons.items()):
            lines.append(f"### {repo}")
            for reason in sorted(reasons):
                lines.append(f"- {reason}")
            lines.append("")

    if operations:
        lines.extend(["## Matched Operations", ""])
        for impact in operations:
            lines.append(f"### `{impact.operation}`")
            append_fact_group(lines, "Providers", impact.providers)
            append_fact_group(lines, "Callers", impact.callers)
            append_fact_group(lines, "API mappings", impact.api_mappings)
            append_fact_group(lines, "RPC methods", impact.rpc_methods)
            append_fact_group(lines, "Events", impact.events)
            lines.append("")

    if api_hits:
        lines.extend(["## Matched APIs", ""])
        append_fact_group(lines, "API facts", api_hits)
        lines.append("")

    if rpc_hits:
        lines.extend(["## Matched RPCs", ""])
        append_fact_group(lines, "RPC facts", rpc_hits)
        lines.append("")

    lines.extend(
        [
            "## Suggested Execution Order",
            "",
            "1. Confirm product ambiguities and acceptance criteria.",
            "2. Update or add contracts first: API, RPC, event schema, or framework operation mapping.",
            "3. Modify provider repositories that own the matched operation.",
            "4. Modify client repositories that call the operation or expose matching screens.",
            "5. Verify downstream event consumers and compatibility.",
            "6. Add or update tests around changed contracts and flows.",
            "",
            "## Open Questions",
            "",
            "- Are there hidden framework adapters that the current scan did not load?",
            "- Does the requirement change request/response schemas or only behavior?",
            "- Should old clients remain backward compatible during rollout?",
            "",
        ]
    )
    return "\n".join(lines)


def match_operations(prd: str, facts: list[GraphFact]) -> list[OperationImpact]:
    operation_names = sorted(
        {
            value.removeprefix("operation:")
            for fact in facts
            for value in (fact.subject, fact.object, str(fact.attributes.get("operation", "")))
            if value.startswith("operation:")
        }
    )
    matched = [name for name in operation_names if matches_term(prd, name)]
    impacts: list[OperationImpact] = []
    for name in matched:
        entity = f"operation:{name}"
        related = [fact for fact in facts if fact.subject == entity or fact.object == entity]
        impacts.append(
            OperationImpact(
                operation=name,
                providers=[fact for fact in related if fact.predicate == "provides_operation"],
                callers=[fact for fact in related if fact.predicate == "calls_operation"],
                api_mappings=[fact for fact in related if fact.predicate == "maps_operation_to_api"],
                rpc_methods=[fact for fact in related if fact.predicate in {"provides_rpc", "calls_rpc"}],
                events=[fact for fact in related if fact.predicate in {"emits_event", "consumes_event"}],
            )
        )
    return impacts


def match_apis(prd: str, facts: list[GraphFact]) -> list[GraphFact]:
    return [
        fact
        for fact in facts
        if fact.object.startswith("api:") and matches_term(prd, fact.object.removeprefix("api:"))
    ]


def match_rpcs(prd: str, facts: list[GraphFact]) -> list[GraphFact]:
    return [
        fact
        for fact in facts
        if fact.object.startswith("rpc:") and matches_term(prd, fact.object.removeprefix("rpc:"))
    ]


def matches_term(text: str, term: str) -> bool:
    normalized_text = normalize_for_match(text)
    candidates = {normalize_for_match(term), normalize_for_match(term.replace(".", " "))}
    candidates.update(split_identifier(term))
    return any(candidate and candidate in normalized_text for candidate in candidates)


def split_identifier(value: str) -> set[str]:
    raw_parts = re.split(r"[^A-Za-z0-9]+", value)
    parts: set[str] = set()
    for raw in raw_parts:
        if len(raw) < 4:
            continue
        snake = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw)
        normalized = normalize_for_match(snake)
        if normalized:
            parts.add(normalized)
    return parts


def normalize_for_match(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def repository_reasons(
    operations: list[OperationImpact],
    api_hits: list[GraphFact],
    rpc_hits: list[GraphFact],
) -> dict[str, set[str]]:
    reasons: dict[str, set[str]] = defaultdict(set)
    for impact in operations:
        for fact in impact.providers:
            reasons[fact.repo].add(f"Provides operation `{impact.operation}`.")
        for fact in impact.callers:
            reasons[fact.repo].add(f"Calls operation `{impact.operation}`.")
        for fact in impact.api_mappings:
            reasons[fact.repo].add(f"Maps operation `{impact.operation}` to `{fact.object}`.")
        for fact in impact.events:
            reasons[fact.repo].add(f"Touches event `{fact.object}` via `{fact.predicate}`.")
    for fact in api_hits:
        reasons[fact.repo].add(f"{fact.predicate} `{fact.object}`.")
    for fact in rpc_hits:
        reasons[fact.repo].add(f"{fact.predicate} `{fact.object}`.")
    return reasons


def append_fact_group(lines: list[str], title: str, facts: list[GraphFact]) -> None:
    if not facts:
        lines.append(f"- {title}: none found")
        return
    lines.append(f"- {title}:")
    for fact in facts:
        evidence = fact.evidence[0] if fact.evidence else None
        if evidence is None:
            lines.append(f"  - `{fact.repo}` {fact.predicate} `{fact.object}`")
        else:
            lines.append(
                f"  - `{fact.repo}` {fact.predicate} `{fact.object}` "
                f"({evidence.file}:{evidence.line})"
            )

