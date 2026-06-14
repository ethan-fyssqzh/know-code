from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import re
from typing import Any

from .models import Evidence, GraphFact
from .quality import entity_type, sample_location


EDGE_WEIGHTS = {
    "calls_operation": 6.0,
    "provides_operation": 7.0,
    "maps_operation_to_operation": 5.0,
    "maps_operation_to_api": 4.0,
    "belongs_to_module": 4.0,
    "defines_interface": 2.0,
    "defines_screen": 3.0,
    "defines_module": 2.5,
    "calls_api": 3.0,
    "provides_api": 4.0,
    "calls_rpc": 4.0,
    "provides_rpc": 5.0,
    "emits_event": 3.5,
    "consumes_event": 3.5,
    "capability_has_operation": 8.0,
    "capability_has_screen": 6.0,
    "capability_has_module": 5.0,
    "capability_has_file": 3.0,
    "capability_depends_on": 4.0,
    "derived_from_cluster": 1.0,
}
HUB_OPERATION_CALLER_LIMIT = 80
MIN_CAPABILITY_DEPENDENCY_COUNT = 2
MAX_CAPABILITY_DEPENDENCIES_PER_SOURCE = 8
GENERIC_MODULE_KEYS = {"app", "common", "include", "src", "tests", "test", "main"}

SKIPPED_TYPES = {"repo", "language", "build", "cluster"}
SKIPPED_PREDICATES = {"is_repository", "has_language", "uses_build_system"}


@dataclass(frozen=True)
class ClusterSummary:
    id: str
    name: str
    score: float
    node_count: int
    edge_count: int
    top_terms: list[str]
    operations: list[str]
    screens: list[str]
    modules: list[str]
    files: list[str]
    evidence: list[str]
    source_clusters: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "top_terms": self.top_terms,
            "operations": self.operations,
            "screens": self.screens,
            "modules": self.modules,
            "files": self.files,
            "evidence": self.evidence,
            "source_clusters": self.source_clusters,
        }


def cluster_facts(
    facts: list[GraphFact],
    min_nodes: int = 3,
    max_iterations: int = 30,
    refine: bool = True,
    strategy: str = "auto",
) -> list[ClusterSummary]:
    if strategy == "hierarchical":
        graph, fact_edges = build_weighted_graph(facts)
        summaries = module_seeded_clusters(facts, fact_edges, min_nodes)
        if not summaries:
            summaries = label_propagation_clusters(graph, fact_edges, min_nodes, max_iterations)
    elif strategy == "label":
        graph, fact_edges = build_weighted_graph(facts)
        summaries = label_propagation_clusters(graph, fact_edges, min_nodes, max_iterations)
    elif strategy == "auto":
        graph, fact_edges = build_weighted_graph(facts)
        summaries = label_propagation_clusters(graph, fact_edges, min_nodes, max_iterations)
        if should_use_module_fallback(summaries, facts):
            summaries = module_seeded_clusters(facts, fact_edges, min_nodes)
    else:
        raise ValueError(f"Unknown cluster strategy: {strategy}")
    summaries = sorted(summaries, key=lambda item: (-item.score, item.name))
    if refine:
        return refine_clusters(summaries)
    return summaries


def label_propagation_clusters(
    graph: dict[str, dict[str, float]],
    fact_edges: list[tuple[str, str, GraphFact]],
    min_nodes: int,
    max_iterations: int,
) -> list[ClusterSummary]:
    labels = propagate_labels(graph, max_iterations=max_iterations)
    groups: dict[str, set[str]] = defaultdict(set)
    for node, label in labels.items():
        groups[label].add(node)

    summaries: list[ClusterSummary] = []
    for index, nodes in enumerate(sorted(groups.values(), key=lambda item: (-len(item), sorted(item)[0]))):
        if len(nodes) < min_nodes:
            continue
        summaries.append(summarize_cluster(f"cluster_{len(summaries) + 1:03d}", nodes, fact_edges))
    return summaries


def should_use_module_fallback(summaries: list[ClusterSummary], facts: list[GraphFact]) -> bool:
    if len(summaries) > 2:
        return False
    cpp_calls = sum(
        1
        for fact in facts
        if fact.predicate == "calls_operation" and fact.attributes.get("language") == "cpp"
    )
    module_edges = sum(1 for fact in facts if fact.predicate == "belongs_to_module")
    return cpp_calls >= 500 and module_edges >= 20


def module_seeded_clusters(
    facts: list[GraphFact],
    fact_edges: list[tuple[str, str, GraphFact]],
    min_nodes: int,
) -> list[ClusterSummary]:
    module_nodes: dict[str, set[str]] = defaultdict(set)
    file_to_modules: dict[str, set[str]] = defaultdict(set)
    file_neighbors: dict[str, set[str]] = defaultdict(set)

    for fact in facts:
        if fact.predicate == "belongs_to_module":
            module_nodes[fact.object].update({fact.subject, fact.object})
            file_to_modules[fact.subject].add(fact.object)
        elif fact.predicate in {
            "provides_operation",
            "calls_operation",
            "defines_interface",
            "defines_screen",
            "defines_route",
            "provides_api",
            "calls_api",
            "provides_rpc",
            "calls_rpc",
            "emits_event",
            "consumes_event",
        }:
            file_neighbors[fact.subject].add(fact.object)
            if entity_type(fact.subject) == "file":
                inferred_module = inferred_module_for_file(fact.subject, fact.repo)
                if inferred_module is not None:
                    module_nodes[inferred_module].update({fact.subject, inferred_module})
                    file_to_modules[fact.subject].add(inferred_module)

    for file_entity, modules in file_to_modules.items():
        neighbors = file_neighbors.get(file_entity, set())
        for module in modules:
            module_nodes[module].update(neighbors)

    summaries: list[ClusterSummary] = []
    for nodes in sorted(module_nodes.values(), key=lambda item: (-len(item), sorted(item)[0])):
        if len(nodes) < min_nodes:
            continue
        summaries.append(summarize_cluster(f"cluster_{len(summaries) + 1:03d}", nodes, fact_edges))
    return summaries


def inferred_module_for_file(file_entity: str, repo: str) -> str | None:
    label = file_label(file_entity)
    key = file_module_key(label)
    if key is None:
        return None
    return f"module:{repo}:{key}"


def build_weighted_graph(facts: list[GraphFact]) -> tuple[dict[str, dict[str, float]], list[tuple[str, str, GraphFact]]]:
    graph: dict[str, dict[str, float]] = defaultdict(dict)
    fact_edges: list[tuple[str, str, GraphFact]] = []
    operation_callers = Counter(
        fact.object
        for fact in facts
        if fact.predicate == "calls_operation" and entity_type(fact.object) == "operation"
    )
    for fact in facts:
        if fact.predicate in SKIPPED_PREDICATES:
            continue
        source_type = entity_type(fact.subject)
        target_type = entity_type(fact.object)
        if source_type in SKIPPED_TYPES or target_type in SKIPPED_TYPES:
            continue
        if is_hub_call_edge(fact, operation_callers):
            continue
        weight = EDGE_WEIGHTS.get(fact.predicate)
        if weight is None:
            continue
        if fact.attributes.get("language") == "cpp" and fact.predicate == "calls_operation":
            weight *= 0.2
        weight *= max(0.1, fact.confidence)
        add_edge(graph, fact.subject, fact.object, weight)
        fact_edges.append((fact.subject, fact.object, fact))
    return graph, fact_edges


def is_hub_call_edge(fact: GraphFact, operation_callers: Counter[str]) -> bool:
    if fact.predicate != "calls_operation" or entity_type(fact.object) != "operation":
        return False
    return operation_callers[fact.object] > HUB_OPERATION_CALLER_LIMIT


def add_edge(graph: dict[str, dict[str, float]], left: str, right: str, weight: float) -> None:
    graph[left][right] = graph[left].get(right, 0.0) + weight
    graph[right][left] = graph[right].get(left, 0.0) + weight


def propagate_labels(graph: dict[str, dict[str, float]], max_iterations: int) -> dict[str, str]:
    labels = {node: node for node in graph}
    for _ in range(max_iterations):
        changed = False
        for node in sorted(graph, key=lambda item: (-weighted_degree(graph, item), item)):
            scores: dict[str, float] = defaultdict(float)
            for neighbor, weight in graph[node].items():
                scores[labels[neighbor]] += weight
            if not scores:
                continue
            best_label, _ = max(scores.items(), key=lambda item: (item[1], -len(item[0]), item[0]))
            if best_label != labels[node]:
                labels[node] = best_label
                changed = True
        if not changed:
            break
    return labels


def weighted_degree(graph: dict[str, dict[str, float]], node: str) -> float:
    return sum(graph[node].values())


def summarize_cluster(
    cluster_id: str,
    nodes: set[str],
    fact_edges: list[tuple[str, str, GraphFact]],
) -> ClusterSummary:
    internal_edges = [(left, right, fact) for left, right, fact in fact_edges if left in nodes and right in nodes]
    operations = sorted(node.removeprefix("operation:") for node in nodes if node.startswith("operation:"))
    screens = sorted(node.removeprefix("screen:") for node in nodes if node.startswith("screen:"))
    modules = sorted(node.removeprefix("module:") for node in nodes if node.startswith("module:"))
    files = sorted(node for node in nodes if entity_type(node) == "file")
    term_counts = Counter(term for node in nodes for term in terms_for_entity(node))
    top_terms = [term for term, _ in term_counts.most_common(8)]
    name = name_cluster(top_terms, operations, screens, modules)
    evidence = []
    seen = set()
    for _, _, fact in sorted(
        internal_edges,
        key=lambda item: (predicate_rank(item[2].predicate), sample_location(item[2])),
    ):
        location = sample_location(fact)
        if location in seen:
            continue
        seen.add(location)
        evidence.append(location)
        if len(evidence) >= 8:
            break
    score = len(nodes) + len(internal_edges) * 0.5 + len(operations) * 1.2 + len(screens) * 0.8
    return ClusterSummary(
        id=cluster_id,
        name=name,
        score=round(score, 2),
        node_count=len(nodes),
        edge_count=len(internal_edges),
        top_terms=top_terms,
        operations=operations[:30],
        screens=screens[:20],
        modules=modules[:12],
        files=files[:20],
        evidence=evidence,
        source_clusters=[cluster_id],
    )


def refine_clusters(clusters: list[ClusterSummary]) -> list[ClusterSummary]:
    grouped: dict[str, list[ClusterSummary]] = defaultdict(list)
    for cluster in clusters:
        grouped[capability_key(cluster)].append(cluster)

    refined: list[ClusterSummary] = []
    for items in grouped.values():
        refined.append(merge_cluster_group(items))

    refined = sorted(refined, key=lambda item: (-item.score, item.name))
    return [
        ClusterSummary(
            id=f"capability_{index + 1:03d}",
            name=cluster.name,
            score=cluster.score,
            node_count=cluster.node_count,
            edge_count=cluster.edge_count,
            top_terms=cluster.top_terms,
            operations=cluster.operations,
            screens=cluster.screens,
            modules=cluster.modules,
            files=cluster.files,
            evidence=cluster.evidence,
            source_clusters=cluster.source_clusters,
        )
        for index, cluster in enumerate(refined)
    ]


def capability_key(cluster: ClusterSummary) -> str:
    module_key = dominant_module_key(cluster)
    operation_counts = operation_key_counts(cluster.operations)
    operation_key = operation_counts.most_common(1)[0][0] if operation_counts else None
    operation_count = operation_counts.most_common(1)[0][1] if operation_counts else 0
    if operation_key is not None and (operation_count >= 2 or module_key is None):
        return operation_key
    if module_key is not None:
        return module_key
    if cluster.top_terms:
        return normalize_key(cluster.top_terms[0])
    return normalize_key(cluster.name)


def dominant_module_key(cluster: ClusterSummary) -> str | None:
    candidates: list[str] = []
    for module in cluster.modules:
        candidates.append(module_key_from_module_label(module))
    for screen in cluster.screens:
        rest = screen.split(":", 1)[-1]
        if "." in rest:
            candidates.append(rest.split(".", 1)[0])
    for file in cluster.files:
        file_key = file_module_key(file)
        if file_key is not None:
            candidates.append(file_key)
    counts = Counter(normalize_key(item) for item in candidates if item)
    if not counts:
        return None
    key, _ = counts.most_common(1)[0]
    return key


def module_key_from_module_label(module: str) -> str:
    parts = module.split(":", 1)
    if len(parts) != 2:
        return module
    repo, name = parts
    normalized = normalize_key(name)
    if normalized in GENERIC_MODULE_KEYS:
        return f"{repo}:{name}"
    return name


def dominant_operation_key(cluster: ClusterSummary) -> str | None:
    counts = operation_key_counts(cluster.operations)
    if not counts:
        return None
    key, count = counts.most_common(1)[0]
    if count >= 2 or len(cluster.operations) <= 3:
        return key
    return None


def operation_namespace(operation: str) -> str | None:
    parts = operation.split(".")
    if not parts:
        return None
    if parts[0] == "trpc" and len(parts) >= 2:
        return normalize_key(parts[1])
    if parts[0] == "desktopApi":
        return "desktopApi"
    if parts[0] == "ipc" and len(parts) >= 2:
        return normalize_key(parts[1])
    if parts[0] == "cpp":
        return None
    if len(parts) >= 2:
        return normalize_key(parts[0])
    return None


def operation_key_counts(operations: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for operation in operations:
        key = operation_namespace(operation)
        if key is not None:
            counts[key] += 1
    return counts


def merge_cluster_group(items: list[ClusterSummary]) -> ClusterSummary:
    operations = unique_sorted(value for item in items for value in item.operations)
    screens = unique_sorted(value for item in items for value in item.screens)
    modules = unique_sorted(value for item in items for value in item.modules)
    files = unique_sorted(value for item in items for value in item.files)
    evidence = unique_sorted(value for item in items for value in item.evidence)
    source_clusters = unique_sorted(value for item in items for value in item.source_clusters)
    term_counts = Counter(term for item in items for term in item.top_terms)
    top_terms = [term for term, _ in term_counts.most_common(10)]
    name = refined_name(items, top_terms, operations, screens, modules, files)
    return ClusterSummary(
        id=items[0].id,
        name=name,
        score=round(sum(item.score for item in items), 2),
        node_count=sum(item.node_count for item in items),
        edge_count=sum(item.edge_count for item in items),
        top_terms=top_terms[:8],
        operations=operations[:45],
        screens=screens[:30],
        modules=modules[:16],
        files=files[:30],
        evidence=evidence[:12],
        source_clusters=source_clusters,
    )


def refined_name(
    items: list[ClusterSummary],
    top_terms: list[str],
    operations: list[str],
    screens: list[str],
    modules: list[str],
    files: list[str],
) -> str:
    operation_counts = operation_key_counts(operations)
    op_key = operation_counts.most_common(1)[0][0] if operation_counts else None
    op_count = operation_counts.most_common(1)[0][1] if operation_counts else 0
    module_key = dominant_module_key(ClusterSummary("", "", 0, 0, 0, top_terms, operations, screens, modules, files, [], []))
    if op_key is not None and (op_count >= 2 or module_key is None):
        return titleize_special(op_key)
    if module_key is not None:
        return titleize_special(module_key)
    names = Counter(item.name for item in items)
    return names.most_common(1)[0][0]


def normalize_key(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1-\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return value[:1].lower() + value[1:] if value else value


def unique_sorted(values) -> list[str]:
    return sorted({value for value in values if value})


def titleize_special(value: str) -> str:
    special = {
        "desktopApi": "Desktop API",
        "claudeCode": "Claude Code",
        "worktreeConfig": "Worktree Config",
        "anthropicAccounts": "Anthropic Accounts",
        "fileViewer": "File Viewer",
        "detailsSidebar": "Details Sidebar",
        "sandboxImport": "Sandbox Import",
    }
    if value in special:
        return special[value]
    return titleize(value)


def predicate_rank(predicate: str) -> int:
    order = {
        "provides_operation": 0,
        "calls_operation": 1,
        "belongs_to_module": 2,
        "defines_screen": 3,
    }
    return order.get(predicate, 10)


def file_label(entity: str) -> str:
    if ":file:" in entity:
        return entity.split(":file:", 1)[1]
    if entity.startswith("file:"):
        return entity.removeprefix("file:")
    return entity


def file_module_key(file: str) -> str | None:
    repo = repo_for_file_entity(file)
    parts = file_label(file).split("/")
    if not parts:
        return None
    first = parts[0]
    if first in {"examples", "pocs", "tools"} and len(parts) >= 2:
        return f"{first}/{parts[1]}"
    if first == "ggml" and len(parts) >= 3:
        return f"ggml/{parts[1]}"
    if first in {"app", "common", "include", "src", "tests"}:
        return f"{repo}:{first}" if repo else first
    return first if len(parts) > 1 else None


def repo_for_file_entity(file: str) -> str | None:
    if file.startswith("repo:") and ":file:" in file:
        return file.removeprefix("repo:").split(":file:", 1)[0]
    return None


def terms_for_entity(entity: str) -> list[str]:
    value = entity
    if ":" in value:
        value = value.split(":", 1)[1]
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    raw_terms = re.split(r"[^A-Za-z0-9]+", value)
    ignored = {
        "src",
        "main",
        "renderer",
        "features",
        "components",
        "lib",
        "trpc",
        "operation",
        "file",
        "index",
        "tsx",
        "ts",
        "js",
        "repo",
    }
    return [term.lower() for term in raw_terms if len(term) >= 3 and term.lower() not in ignored]


def name_cluster(
    top_terms: list[str],
    operations: list[str],
    screens: list[str],
    modules: list[str],
) -> str:
    if modules:
        module = modules[0].split(":", 1)[-1]
        return titleize(module)
    if operations:
        parts = operations[0].split(".")
        if len(parts) >= 2:
            return titleize(parts[1])
    if screens:
        return titleize(screens[0].split(".")[0])
    if top_terms:
        return titleize(" ".join(top_terms[:2]))
    return "Unlabeled Capability"


def titleize(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    words = re.split(r"[^A-Za-z0-9]+", value)
    return " ".join(word[:1].upper() + word[1:] for word in words if word)


def clusters_to_json(clusters: list[ClusterSummary]) -> str:
    return json.dumps({"clusters": [cluster.to_dict() for cluster in clusters]}, indent=2, sort_keys=True)


def capability_facts(
    clusters: list[ClusterSummary],
    repo: str = "capabilities",
    commit: str = "derived",
    base_facts: list[GraphFact] | None = None,
) -> list[GraphFact]:
    facts: list[GraphFact] = []
    for cluster in clusters:
        capability = capability_entity(cluster)
        evidence = capability_evidence(cluster, repo, commit)
        base_attributes = {
            "capability_id": cluster.id,
            "capability_name": cluster.name,
            "score": cluster.score,
            "top_terms": cluster.top_terms,
            "source_clusters": cluster.source_clusters,
        }
        facts.append(
            GraphFact(
                subject=capability,
                predicate="is_capability",
                object=capability,
                evidence=[evidence],
                confidence=capability_confidence(cluster),
                source="capability-cluster",
                source_version="0.1.0",
                repo=repo,
                commit=commit,
                attributes=base_attributes,
            )
        )
        facts.extend(
            linked_capability_facts(
                cluster,
                capability,
                "capability_has_operation",
                [f"operation:{operation}" for operation in cluster.operations],
                evidence,
                repo,
                commit,
                base_attributes,
            )
        )
        facts.extend(
            linked_capability_facts(
                cluster,
                capability,
                "capability_has_screen",
                [f"screen:{screen}" for screen in cluster.screens],
                evidence,
                repo,
                commit,
                base_attributes,
            )
        )
        facts.extend(
            linked_capability_facts(
                cluster,
                capability,
                "capability_has_module",
                [f"module:{module}" for module in cluster.modules],
                evidence,
                repo,
                commit,
                base_attributes,
            )
        )
        facts.extend(
            linked_capability_facts(
                cluster,
                capability,
                "capability_has_file",
                [file_entity(file, repo) for file in cluster.files],
                evidence,
                repo,
                commit,
                base_attributes,
            )
        )
        for source_cluster in cluster.source_clusters:
            facts.append(
                GraphFact(
                    subject=capability,
                    predicate="derived_from_cluster",
                    object=f"cluster:{source_cluster}",
                    evidence=[evidence],
                    confidence=capability_confidence(cluster),
                    source="capability-cluster",
                    source_version="0.1.0",
                    repo=repo,
                    commit=commit,
                    attributes=base_attributes,
                )
            )
    if base_facts is not None:
        facts.extend(capability_dependency_facts(clusters, base_facts, repo, commit))
    return facts


def capability_dependency_facts(
    clusters: list[ClusterSummary],
    base_facts: list[GraphFact],
    repo: str,
    commit: str,
) -> list[GraphFact]:
    file_to_capability: dict[str, str] = {}
    operation_to_capability: dict[str, str] = {}
    screen_to_capability: dict[str, str] = {}
    cluster_by_capability: dict[str, ClusterSummary] = {}
    for cluster in clusters:
        capability = capability_entity(cluster)
        cluster_by_capability[capability] = cluster
        for file in cluster.files:
            file_to_capability[file_entity(file, repo)] = capability
        for operation in cluster.operations:
            operation_to_capability[f"operation:{operation}"] = capability
        for screen in cluster.screens:
            screen_to_capability[f"screen:{screen}"] = capability

    dependency_counts: Counter[tuple[str, str]] = Counter()
    dependency_evidence: dict[tuple[str, str], GraphFact] = {}
    dependency_operations: dict[tuple[str, str], set[str]] = defaultdict(set)
    entity_to_capability = {**file_to_capability, **operation_to_capability, **screen_to_capability}
    for fact in base_facts:
        if fact.predicate != "calls_operation":
            continue
        source_capability = entity_to_capability.get(fact.subject)
        target_capability = operation_to_capability.get(fact.object)
        if source_capability is None or target_capability is None or source_capability == target_capability:
            continue
        key = (source_capability, target_capability)
        dependency_counts[key] += 1
        dependency_operations[key].add(fact.object.removeprefix("operation:"))
        dependency_evidence.setdefault(key, fact)
    add_contract_dependencies(base_facts, entity_to_capability, dependency_counts, dependency_operations, dependency_evidence)

    facts: list[GraphFact] = []
    kept_dependencies = strongest_capability_dependencies(dependency_counts)
    for source, target, count in kept_dependencies:
        evidence_fact = dependency_evidence[(source, target)]
        evidence = evidence_fact.evidence[0] if evidence_fact.evidence else capability_evidence(
            cluster_by_capability[source],
            repo,
            commit,
        )
        facts.append(
            GraphFact(
                subject=source,
                predicate="capability_depends_on",
                object=target,
                evidence=[evidence],
                confidence=round(min(0.92, 0.5 + min(0.32, count / 50)), 3),
                source="capability-cluster",
                source_version="0.1.0",
                repo=repo,
                commit=commit,
                attributes={
                    "dependency_count": count,
                    "sample_operations": sorted(dependency_operations[(source, target)])[:10],
                    "source_capability": cluster_by_capability[source].name,
                    "target_capability": cluster_by_capability[target].name,
                },
            )
        )
    return facts


def add_contract_dependencies(
    base_facts: list[GraphFact],
    entity_to_capability: dict[str, str],
    dependency_counts: Counter[tuple[str, str]],
    dependency_operations: dict[tuple[str, str], set[str]],
    dependency_evidence: dict[tuple[str, str], GraphFact],
) -> None:
    providers: dict[str, set[str]] = defaultdict(set)
    consumers: dict[str, set[str]] = defaultdict(set)
    evidence_by_contract: dict[str, GraphFact] = {}
    provider_predicates = {"provides_api", "provides_rpc", "emits_event"}
    consumer_predicates = {"calls_api", "calls_rpc", "consumes_event", "maps_operation_to_api"}
    for fact in base_facts:
        capability = entity_to_capability.get(fact.subject)
        if capability is None:
            continue
        if fact.predicate in provider_predicates:
            providers[fact.object].add(capability)
            evidence_by_contract.setdefault(fact.object, fact)
        elif fact.predicate in consumer_predicates:
            consumers[fact.object].add(capability)
            evidence_by_contract.setdefault(fact.object, fact)

    for contract, consumer_caps in consumers.items():
        for consumer in consumer_caps:
            for provider in providers.get(contract, set()):
                if consumer == provider:
                    continue
                key = (consumer, provider)
                dependency_counts[key] += MIN_CAPABILITY_DEPENDENCY_COUNT
                dependency_operations[key].add(contract)
                dependency_evidence.setdefault(key, evidence_by_contract[contract])


def strongest_capability_dependencies(dependency_counts: Counter[tuple[str, str]]) -> list[tuple[str, str, int]]:
    by_source: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for (source, target), count in dependency_counts.items():
        if count < MIN_CAPABILITY_DEPENDENCY_COUNT:
            continue
        by_source[source].append((source, target, count))

    kept: list[tuple[str, str, int]] = []
    for dependencies in by_source.values():
        kept.extend(
            sorted(dependencies, key=lambda item: (-item[2], item[1]))[:MAX_CAPABILITY_DEPENDENCIES_PER_SOURCE]
        )
    return sorted(kept, key=lambda item: (-item[2], item[0], item[1]))


def linked_capability_facts(
    cluster: ClusterSummary,
    capability: str,
    predicate: str,
    objects: list[str],
    evidence: Evidence,
    repo: str,
    commit: str,
    base_attributes: dict[str, Any],
) -> list[GraphFact]:
    confidence = capability_confidence(cluster)
    return [
        GraphFact(
            subject=capability,
            predicate=predicate,
            object=object_,
            evidence=[evidence],
            confidence=confidence,
            source="capability-cluster",
            source_version="0.1.0",
            repo=repo,
            commit=commit,
            attributes=base_attributes,
        )
        for object_ in objects
    ]


def capability_entity(cluster: ClusterSummary) -> str:
    return f"capability:{cluster.id}:{slugify(cluster.name)}"


def capability_evidence(cluster: ClusterSummary, repo: str, commit: str) -> Evidence:
    snippet = f"{cluster.name}; score={cluster.score}; terms={', '.join(cluster.top_terms[:5])}"
    file = cluster.evidence[0].split(":", 1)[0] if cluster.evidence else "capabilities"
    line = 1
    if cluster.evidence:
        parts = cluster.evidence[0].rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit():
            file = parts[0]
            line = int(parts[1])
    return Evidence(repo=repo, commit=commit, file=file, line=line, snippet=snippet)


def capability_confidence(cluster: ClusterSummary) -> float:
    score_part = min(0.22, cluster.score / 1000)
    operation_part = min(0.18, len(cluster.operations) * 0.01)
    evidence_part = min(0.12, len(cluster.evidence) * 0.01)
    return round(min(0.96, 0.52 + score_part + operation_part + evidence_part), 3)


def file_entity(file: str, fallback_repo: str) -> str:
    if file.startswith("repo:"):
        return file
    return f"repo:{fallback_repo}:file:{file}"


def slugify(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1-\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or "capability"


def render_clusters_markdown(clusters: list[ClusterSummary]) -> str:
    lines = ["# Capability Clusters", ""]
    for cluster in clusters:
        lines.extend(
            [
                f"## {cluster.name}",
                "",
                f"- ID: `{cluster.id}`",
                f"- Score: `{cluster.score}`",
                f"- Nodes: `{cluster.node_count}`",
                f"- Edges: `{cluster.edge_count}`",
                f"- Top terms: {', '.join(cluster.top_terms) if cluster.top_terms else 'none'}",
                "",
            ]
        )
        append_section(lines, "Operations", cluster.operations)
        append_section(lines, "Screens", cluster.screens)
        append_section(lines, "Modules", cluster.modules)
        append_section(lines, "Files", cluster.files)
        append_section(lines, "Evidence", cluster.evidence)
    return "\n".join(lines)


def append_section(lines: list[str], title: str, values: list[str]) -> None:
    if not values:
        return
    lines.append(f"### {title}")
    for value in values:
        lines.append(f"- `{value}`")
    lines.append("")
