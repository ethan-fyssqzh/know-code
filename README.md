# Know Code

Codebase intelligence layer for AI coding agents.

Know Code scans one or more repositories and builds an evidence-backed
capability graph. The goal is to help an AI coding agent answer:

> Given this product requirement, which repositories, contracts, capabilities,
> files, and operations should change, and why?

It is designed for mixed stacks: Java/Kotlin services, C/C++ native code,
Android/iOS clients, H5/TypeScript apps, Electron/tRPC apps, protobuf contracts,
HTTP APIs, RPC, events, and company-specific framework wrappers.

## Quick Start

```bash
python -m pip install -e .
know-code init
know-code index --open
know-code open
```

`know-code init` creates `.know-code.yml`.

```yaml
output: .know-code
strategy: hierarchical
min_nodes: 4
title: Know Code Workspace

repos:
  - path: .
    name: current-repo
```

For multiple repositories:

```bash
know-code init ../android-app ../ios-app ../h5-member-center ../subscription-service
```

Or edit `.know-code.yml` manually:

```yaml
output: .know-code
strategy: hierarchical

repos:
  - path: ../android-app
    name: android-app
  - path: ../ios-app
    name: ios-app
  - path: ../h5-member-center
    name: h5-member-center
  - path: ../subscription-service
    name: subscription-service
  - path: ../contracts
    name: contracts
```

Then run:

```bash
know-code index --config .know-code.yml --open
know-code open .know-code
```

## Outputs

`know-code index` writes a local workspace:

```text
.know-code/
  manifest.json
  global.facts.ndjson
  global.capabilities.ndjson
  global.capabilities.json
  global.capabilities.md
  global.serving.html
  global.capability-only.html
  repos/
    <repo>.facts.ndjson
    <repo>.serving.html
    <repo>.quality.json
```

- `global.facts.ndjson`: full fact store with source evidence.
- `global.serving.html`: default graph for humans and AI agents.
- `global.capability-only.html`: compact capability map.
- `repos/*.serving.html`: per-repository serving graphs.
- `global.capabilities.json`: machine-readable capability summaries.

## Core Ideas

Know Code separates graph layers:

```text
Raw Fact Graph       complete evidence store
Repo Serving Graph   per-repository structure for local understanding
Global Capability    cross-repository product capability map
```

Repositories stay as ownership boundaries. Contracts connect repositories.
Capabilities represent product or technical areas.

Examples of cross-repository facts:

```text
h5 route/file        calls_api      api:POST /subscriptions/cancel
java controller      provides_api   api:POST /subscriptions/cancel
ios client           calls_rpc      rpc:subscription.v1.SubscriptionService.Cancel
java worker          consumes_event event:subscription.cancelled
```

Derived capability facts include:

```text
capability_has_file
capability_has_module
capability_has_operation
capability_depends_on
```

## Commands

High-level commands:

```bash
know-code init repo-a repo-b repo-c
know-code doctor
know-code index --open
know-code open
know-code serve .know-code
know-code global /path/to/repo-a /path/to/repo-b --out-dir .know-code
```

Lower-level commands remain available for debugging:

```bash
know-code scan repo-a repo-b --out graph.ndjson
know-code quality --facts graph.ndjson
know-code cluster --facts graph.ndjson --strategy hierarchical --graph-out graph.capabilities.ndjson
know-code visualize --facts graph.capabilities.ndjson --profile serving --out graph.html
know-code explain --facts graph.ndjson --operation subscription.cancel
know-code plan --facts graph.ndjson --prd prd.md
```

## Extractors

Current extractors cover:

- Generic repository metadata and build files.
- Java/Kotlin Spring HTTP providers.
- Java/Kotlin Retrofit HTTP callers.
- Java/Kotlin Kafka event publish/consume.
- Protobuf service, RPC, and message facts.
- TypeScript/JavaScript/H5 routes and HTTP calls.
- Swift/iOS views and HTTP calls.
- Electron IPC, preload APIs, tRPC routers/calls, and React feature surfaces.
- C/C++ CMake/Bazel targets, path modules, public interfaces, functions, calls,
  and native entry points.
- JSON-configured custom framework adapters.

## Documentation

- [Quickstart](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [Graph Schema](docs/GRAPH_SCHEMA.md)
- [Adapters](docs/ADAPTERS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Technical Design](docs/TECHNICAL_DESIGN.md)

## Status

Know Code is early, but already useful for repository mapping, capability
discovery, graph visualization, and evidence-backed PRD planning experiments.
The next major areas are incremental indexing, a local web UI, richer PRD
matching, and plugin packaging.
