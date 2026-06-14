# Quickstart

## Install

```bash
python -m pip install -e .
```

## Single Repository

```bash
know-code init
know-code index --open
know-code open
```

This creates `.know-code.yml`, scans the configured repository, and writes graph
artifacts to `.know-code/`.

## Multiple Repositories

Generate a config from repository paths:

```bash
know-code init ../android-app ../h5-member-center ../subscription-service
know-code doctor
know-code index --open
```

Or edit `.know-code.yml` manually:

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
know-code index --config .know-code.yml --open
know-code open .know-code
```

## Serve Over Local HTTP

```bash
know-code serve .know-code
```

This serves the workspace at `http://127.0.0.1:8765/global.serving.html`.

## Debugging The Graph

```bash
know-code doctor
know-code quality --facts .know-code/global.facts.ndjson
know-code cluster --facts .know-code/global.facts.ndjson --json
know-code explain --facts .know-code/global.facts.ndjson --operation trpc.projects.list
```
