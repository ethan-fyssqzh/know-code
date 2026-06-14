from __future__ import annotations

from pathlib import Path

from .extractors import default_extractors, load_custom_extractors
from .graph import dedupe_facts
from .models import GraphFact
from .repo import RepoContext


def scan_repositories(repo_paths: list[Path], adapter_config: Path | None = None) -> list[GraphFact]:
    extractors = default_extractors() + load_custom_extractors(adapter_config)
    facts: list[GraphFact] = []
    for path in repo_paths:
        context = RepoContext.from_path(path)
        for extractor in extractors:
            facts.extend(extractor.extract(context))
    return dedupe_facts(facts)

