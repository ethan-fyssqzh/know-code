from __future__ import annotations

from collections import Counter
import html
import json
from pathlib import Path
from typing import Any

from .models import GraphFact


def write_visualization(
    facts: list[GraphFact],
    output: Path,
    title: str = "Know Code Graph",
    profile: str = "full",
) -> None:
    graph = build_visualization_graph(facts, profile=profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(graph, title), encoding="utf-8")


def build_visualization_graph(facts: list[GraphFact], profile: str = "full") -> dict[str, Any]:
    facts = facts_for_profile(facts, profile)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for fact in facts:
        for entity in (fact.subject, fact.object):
            if entity not in nodes:
                nodes[entity] = {
                    "id": entity,
                    "label": label_for_entity(entity),
                    "type": type_for_entity(entity),
                    "repo": repo_for_entity(entity) or fact.repo,
                    "degree": 0,
                }
        nodes[fact.subject]["degree"] += 1
        nodes[fact.object]["degree"] += 1
        evidence = fact.evidence[0].to_dict() if fact.evidence else None
        edges.append(
            {
                "id": fact.id,
                "source": fact.subject,
                "target": fact.object,
                "predicate": fact.predicate,
                "confidence": fact.confidence,
                "repo": fact.repo,
                "extractor": fact.source,
                "evidence": evidence,
                "attributes": fact.attributes,
            }
        )

    return {
        "nodes": sorted(nodes.values(), key=lambda item: (item["type"], item["id"])),
        "edges": sorted(edges, key=lambda item: (item["predicate"], item["source"], item["target"])),
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "profile": profile,
            "types": dict(sorted(Counter(node["type"] for node in nodes.values()).items())),
            "predicates": dict(sorted(Counter(edge["predicate"] for edge in edges).items())),
            "repos": dict(sorted(Counter(edge["repo"] for edge in edges).items())),
        },
    }


def facts_for_profile(facts: list[GraphFact], profile: str) -> list[GraphFact]:
    if profile == "full":
        return facts
    if profile == "capability":
        return capability_profile_facts(facts)
    if profile == "serving":
        return serving_profile_facts(facts)
    raise ValueError(f"Unknown visualization profile: {profile}")


def capability_profile_facts(facts: list[GraphFact]) -> list[GraphFact]:
    allowed = {
        "is_capability",
        "capability_has_module",
        "capability_has_file",
        "capability_has_operation",
        "capability_has_screen",
        "capability_depends_on",
    }
    return [fact for fact in facts if fact.predicate in allowed]


def serving_profile_facts(facts: list[GraphFact]) -> list[GraphFact]:
    selected = capability_profile_facts(facts)
    selected.extend(
        fact
        for fact in facts
        if fact.predicate in {"is_repository", "has_language", "uses_build_system", "defines_module"}
    )
    selected.extend(top_facts_by_predicate(facts, "belongs_to_module", limit=500))
    selected.extend(top_facts_by_predicate(facts, "provides_operation", limit=500))
    return selected


def top_facts_by_predicate(facts: list[GraphFact], predicate: str, limit: int) -> list[GraphFact]:
    matching = [fact for fact in facts if fact.predicate == predicate]
    return sorted(
        matching,
        key=lambda fact: (-fact.confidence, fact.repo, fact.subject, fact.object),
    )[:limit]


def label_for_entity(entity: str) -> str:
    if ":" not in entity:
        return entity
    prefix, rest = entity.split(":", 1)
    if prefix == "api":
        return rest
    if prefix == "repo":
        if ":file:" in entity:
            return entity.split(":file:", 1)[1].rsplit("/", 1)[-1]
        return rest.split(":", 1)[0]
    if prefix == "capability":
        parts = rest.split(":", 1)
        return parts[1] if len(parts) == 2 else rest
    if prefix in {"operation", "event", "rpc", "schema", "module", "interface", "screen", "route", "cluster"}:
        return rest
    if prefix == "file":
        return rest.rsplit("/", 1)[-1]
    return rest


def type_for_entity(entity: str) -> str:
    if entity.startswith("repo:") and ":file:" in entity:
        return "file"
    if ":" not in entity:
        return "entity"
    return entity.split(":", 1)[0]


def repo_for_entity(entity: str) -> str | None:
    if entity.startswith("repo:"):
        if ":file:" in entity:
            return entity.removeprefix("repo:").split(":file:", 1)[0]
        return entity.removeprefix("repo:").split(":", 1)[0]
    for prefix in ("screen:", "route:", "module:", "interface:"):
        if entity.startswith(prefix):
            return entity.removeprefix(prefix).split(":", 1)[0]
    if entity.startswith("file:"):
        return entity.removeprefix("file:").split(":", 1)[0]
    return None


def render_html(graph: dict[str, Any], title: str) -> str:
    graph_json = json.dumps(graph, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    return (
        HTML_TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__GRAPH_JSON__", graph_json)
    )


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #5e6a78;
      --line: #d7dde6;
      --blue: #246bfe;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background: var(--bg);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }
    .app {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr) 360px;
      height: 100vh;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      overflow: auto;
      padding: 18px;
    }
    .details {
      border-left: 1px solid var(--line);
      border-right: 0;
    }
    main {
      position: relative;
      min-width: 0;
      overflow: hidden;
    }
    h1 {
      font-size: 20px;
      line-height: 1.2;
      margin: 0 0 14px;
      letter-spacing: 0;
    }
    h2 {
      font-size: 12px;
      margin: 22px 0 9px;
      color: var(--muted);
      letter-spacing: 0;
      text-transform: uppercase;
    }
    input[type="search"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      font: inherit;
      outline: none;
    }
    input[type="search"]:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 3px rgba(36, 107, 254, 0.12);
    }
    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 12px;
    }
    .stat {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfe;
    }
    .stat strong {
      display: block;
      font-size: 20px;
      line-height: 1;
      margin-bottom: 4px;
    }
    .legend {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .legend-item, .filter {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 30px;
      color: var(--muted);
    }
    .filter {
      color: var(--ink);
    }
    .filter input {
      margin: 0;
    }
    .filter span, .legend-item span:last-child {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .swatch {
      width: 11px;
      height: 11px;
      border-radius: 50%;
      flex: 0 0 auto;
    }
    .toolbar {
      position: absolute;
      inset: 16px 16px auto auto;
      z-index: 3;
      display: flex;
      gap: 8px;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      font: inherit;
      padding: 8px 10px;
      box-shadow: 0 8px 22px rgba(30, 42, 60, 0.08);
      cursor: pointer;
    }
    svg {
      display: block;
      width: 100%;
      height: 100%;
      background:
        linear-gradient(#e9edf4 1px, transparent 1px),
        linear-gradient(90deg, #e9edf4 1px, transparent 1px);
      background-size: 34px 34px;
    }
    .edge {
      stroke: #9aa7b8;
      stroke-opacity: 0.52;
      stroke-width: 1.4;
    }
    .edge.highlight {
      stroke: var(--blue);
      stroke-opacity: 0.95;
      stroke-width: 2.5;
    }
    .node circle {
      stroke: #fff;
      stroke-width: 2;
      filter: drop-shadow(0 5px 12px rgba(30, 42, 60, 0.18));
      cursor: pointer;
    }
    .node.selected circle {
      stroke: #111827;
      stroke-width: 3;
    }
    .label {
      font-size: 11px;
      fill: #293442;
      paint-order: stroke;
      stroke: rgba(247, 248, 251, 0.92);
      stroke-width: 4px;
      pointer-events: none;
    }
    .empty {
      color: var(--muted);
      margin-top: 18px;
    }
    .detail-title {
      font-size: 18px;
      font-weight: 700;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .kv {
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 8px;
      padding: 8px 0;
      border-bottom: 1px solid #edf0f5;
    }
    .kv span:first-child {
      color: var(--muted);
    }
    .kv span:last-child {
      overflow-wrap: anywhere;
    }
    .fact {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      margin: 8px 0;
      background: #fbfcfe;
    }
    .fact strong {
      display: block;
      margin-bottom: 5px;
      overflow-wrap: anywhere;
    }
    .fact code {
      display: block;
      color: var(--muted);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    @media (max-width: 980px) {
      body { overflow: auto; }
      .app {
        grid-template-columns: 1fr;
        height: auto;
        min-height: 100vh;
      }
      aside, .details {
        border: 0;
        border-bottom: 1px solid var(--line);
      }
      main {
        height: 68vh;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>__TITLE__</h1>
      <input id="search" type="search" placeholder="Search repo, operation, API, RPC...">
      <div class="stats">
        <div class="stat"><strong id="nodeCount">0</strong><span>nodes</span></div>
        <div class="stat"><strong id="edgeCount">0</strong><span>edges</span></div>
      </div>
      <h2>Legend</h2>
      <div id="legend" class="legend"></div>
      <h2>Predicates</h2>
      <div id="predicates"></div>
    </aside>
    <main>
      <div class="toolbar">
        <button id="fit">Fit</button>
        <button id="reset">Reset</button>
      </div>
      <svg id="graph" role="img" aria-label="Know Code graph visualization"></svg>
    </main>
    <aside class="details">
      <h2>Selection</h2>
      <div id="details" class="empty">Select a node or edge to inspect evidence.</div>
    </aside>
  </div>
  <script id="graph-data" type="application/json">__GRAPH_JSON__</script>
  <script>
    const graph = JSON.parse(document.getElementById("graph-data").textContent);
    const svg = document.getElementById("graph");
    const details = document.getElementById("details");
    const search = document.getElementById("search");
    const fitButton = document.getElementById("fit");
    const resetButton = document.getElementById("reset");
    const width = () => svg.clientWidth || 900;
    const height = () => svg.clientHeight || 700;
    const colors = {
      repo: "#246bfe",
      operation: "#169b62",
      api: "#c46a16",
      rpc: "#7650d9",
      event: "#c93d3d",
      schema: "#0e8d91",
      capability: "#111827",
      screen: "#d14c8b",
      route: "#607d2d",
      module: "#795548",
      interface: "#5865a8",
      file: "#6b7280",
      language: "#5e6a78",
      build: "#7a6a42",
      entity: "#5e6a78"
    };
    const nodeById = new Map(graph.nodes.map(node => [node.id, {...node}]));
    graph.nodes = [...nodeById.values()];
    const edges = graph.edges.map(edge => ({
      ...edge,
      sourceNode: nodeById.get(edge.source),
      targetNode: nodeById.get(edge.target)
    })).filter(edge => edge.sourceNode && edge.targetNode);
    const predicates = [...new Set(edges.map(edge => edge.predicate))].sort();
    const enabledPredicates = new Set(predicates);
    let selected = null;
    let transform = {x: 0, y: 0, scale: 1};

    document.getElementById("nodeCount").textContent = graph.nodes.length;
    document.getElementById("edgeCount").textContent = edges.length;

    function initPositions() {
      const types = [...new Set(graph.nodes.map(node => node.type))].sort();
      const buckets = new Map(types.map((type, index) => [type, index]));
      const centerX = width() / 2;
      const centerY = height() / 2;
      const radius = Math.min(width(), height()) * 0.34;
      graph.nodes.forEach((node, index) => {
        const bucket = buckets.get(node.type) || 0;
        const angle = (2 * Math.PI * bucket / Math.max(types.length, 1)) + (index % 11) * 0.045;
        node.x = centerX + Math.cos(angle) * radius + ((index % 5) - 2) * 16;
        node.y = centerY + Math.sin(angle) * radius + ((index % 7) - 3) * 14;
        node.vx = 0;
        node.vy = 0;
      });
    }

    function renderFilters() {
      document.getElementById("legend").innerHTML = [...new Set(graph.nodes.map(node => node.type))].sort().map(type => `
        <div class="legend-item"><span class="swatch" style="background:${colors[type] || colors.entity}"></span><span>${escapeHtml(type)}</span></div>
      `).join("");
      document.getElementById("predicates").innerHTML = predicates.map(predicate => `
        <label class="filter">
          <input type="checkbox" data-predicate="${escapeAttr(predicate)}" checked>
          <span title="${escapeAttr(predicate)}">${escapeHtml(predicate)} (${graph.stats.predicates[predicate] || 0})</span>
        </label>
      `).join("");
      document.querySelectorAll("#predicates input").forEach(input => {
        input.addEventListener("change", () => {
          if (input.checked) enabledPredicates.add(input.dataset.predicate);
          else enabledPredicates.delete(input.dataset.predicate);
          draw();
        });
      });
    }

    function settleLayout() {
      const nodes = graph.nodes;
      const iterations = nodes.length > 900 ? 8 : nodes.length > 450 ? 18 : 85;
      const repulsionStep = nodes.length > 900 ? 24 : nodes.length > 450 ? 10 : 1;
      for (let i = 0; i < iterations; i++) {
        for (const edge of edges) {
          const a = edge.sourceNode;
          const b = edge.targetNode;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const distance = Math.max(36, Math.sqrt(dx * dx + dy * dy));
          const target = edge.predicate.includes("operation") ? 145 : 118;
          const force = (distance - target) * 0.006;
          const fx = (dx / distance) * force;
          const fy = (dy / distance) * force;
          a.vx += fx;
          a.vy += fy;
          b.vx -= fx;
          b.vy -= fy;
        }
        for (let a = 0; a < nodes.length; a++) {
          for (let b = a + repulsionStep; b < nodes.length; b += repulsionStep) {
            const one = nodes[a];
            const two = nodes[b];
            const dx = two.x - one.x;
            const dy = two.y - one.y;
            const distanceSq = Math.max(90, dx * dx + dy * dy);
            const force = 56 / distanceSq;
            one.vx -= dx * force;
            one.vy -= dy * force;
            two.vx += dx * force;
            two.vy += dy * force;
          }
        }
        for (const node of nodes) {
          node.vx += (width() / 2 - node.x) * 0.0009;
          node.vy += (height() / 2 - node.y) * 0.0009;
          node.vx *= 0.82;
          node.vy *= 0.82;
          node.x += node.vx;
          node.y += node.vy;
        }
      }
    }

    function draw() {
      const query = search.value.trim().toLowerCase();
      const visibleEdges = edges.filter(edge => {
        if (!enabledPredicates.has(edge.predicate)) return false;
        if (!query) return true;
        return [edge.source, edge.target, edge.predicate, edge.repo].join(" ").toLowerCase().includes(query);
      });
      const visibleNodeIds = new Set();
      visibleEdges.forEach(edge => {
        visibleNodeIds.add(edge.source);
        visibleNodeIds.add(edge.target);
      });
      if (query) {
        graph.nodes.forEach(node => {
          if ([node.id, node.label, node.type, node.repo].join(" ").toLowerCase().includes(query)) {
            visibleNodeIds.add(node.id);
          }
        });
      }
      if (!query && visibleEdges.length === edges.length) {
        graph.nodes.forEach(node => visibleNodeIds.add(node.id));
      }

      const edgeMarkup = visibleEdges.map(edge => `
        <line class="edge${isHighlightedEdge(edge) ? " highlight" : ""}"
          x1="${edge.sourceNode.x}" y1="${edge.sourceNode.y}"
          x2="${edge.targetNode.x}" y2="${edge.targetNode.y}"
          data-edge="${escapeAttr(edge.id || "")}">
          <title>${escapeHtml(edge.predicate)}\n${escapeHtml(edge.source)} -> ${escapeHtml(edge.target)}</title>
        </line>
      `).join("");
      const nodeMarkup = graph.nodes.filter(node => visibleNodeIds.has(node.id)).map(node => `
        <g class="node${selected && selected.kind === "node" && selected.id === node.id ? " selected" : ""}" data-node="${escapeAttr(node.id)}">
          <circle cx="${node.x}" cy="${node.y}" r="${nodeRadius(node)}" fill="${colors[node.type] || colors.entity}">
            <title>${escapeHtml(node.id)}</title>
          </circle>
        </g>
        <text class="label" x="${node.x + nodeRadius(node) + 5}" y="${node.y + 4}">${escapeHtml(shortLabel(node.label))}</text>
      `).join("");

      svg.innerHTML = `<g transform="translate(${transform.x} ${transform.y}) scale(${transform.scale})">${edgeMarkup}${nodeMarkup}</g>`;
      svg.querySelectorAll("[data-node]").forEach(item => {
        item.addEventListener("click", event => {
          event.stopPropagation();
          selectNode(item.dataset.node);
        });
      });
      svg.querySelectorAll("[data-edge]").forEach(item => {
        item.addEventListener("click", event => {
          event.stopPropagation();
          selectEdge(item.dataset.edge);
        });
      });
    }

    function nodeRadius(node) {
      return Math.min(16, 7 + Math.sqrt(node.degree || 1) * 2.2);
    }

    function shortLabel(value) {
      return value.length > 42 ? value.slice(0, 39) + "..." : value;
    }

    function isHighlightedEdge(edge) {
      if (!selected) return false;
      if (selected.kind === "edge") return selected.id === edge.id;
      return edge.source === selected.id || edge.target === selected.id;
    }

    function selectNode(id) {
      const node = nodeById.get(id);
      selected = {kind: "node", id};
      const related = edges.filter(edge => edge.source === id || edge.target === id);
      details.className = "";
      details.innerHTML = `
        <div class="detail-title">${escapeHtml(node.label)}</div>
        <div class="kv"><span>Type</span><span>${escapeHtml(node.type)}</span></div>
        <div class="kv"><span>Repo</span><span>${escapeHtml(node.repo || "")}</span></div>
        <div class="kv"><span>ID</span><span>${escapeHtml(node.id)}</span></div>
        <h2>Related Facts</h2>
        ${related.slice(0, 40).map(renderFact).join("") || "<div class='empty'>No related facts.</div>"}
      `;
      draw();
    }

    function selectEdge(id) {
      const edge = edges.find(item => item.id === id);
      if (!edge) return;
      selected = {kind: "edge", id};
      details.className = "";
      details.innerHTML = `
        <div class="detail-title">${escapeHtml(edge.predicate)}</div>
        <div class="kv"><span>Source</span><span>${escapeHtml(edge.source)}</span></div>
        <div class="kv"><span>Target</span><span>${escapeHtml(edge.target)}</span></div>
        <div class="kv"><span>Repo</span><span>${escapeHtml(edge.repo || "")}</span></div>
        <div class="kv"><span>Confidence</span><span>${Math.round(edge.confidence * 100)}%</span></div>
        <h2>Evidence</h2>
        ${renderFact(edge)}
      `;
      draw();
    }

    function renderFact(edge) {
      const ev = edge.evidence;
      const location = ev ? `${ev.repo}/${ev.file}:${ev.line}` : "No evidence";
      const snippet = ev && ev.snippet ? ev.snippet : "";
      return `
        <div class="fact">
          <strong>${escapeHtml(edge.repo || "")} ${escapeHtml(edge.predicate)} ${escapeHtml(edge.target)}</strong>
          <code>${escapeHtml(location)}${snippet ? "\\n" + escapeHtml(snippet) : ""}</code>
        </div>
      `;
    }

    function fitGraph() {
      if (!graph.nodes.length) return;
      const xs = graph.nodes.map(node => node.x);
      const ys = graph.nodes.map(node => node.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const padding = 72;
      const scaleX = (width() - padding * 2) / Math.max(1, maxX - minX);
      const scaleY = (height() - padding * 2) / Math.max(1, maxY - minY);
      transform.scale = Math.min(1.6, Math.max(0.25, Math.min(scaleX, scaleY)));
      transform.x = width() / 2 - ((minX + maxX) / 2) * transform.scale;
      transform.y = height() / 2 - ((minY + maxY) / 2) * transform.scale;
      draw();
    }

    function resetGraph() {
      selected = null;
      search.value = "";
      enabledPredicates.clear();
      predicates.forEach(predicate => enabledPredicates.add(predicate));
      document.querySelectorAll("#predicates input").forEach(input => input.checked = true);
      transform = {x: 0, y: 0, scale: 1};
      initPositions();
      settleLayout();
      details.className = "empty";
      details.innerHTML = "Select a node or edge to inspect evidence.";
      fitGraph();
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => {
        switch (char) {
          case "&": return "&amp;";
          case "<": return "&lt;";
          case ">": return "&gt;";
          case '"': return "&quot;";
          case "'": return "&#39;";
          default: return char;
        }
      });
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    svg.addEventListener("click", () => {
      selected = null;
      details.className = "empty";
      details.innerHTML = "Select a node or edge to inspect evidence.";
      draw();
    });
    search.addEventListener("input", draw);
    fitButton.addEventListener("click", fitGraph);
    resetButton.addEventListener("click", resetGraph);
    window.addEventListener("resize", fitGraph);

    initPositions();
    renderFilters();
    settleLayout();
    fitGraph();
  </script>
</body>
</html>
"""
