# Architecture

Know Code uses a layered graph pipeline.

```text
repositories
  -> extractors
  -> raw fact graph
  -> repo serving graphs
  -> global capability graph
  -> PRD planning / explain / visualization
```

## Raw Fact Graph

The raw graph is the complete evidence store. It can be large, and that is fine.
It exists for traceability and diffing.

## Serving Graph

Serving graphs are smaller views for humans and AI agents. They keep capability,
module, file, contract, and selected operation edges while dropping noisy
low-level call edges.

## Capability Graph

Capabilities are derived nodes. In multi-repository workspaces, contracts such
as HTTP APIs, RPC methods, and events connect capabilities across repositories.

The recommended clustering strategy is `hierarchical`:

1. Seed candidate capabilities from build/path/module structure.
2. Attach files.
3. Attach operations, screens, routes, APIs, RPCs, and events.
4. Add capability dependency edges from operation and contract usage.
5. Filter weak dependency edges.

