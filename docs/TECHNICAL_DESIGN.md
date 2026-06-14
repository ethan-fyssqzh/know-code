# Technical Design

## Product Goal

Know Code helps AI coding agents answer this question before editing code:

> Given a product requirement, which repositories, operations, contracts,
> client surfaces, and tests should be changed, and why?

The system builds an incremental, evidence-backed cross-repository graph. It is
not a one-shot summary of code. Every edge is a fact with source location,
extractor version, confidence, and commit metadata.

## Core Pipeline

```text
Repository set
  -> repo profiling
  -> extractor facts
  -> entity resolution
  -> operation graph
  -> capability stitching
  -> PRD matching
  -> technical plan
```

The first implementation ships the lower half of this pipeline:

```text
Repository set
  -> extractor facts
  -> operation graph
  -> graph diff
  -> quality / explain / visualize / cluster / plan commands
```

LLM-based capability stitching is deliberately a later layer. It should reason
over facts instead of reading every file directly.

## Graph Fact Schema

`GraphFact` is the write format for extractors, the storage format for graph
snapshots, the diff unit for code changes, and the evidence layer for PRD
planning.

```json
{
  "id": "fact_deduplicated_hash",
  "subject": "repo:android-app:file:SubscriptionRepository.kt",
  "predicate": "calls_operation",
  "object": "operation:subscription.cancel",
  "attributes": {
    "language": "kotlin"
  },
  "evidence": [
    {
      "repo": "android-app",
      "commit": "abc123",
      "file": "app/src/main/java/.../SubscriptionRepository.kt",
      "line": 42,
      "snippet": "bizClient.call(\"subscription.cancel\", request)"
    }
  ],
  "confidence": 0.92,
  "source": "company-biz-http",
  "source_version": "0.1.0",
  "repo": "android-app",
  "commit": "abc123",
  "valid_from": "abc123",
  "valid_until": null
}
```

### Required Semantics

- `subject`: the entity that owns the relation.
- `predicate`: the relation type.
- `object`: the target entity.
- `evidence`: where the fact came from.
- `confidence`: extractor confidence, not model confidence.
- `source`: extractor or adapter name.
- `valid_from` / `valid_until`: fact lifecycle for incremental graph updates.

## Entity Model

The graph is language agnostic. Extractors translate language and framework
details into shared entities:

```text
repo:<name>
file:<repo>:<path>
screen:<repo>:<name>
route:<repo>:<path>
api:<METHOD> <PATH>
rpc:<Package.Service.Method>
operation:<domain.action>
event:<topic>
schema:<name>
module:<repo>:<name>
```

## Predicate Model

Initial predicates:

```text
has_language
has_file
defines_screen
defines_route
calls_api
provides_api
calls_rpc
provides_rpc
defines_schema
calls_operation
provides_operation
maps_operation_to_api
emits_event
consumes_event
```

Electron IPC and tRPC are normalized into operations:

```text
ipcMain.handle("window:minimize") -> provides_operation operation:ipc.window.minimize
ipcRenderer.invoke("window:minimize") -> calls_operation operation:ipc.window.minimize
trpc.projects.list.useQuery() -> calls_operation operation:trpc.projects.list
projectsRouter.list -> provides_operation operation:trpc.projects.list
features/projects/ProjectSelector.tsx -> screen:repo:projects.ProjectSelector
```

The extractor also follows simple tRPC router aliases and flattened factories,
for example `changes: createGitRouter()` plus
`...createStatusRouter()._def.procedures` maps
`createStatusRouter().getStatus` to `operation:trpc.changes.getStatus`.

## Graph Quality Metrics

Graph quality is measurable:

```bash
know-code quality --facts graph.ndjson
```

The report includes:

- operation provider/caller match rate
- call-only operations, which often indicate missing provider extractors or
  router alias gaps
- provider-only operations, which may be unused, dynamically called, or simply
  missing client extraction
- top connected operations by call/provider count
- predicate and entity type distribution

## Capability Candidate Clustering

The CLI can cluster graph nodes into capability candidates:

```bash
know-code cluster --facts graph.ndjson --out capabilities.json --markdown capabilities.md
```

The first implementation uses dependency-free weighted label propagation. It is
not a full Leiden/Louvain implementation, but it uses the same idea of weighted
graph communities and produces stable candidates that can later be fed into a
Leiden implementation or an LLM naming pass.

Before clustering, the graph is filtered and weighted:

```text
screen calls_operation operation       weight 6
file provides_operation operation      weight 7
operation maps_operation_to operation  weight 5
screen belongs_to_module module        weight 4
file belongs_to_module module          weight 4
repo/language/build facts              skipped
```

Raw clusters are refined by merging communities with the same dominant feature
module or operation namespace, such as `changes`, `chats`, or `desktopApi`.
Each refined capability includes top operations, screens, modules, files, terms,
source evidence, and the raw `source_clusters` that were merged. Use
`--raw-clusters` to inspect the pre-refinement communities.

Capabilities can be written back into the graph:

```bash
know-code cluster --facts graph.ndjson --graph-out graph.capabilities.ndjson
```

This emits derived facts:

```text
capability:<id>:<slug> is_capability capability:<id>:<slug>
capability:<id>:<slug> capability_has_operation operation:trpc.changes.getStatus
capability:<id>:<slug> capability_has_screen screen:1code:changes.ChangesView
capability:<id>:<slug> capability_has_module module:1code:changes
capability:<id>:<slug> capability_has_file repo:1code:file:src/main/lib/git/status.ts
capability:<id>:<slug> derived_from_cluster cluster:cluster_003
```

The augmented graph is the bridge from operation-level graph to capability-level
PRD matching.

Later capability-level predicates:

```text
belongs_to_capability
owns_capability
impacts_repo
tested_by
configured_by
```

## Custom Framework Strategy

Company-specific HTTP/RPC wrappers are first-class. The system should not depend
on URLs being visible in business code.

The graph uses an `operation:<name>` abstraction:

```text
android-app calls_operation operation:subscription.cancel
subscription-service provides_operation operation:subscription.cancel
operation:subscription.cancel maps_operation_to_api api:POST /subscription/cancel
```

This lets PRD planning work even when the underlying transport is hidden by a
framework.

Adapters can extract facts from:

- annotations or decorators
- interface definitions
- registration calls
- generated client metadata
- gateway or service discovery config
- runtime route registries

The first implementation supports JSON-configured annotation and regex rules.

## Incremental Updates

Graph snapshots are NDJSON files. A future service can persist the same records
in SQLite, DuckDB, Neo4j, or Glean-like fact storage.

For code changes:

```text
old graph snapshot
new graph snapshot
  -> compare fact ids
  -> added facts
  -> removed facts
  -> changed facts
  -> impacted operations
```

Facts should be deterministic for the same code and extractor version. Removed
facts can later be marked with `valid_until` instead of physically deleted.

## PRD-to-Tech-Plan Flow

The first planner is rule-based:

1. Read PRD text.
2. Match operation/API/RPC names and aliases from facts.
3. Resolve provider repositories, caller repositories, endpoints, RPC methods,
   and events.
4. Generate a Markdown plan with evidence and open questions.

The intended production planner adds an LLM layer:

```text
PRD decomposition
  -> requirement objects with source spans
  -> capability matching against graph
  -> repository ownership inference
  -> implementation plan with evidence
```

The LLM must cite graph facts instead of inventing repository ownership.

## Graph Visualization

The CLI can render a graph snapshot as a standalone HTML file:

```bash
know-code visualize --facts graph.ndjson --out graph.html
```

The visualization is a trust and debugging surface. It shows:

- entity nodes grouped by type, such as repo, operation, api, rpc, event, screen,
  module, and interface
- fact edges labeled by predicate
- predicate filters and free-text search
- side-panel evidence for selected nodes and edges

The HTML is dependency-free and can be published as a CI artifact for PR graph
impact reports.

## MVP Scope

In scope:

- Java/Kotlin services and Android clients.
- Swift/iOS clients.
- H5 TypeScript/JavaScript clients.
- Protobuf RPC contracts.
- Custom framework operation extraction.
- Snapshot diff and operation explanation.
- Graph quality report.
- Static HTML graph visualization.
- Weighted community clustering for capability candidates.
- Rule-based PRD technical plan generation.

Out of scope for the first cut:

- Full C++ call graph.
- Full Java bytecode analysis.
- Runtime registry dumping.
- LLM API integration.
- Persistent graph database.

## Open Source Influence

- Glean and Kythe inform the fact-based model.
- SCIP/LSIF inform language-agnostic symbol indexing.
- Tree-sitter and Semgrep inform framework adapter extraction.
- Joern and clangd are candidates for future C++ depth.
- Backstage, Buf, OpenAPI, and AsyncAPI inform ownership and contract thinking.
