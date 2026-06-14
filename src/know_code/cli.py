from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from .cluster import capability_facts, cluster_facts, clusters_to_json, render_clusters_markdown
from .config import DEFAULT_CONFIG, load_workspace_config, write_default_config
from .global_graph import build_global_graph
from .graph import diff_facts, facts_for_operation, read_ndjson, write_ndjson
from .planner import generate_plan
from .quality import analyze_quality, quality_json, render_quality_report
from .scanner import scan_repositories
from .visualize import write_visualization


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return run_init(args)
    if args.command == "index":
        return run_index(args)
    if args.command == "open":
        return run_open(args)
    if args.command == "scan":
        return run_scan(args)
    if args.command == "diff":
        return run_diff(args)
    if args.command == "explain":
        return run_explain(args)
    if args.command == "plan":
        return run_plan(args)
    if args.command == "visualize":
        return run_visualize(args)
    if args.command == "quality":
        return run_quality(args)
    if args.command == "cluster":
        return run_cluster(args)
    if args.command == "global":
        return run_global(args)
    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="know-code")
    subparsers = parser.add_subparsers(dest="command")

    init = subparsers.add_parser("init", help="create a Know Code workspace config")
    init.add_argument("--config", type=Path, default=Path(DEFAULT_CONFIG))
    init.add_argument("--force", action="store_true")

    index = subparsers.add_parser("index", help="build the configured workspace graph")
    index.add_argument("--config", type=Path, default=Path(DEFAULT_CONFIG))
    index.add_argument("--out-dir", type=Path)
    index.add_argument("--strategy", choices=["auto", "label", "hierarchical"])
    index.add_argument("--min-nodes", type=int)
    index.add_argument("--adapter-config", type=Path)

    open_cmd = subparsers.add_parser("open", help="open a generated Know Code graph")
    open_cmd.add_argument("workspace", nargs="?", type=Path, default=Path(".know-code"))
    open_cmd.add_argument(
        "--target",
        choices=["serving", "capability", "manifest"],
        default="serving",
        help="workspace artifact to open",
    )

    scan = subparsers.add_parser("scan", help="scan repositories and write graph facts")
    scan.add_argument("repos", nargs="+", type=Path)
    scan.add_argument("--out", type=Path, required=True)
    scan.add_argument("--adapter-config", type=Path)

    diff = subparsers.add_parser("diff", help="compare two graph snapshots")
    diff.add_argument("--base", type=Path, required=True)
    diff.add_argument("--next", type=Path, required=True)
    diff.add_argument("--json", action="store_true")

    explain = subparsers.add_parser("explain", help="explain operation evidence")
    explain.add_argument("--facts", type=Path, required=True)
    explain.add_argument("--operation", required=True)

    plan = subparsers.add_parser("plan", help="generate a technical plan from a PRD")
    plan.add_argument("--facts", type=Path)
    plan.add_argument("--workspace", type=Path, help="Know Code workspace directory; defaults facts to global.capabilities.ndjson")
    plan.add_argument("--prd", type=Path, required=True)
    plan.add_argument("--out", type=Path)

    visualize = subparsers.add_parser("visualize", help="generate an interactive HTML graph")
    visualize.add_argument("--facts", type=Path, required=True)
    visualize.add_argument("--out", type=Path, required=True)
    visualize.add_argument("--title", default="Know Code Graph")
    visualize.add_argument(
        "--profile",
        choices=["full", "serving", "capability"],
        default="full",
        help="graph density to render: full evidence graph, serving graph, or capability-only graph",
    )

    quality = subparsers.add_parser("quality", help="report graph coverage and operation match quality")
    quality.add_argument("--facts", type=Path, required=True)
    quality.add_argument("--json", action="store_true")

    cluster = subparsers.add_parser("cluster", help="cluster graph nodes into capability candidates")
    cluster.add_argument("--facts", type=Path, required=True)
    cluster.add_argument("--out", type=Path)
    cluster.add_argument("--markdown", type=Path)
    cluster.add_argument("--graph-out", type=Path)
    cluster.add_argument("--min-nodes", type=int, default=4)
    cluster.add_argument(
        "--strategy",
        choices=["auto", "label", "hierarchical"],
        default="auto",
        help="capability clustering strategy",
    )
    cluster.add_argument("--raw-clusters", action="store_true")
    cluster.add_argument("--json", action="store_true")

    global_graph = subparsers.add_parser("global", help="build a multi-repository global capability graph")
    global_graph.add_argument("repos", nargs="+", type=Path)
    global_graph.add_argument("--out-dir", type=Path, required=True)
    global_graph.add_argument("--adapter-config", type=Path)
    global_graph.add_argument("--min-nodes", type=int, default=4)
    global_graph.add_argument(
        "--strategy",
        choices=["auto", "label", "hierarchical"],
        default="hierarchical",
        help="global capability clustering strategy",
    )
    global_graph.add_argument("--title", default="Global Code Capability Graph")

    return parser


def run_init(args: argparse.Namespace) -> int:
    if args.config.exists() and not args.force:
        print(f"Config already exists: {args.config}. Use --force to overwrite.")
        return 1
    write_default_config(args.config)
    print(f"Wrote config to {args.config}")
    return 0


def run_index(args: argparse.Namespace) -> int:
    config = load_workspace_config(args.config)
    out_dir = args.out_dir or config.output
    strategy = args.strategy or config.strategy
    min_nodes = args.min_nodes if args.min_nodes is not None else config.min_nodes
    adapter_config = args.adapter_config or config.adapter_config
    manifest = build_global_graph(
        config.repos,
        out_dir,
        adapter_config=adapter_config,
        strategy=strategy,
        min_nodes=min_nodes,
        title=config.title,
    )
    print(f"Wrote Know Code workspace to {out_dir}")
    print(f"- Serving graph: {manifest['outputs']['serving_graph']}")
    print(f"- Capability graph: {manifest['outputs']['capability_graph']}")
    print(f"- Manifest: {manifest['outputs']['manifest']}")
    return 0


def run_open(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    targets = {
        "serving": workspace / "global.serving.html",
        "capability": workspace / "global.capability-only.html",
        "manifest": workspace / "manifest.json",
    }
    target = targets[args.target]
    if not target.exists():
        print(f"Missing artifact: {target}")
        return 1
    webbrowser.open(target.as_uri())
    print(f"Opened {target}")
    return 0


def run_scan(args: argparse.Namespace) -> int:
    facts = scan_repositories(args.repos, args.adapter_config)
    write_ndjson(args.out, facts)
    print(f"Wrote {len(facts)} fact(s) to {args.out}")
    return 0


def run_diff(args: argparse.Namespace) -> int:
    base = read_ndjson(args.base)
    next_facts = read_ndjson(args.next)
    diff = diff_facts(base, next_facts)
    if args.json:
        print(
            json.dumps(
                {key: [fact.to_dict() for fact in value] for key, value in diff.items()},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for key in ("added", "removed", "changed"):
            print(f"{key}: {len(diff[key])}")
    return 0


def run_explain(args: argparse.Namespace) -> int:
    facts = read_ndjson(args.facts)
    related = facts_for_operation(facts, args.operation)
    if not related:
        print(f"No facts found for operation {args.operation}")
        return 1
    print(f"Operation: {args.operation.removeprefix('operation:')}")
    for fact in related:
        evidence = fact.evidence[0] if fact.evidence else None
        location = ""
        if evidence is not None:
            location = f" at {evidence.repo}/{evidence.file}:{evidence.line}"
        print(f"- {fact.repo}: {fact.predicate} {fact.object}{location}")
    return 0


def run_plan(args: argparse.Namespace) -> int:
    facts_path = args.facts
    if facts_path is None and args.workspace is not None:
        facts_path = args.workspace / "global.capabilities.ndjson"
    if facts_path is None:
        print("Either --facts or --workspace is required.")
        return 1
    facts = read_ndjson(facts_path)
    plan = generate_plan(args.prd, facts)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(plan, encoding="utf-8")
        print(f"Wrote plan to {args.out}")
    else:
        sys.stdout.write(plan)
    return 0


def run_visualize(args: argparse.Namespace) -> int:
    facts = read_ndjson(args.facts)
    write_visualization(facts, args.out, args.title, profile=args.profile)
    print(f"Wrote visualization to {args.out}")
    return 0


def run_quality(args: argparse.Namespace) -> int:
    facts = read_ndjson(args.facts)
    quality = analyze_quality(facts)
    if args.json:
        print(quality_json(quality))
    else:
        print(render_quality_report(quality))
    return 0


def run_cluster(args: argparse.Namespace) -> int:
    facts = read_ndjson(args.facts)
    clusters = cluster_facts(
        facts,
        min_nodes=args.min_nodes,
        refine=not args.raw_clusters,
        strategy=args.strategy,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(clusters_to_json(clusters), encoding="utf-8")
        print(f"Wrote {len(clusters)} cluster(s) to {args.out}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_clusters_markdown(clusters), encoding="utf-8")
        print(f"Wrote cluster report to {args.markdown}")
    if args.graph_out:
        graph_repo = dominant_repo(facts)
        augmented = facts + capability_facts(clusters, repo=graph_repo, commit="derived", base_facts=facts)
        write_ndjson(args.graph_out, augmented)
        print(f"Wrote augmented graph to {args.graph_out}")
    if args.json or (not args.out and not args.markdown):
        print(clusters_to_json(clusters))
    return 0


def run_global(args: argparse.Namespace) -> int:
    manifest = build_global_graph(
        args.repos,
        args.out_dir,
        adapter_config=args.adapter_config,
        strategy=args.strategy,
        min_nodes=args.min_nodes,
        title=args.title,
    )
    print(f"Wrote global graph workspace to {args.out_dir}")
    print(f"- Raw facts: {manifest['outputs']['raw_facts']}")
    print(f"- Serving graph: {manifest['outputs']['serving_graph']}")
    print(f"- Capability graph: {manifest['outputs']['capability_graph']}")
    print(f"- Manifest: {manifest['outputs']['manifest']}")
    return 0


def dominant_repo(facts) -> str:
    counts: dict[str, int] = {}
    for fact in facts:
        counts[fact.repo] = counts.get(fact.repo, 0) + 1
    if not counts:
        return "capabilities"
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


if __name__ == "__main__":
    raise SystemExit(main())
