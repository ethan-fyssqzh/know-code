from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import json

from .cluster import capability_facts, cluster_facts, clusters_to_json, render_clusters_markdown
from .graph import write_ndjson
from .models import GraphFact
from .quality import analyze_quality, quality_json
from .scanner import scan_repositories
from .visualize import write_visualization


def build_global_graph(
    repos: list[Path],
    out_dir: Path,
    adapter_config: Path | None = None,
    strategy: str = "hierarchical",
    min_nodes: int = 4,
    title: str = "Global Code Capability Graph",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = scan_repositories(repos, adapter_config)

    raw_path = out_dir / "global.facts.ndjson"
    write_ndjson(raw_path, facts)
    global_quality_path = out_dir / "global.quality.json"
    global_quality_path.write_text(quality_json(analyze_quality(facts)), encoding="utf-8")

    repo_outputs = write_repo_outputs(facts, out_dir)
    clusters = cluster_facts(facts, min_nodes=min_nodes, strategy=strategy)

    capabilities_path = out_dir / "global.capabilities.json"
    capabilities_path.write_text(clusters_to_json(clusters), encoding="utf-8")

    capabilities_markdown_path = out_dir / "global.capabilities.md"
    capabilities_markdown_path.write_text(render_clusters_markdown(clusters), encoding="utf-8")

    augmented = facts + capability_facts(clusters, repo="global", commit="derived", base_facts=facts)
    augmented_path = out_dir / "global.capabilities.ndjson"
    write_ndjson(augmented_path, augmented)

    serving_graph_path = out_dir / "global.serving.html"
    write_visualization(augmented, serving_graph_path, title, profile="serving")

    capability_graph_path = out_dir / "global.capability-only.html"
    write_visualization(augmented, capability_graph_path, title, profile="capability")

    manifest_path = out_dir / "manifest.json"
    manifest = {
        "repos": sorted(repo_outputs),
        "counts": {
            "facts": len(facts),
            "augmented_facts": len(augmented),
            "capabilities": len(clusters),
            "predicates": dict(sorted(Counter(fact.predicate for fact in augmented).items())),
            "repo_facts": dict(sorted(Counter(fact.repo for fact in facts).items())),
        },
        "outputs": {
            "raw_facts": str(raw_path),
            "global_quality": str(global_quality_path),
            "augmented_facts": str(augmented_path),
            "capabilities_json": str(capabilities_path),
            "capabilities_markdown": str(capabilities_markdown_path),
            "serving_graph": str(serving_graph_path),
            "capability_graph": str(capability_graph_path),
            "repo_outputs": repo_outputs,
            "manifest": str(manifest_path),
        },
        "strategy": strategy,
        "min_nodes": min_nodes,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def write_repo_outputs(facts: list[GraphFact], out_dir: Path) -> dict[str, dict[str, str]]:
    by_repo: dict[str, list[GraphFact]] = defaultdict(list)
    for fact in facts:
        by_repo[fact.repo].append(fact)

    repo_dir = out_dir / "repos"
    repo_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, str]] = {}
    for repo, repo_facts in sorted(by_repo.items()):
        safe_name = safe_path_part(repo)
        facts_path = repo_dir / f"{safe_name}.facts.ndjson"
        serving_path = repo_dir / f"{safe_name}.serving.html"
        quality_path = repo_dir / f"{safe_name}.quality.json"
        write_ndjson(facts_path, repo_facts)
        write_visualization(repo_facts, serving_path, f"{repo} Repo Serving Graph", profile="serving")
        quality_path.write_text(quality_json(analyze_quality(repo_facts)), encoding="utf-8")
        outputs[repo] = {
            "facts": str(facts_path),
            "serving_graph": str(serving_path),
            "quality": str(quality_path),
        }
    return outputs


def safe_path_part(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value) or "repo"
