# Configuration

Know Code workspaces are configured with `.know-code.yml`.

Create one from repository paths:

```bash
know-code init ../android-app ../java-service
```

```yaml
output: .know-code
strategy: hierarchical
min_nodes: 4
title: My Workspace

repos:
  - path: ../android-app
    name: android-app
  - path: ../java-service
    name: java-service

adapter_config: examples/framework-adapters.json
```

## Fields

- `output`: workspace output directory.
- `strategy`: `hierarchical`, `auto`, or `label`.
- `min_nodes`: minimum cluster size.
- `title`: visualization title.
- `repos`: repository paths to scan.
- `adapter_config`: optional custom framework adapter JSON file.

`hierarchical` is the recommended strategy for multi-repository and native code
workspaces because it uses build/path/module structure before operation calls.
