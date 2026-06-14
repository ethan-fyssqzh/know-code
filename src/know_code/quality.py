from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from typing import Any

from .models import GraphFact


@dataclass(frozen=True)
class OperationQuality:
    total_operations: int
    operations_with_provider_and_caller: int
    call_only_operations: int
    provider_only_operations: int
    provider_match_rate: float
    caller_match_rate: float
    top_call_only: list[tuple[str, int, str]]
    top_provider_only: list[tuple[str, int, str]]
    top_connected: list[tuple[str, int, int]]
    predicate_counts: dict[str, int]
    entity_type_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_operations": self.total_operations,
            "operations_with_provider_and_caller": self.operations_with_provider_and_caller,
            "call_only_operations": self.call_only_operations,
            "provider_only_operations": self.provider_only_operations,
            "provider_match_rate": self.provider_match_rate,
            "caller_match_rate": self.caller_match_rate,
            "top_call_only": [
                {"operation": op, "callers": count, "sample": sample}
                for op, count, sample in self.top_call_only
            ],
            "top_provider_only": [
                {"operation": op, "providers": count, "sample": sample}
                for op, count, sample in self.top_provider_only
            ],
            "top_connected": [
                {"operation": op, "callers": callers, "providers": providers}
                for op, callers, providers in self.top_connected
            ],
            "predicate_counts": self.predicate_counts,
            "entity_type_counts": self.entity_type_counts,
        }


def analyze_quality(facts: list[GraphFact]) -> OperationQuality:
    providers: dict[str, list[GraphFact]] = defaultdict(list)
    callers: dict[str, list[GraphFact]] = defaultdict(list)
    predicate_counts = Counter(fact.predicate for fact in facts)
    entity_types = Counter()

    for fact in facts:
        entity_types[entity_type(fact.subject)] += 1
        entity_types[entity_type(fact.object)] += 1
        if not fact.object.startswith("operation:"):
            continue
        operation = fact.object.removeprefix("operation:")
        if fact.predicate == "provides_operation":
            providers[operation].append(fact)
        elif fact.predicate == "calls_operation":
            callers[operation].append(fact)

    all_operations = set(providers) | set(callers)
    with_both = [op for op in all_operations if providers[op] and callers[op]]
    call_only = [op for op in all_operations if callers[op] and not providers[op]]
    provider_only = [op for op in all_operations if providers[op] and not callers[op]]

    total_called = sum(1 for op in all_operations if callers[op])
    total_provided = sum(1 for op in all_operations if providers[op])
    provider_match_rate = len(with_both) / total_called if total_called else 1.0
    caller_match_rate = len(with_both) / total_provided if total_provided else 1.0

    return OperationQuality(
        total_operations=len(all_operations),
        operations_with_provider_and_caller=len(with_both),
        call_only_operations=len(call_only),
        provider_only_operations=len(provider_only),
        provider_match_rate=provider_match_rate,
        caller_match_rate=caller_match_rate,
        top_call_only=[
            (op, len(callers[op]), sample_location(callers[op][0]))
            for op in sorted(call_only, key=lambda item: len(callers[item]), reverse=True)[:20]
        ],
        top_provider_only=[
            (op, len(providers[op]), sample_location(providers[op][0]))
            for op in sorted(provider_only, key=lambda item: len(providers[item]), reverse=True)[:20]
        ],
        top_connected=[
            (op, len(callers[op]), len(providers[op]))
            for op in sorted(with_both, key=lambda item: len(callers[item]) + len(providers[item]), reverse=True)[:20]
        ],
        predicate_counts=dict(sorted(predicate_counts.items())),
        entity_type_counts=dict(sorted(entity_types.items())),
    )


def render_quality_report(quality: OperationQuality) -> str:
    lines = [
        "Graph Quality",
        "=============",
        "",
        f"Operations: {quality.total_operations}",
        f"Provider/caller matched: {quality.operations_with_provider_and_caller}",
        f"Call-only operations: {quality.call_only_operations}",
        f"Provider-only operations: {quality.provider_only_operations}",
        f"Provider match rate: {quality.provider_match_rate:.1%}",
        f"Caller match rate: {quality.caller_match_rate:.1%}",
        "",
        "Predicates:",
    ]
    for predicate, count in sorted(quality.predicate_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {predicate}: {count}")
    lines.extend(["", "Entity types:"])
    for entity, count in sorted(quality.entity_type_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {entity}: {count}")

    lines.extend(["", "Top connected operations:"])
    for op, callers, providers in quality.top_connected:
        lines.append(f"- {op}: callers={callers}, providers={providers}")

    lines.extend(["", "Top call-only operations:"])
    for op, count, sample in quality.top_call_only:
        lines.append(f"- {op}: callers={count}, sample={sample}")

    lines.extend(["", "Top provider-only operations:"])
    for op, count, sample in quality.top_provider_only:
        lines.append(f"- {op}: providers={count}, sample={sample}")
    return "\n".join(lines)


def quality_json(quality: OperationQuality) -> str:
    return json.dumps(quality.to_dict(), indent=2, sort_keys=True)


def entity_type(entity: str) -> str:
    if entity.startswith("repo:") and ":file:" in entity:
        return "file"
    if ":" not in entity:
        return "entity"
    return entity.split(":", 1)[0]


def sample_location(fact: GraphFact) -> str:
    if not fact.evidence:
        return fact.repo
    evidence = fact.evidence[0]
    return f"{evidence.file}:{evidence.line}"
