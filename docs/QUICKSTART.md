# Quickstart

## Install

```bash
python -m pip install -e .
```

## Single Repository

```bash
know-code init
know-code index
know-code open
```

This creates `.know-code.yml`, scans the configured repository, and writes graph
artifacts to `.know-code/`.

## Multiple Repositories

Edit `.know-code.yml`:

```yaml
output: .know-code
strategy: hierarchical
min_nodes: 4

repos:
  - path: ../android-app
    name: android-app
  - path: ../h5-member-center
    name: h5-member-center
  - path: ../subscription-service
    name: subscription-service
  - path: ../contracts
    name: contracts
```

Then run:

```bash
know-code index --config .know-code.yml
know-code open .know-code
```

## Debugging The Graph

```bash
know-code quality --facts .know-code/global.facts.ndjson
know-code cluster --facts .know-code/global.facts.ndjson --json
know-code explain --facts .know-code/global.facts.ndjson --operation trpc.projects.list
```

