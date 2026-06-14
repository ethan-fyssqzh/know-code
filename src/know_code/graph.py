from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import GraphFact


def dedupe_facts(facts: Iterable[GraphFact]) -> list[GraphFact]:
    by_id: dict[str, GraphFact] = {}
    for fact in facts:
        if fact.id is None:
            continue
        existing = by_id.get(fact.id)
        if existing is None or fact.confidence > existing.confidence:
            by_id[fact.id] = fact
    return sorted(by_id.values(), key=lambda item: (item.subject, item.predicate, item.object, item.id or ""))


def write_ndjson(path: Path, facts: Iterable[GraphFact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for fact in dedupe_facts(facts):
            handle.write(json.dumps(fact.to_dict(), sort_keys=True, ensure_ascii=True))
            handle.write("\n")


def read_ndjson(path: Path) -> list[GraphFact]:
    facts: list[GraphFact] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            facts.append(GraphFact.from_dict(json.loads(line)))
    return facts


def diff_facts(old: Iterable[GraphFact], new: Iterable[GraphFact]) -> dict[str, list[GraphFact]]:
    old_by_id = {fact.id: fact for fact in old if fact.id is not None}
    new_by_id = {fact.id: fact for fact in new if fact.id is not None}

    added = [new_by_id[key] for key in sorted(set(new_by_id) - set(old_by_id))]
    removed = [old_by_id[key] for key in sorted(set(old_by_id) - set(new_by_id))]
    changed = [
        new_by_id[key]
        for key in sorted(set(old_by_id) & set(new_by_id))
        if old_by_id[key].content_fingerprint() != new_by_id[key].content_fingerprint()
    ]
    return {"added": added, "removed": removed, "changed": changed}


def facts_for_operation(facts: Iterable[GraphFact], operation: str) -> list[GraphFact]:
    needle = operation if operation.startswith("operation:") else f"operation:{operation}"
    return [
        fact
        for fact in facts
        if fact.subject == needle or fact.object == needle or fact.attributes.get("operation") == needle
    ]

