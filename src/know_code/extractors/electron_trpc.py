from __future__ import annotations

import re

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence, normalize_operation


TS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
IPC_MAIN_HANDLE_RE = re.compile(r"\bipcMain\.handle\s*\(\s*[`\"'](?P<channel>[^`\"']+)[`\"']", re.MULTILINE)
IPC_RENDERER_INVOKE_RE = re.compile(r"\bipcRenderer\.invoke\s*\(\s*[`\"'](?P<channel>[^`\"']+)[`\"']", re.MULTILINE)
DESKTOP_API_RE = re.compile(
    r"(?P<method>[A-Za-z0-9_]+)\s*:\s*(?:\([^)]*\)\s*=>|async\s*\([^)]*\)\s*=>)"
    r"(?P<body>.{0,260}?)ipcRenderer\.invoke\s*\(\s*[`\"'](?P<channel>[^`\"']+)[`\"']",
    re.MULTILINE | re.DOTALL,
)
TRPC_CALL_RE = re.compile(
    r"\b(?:trpc|trpcClient|remoteTrpc)\.(?P<path>[A-Za-z0-9_$.]+?)"
    r"\.(?:useQuery|useMutation|query|mutation)\s*\(",
    re.MULTILINE,
)
ROUTER_VAR_RE = re.compile(r"\b(?:export\s+)?const\s+(?P<name>[A-Za-z0-9_]+Router)\s*=\s*router\s*\(")
ROUTER_FACTORY_RE = re.compile(
    r"\b(?:export\s+)?const\s+(?P<name>create[A-Za-z0-9_]+Router)\s*=\s*\([^)]*\)\s*=>\s*\{?\s*return\s+router\s*\(",
    re.MULTILINE,
)
PROCEDURE_RE = re.compile(
    r"(?P<name>[A-Za-z0-9_]+)\s*:\s*(?:publicProcedure|loggedProcedure|protectedProcedure)"
    r"(?P<body>.*?)(?:\.(?P<kind>query|mutation|subscription)\s*\()",
    re.MULTILINE | re.DOTALL,
)
ROUTER_ALIAS_RE = re.compile(
    r"(?P<alias>[A-Za-z0-9_]+)\s*:\s*(?P<target>[A-Za-z0-9_]+Router|create[A-Za-z0-9_]+Router)\s*(?:\(\s*\))?",
    re.MULTILINE,
)
ROUTER_SPREAD_RE = re.compile(r"\.\.\.(?P<target>create[A-Za-z0-9_]+Router)\s*\(\s*\)\._def\.procedures")
COMPONENT_RE = re.compile(
    r"\b(?:export\s+)?(?:function|const)\s+(?P<name>[A-Z][A-Za-z0-9_]*)\b",
    re.MULTILINE,
)


class ElectronTrpcExtractor(Extractor):
    name = "electron-trpc"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        router_aliases = self._collect_router_aliases(context)
        facts: list[GraphFact] = []
        for path in iter_source_files(context.root):
            if path.suffix not in TS_SUFFIXES:
                continue
            text = read_text(path)
            if text is None:
                continue
            surface = surface_for_path(context, path, text)
            facts.extend(self._extract_feature_surface(context, path, text, surface))
            facts.extend(self._extract_ipc(context, path, text))
            facts.extend(self._extract_desktop_api(context, path, text))
            facts.extend(self._extract_trpc_calls(context, path, text, surface))
            facts.extend(self._extract_trpc_providers(context, path, text, router_aliases))
        return facts

    def _extract_ipc(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in IPC_MAIN_HANDLE_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            channel = match.group("channel")
            facts.append(
                fact(
                    context,
                    subject,
                    "provides_operation",
                    normalize_operation(f"ipc.{channel}"),
                    evidence,
                    0.92,
                    self.name,
                    {"transport": "electron-ipc", "channel": channel},
                    self.version,
                )
            )
        for match in IPC_RENDERER_INVOKE_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            channel = match.group("channel")
            facts.append(
                fact(
                    context,
                    subject,
                    "calls_operation",
                    normalize_operation(f"ipc.{channel}"),
                    evidence,
                    0.92,
                    self.name,
                    {"transport": "electron-ipc", "channel": channel},
                    self.version,
                )
            )
        return facts

    def _extract_desktop_api(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in DESKTOP_API_RE.finditer(text):
            method = match.group("method")
            channel = match.group("channel")
            desktop_operation = normalize_operation(f"desktopApi.{method}")
            ipc_operation = normalize_operation(f"ipc.{channel}")
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "provides_operation",
                    desktop_operation,
                    evidence,
                    0.8,
                    self.name,
                    {"transport": "electron-preload", "method": method},
                    self.version,
                )
            )
            facts.append(
                fact(
                    context,
                    desktop_operation,
                    "maps_operation_to_operation",
                    ipc_operation,
                    evidence,
                    0.84,
                    self.name,
                    {"transport": "electron-preload", "method": method, "channel": channel},
                    self.version,
                )
            )
        return facts

    def _extract_trpc_calls(
        self,
        context: RepoContext,
        path,
        text: str,
        surface: str | None,
    ) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in TRPC_CALL_RE.finditer(text):
            trpc_path = match.group("path").replace("$", ".")
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            operation = normalize_operation(f"trpc.{trpc_path}")
            attributes = {"transport": "trpc", "path": trpc_path}
            facts.append(
                fact(context, subject, "calls_operation", operation, evidence, 0.82, self.name, attributes, self.version)
            )
            if surface is not None:
                facts.append(
                    fact(
                        context,
                        surface,
                        "calls_operation",
                        operation,
                        evidence,
                        0.72,
                        self.name,
                        attributes | {"via_file": context.relative(path)},
                        self.version,
                    )
                )
        return facts

    def _extract_trpc_providers(
        self,
        context: RepoContext,
        path,
        text: str,
        router_aliases: dict[str, str],
    ) -> list[GraphFact]:
        router_match = ROUTER_VAR_RE.search(text) or ROUTER_FACTORY_RE.search(text)
        if router_match is None:
            return []
        raw_router_name = router_match.group("name")
        router_name = router_aliases.get(raw_router_name, strip_router_suffix(raw_router_name))
        facts: list[GraphFact] = []
        for match in PROCEDURE_RE.finditer(text):
            procedure = match.group("name")
            kind = match.group("kind")
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "provides_operation",
                    normalize_operation(f"trpc.{router_name}.{procedure}"),
                    evidence,
                    0.78,
                    self.name,
                    {"transport": "trpc", "router": router_name, "procedure": procedure, "kind": kind},
                    self.version,
                )
            )
        return facts

    def _extract_feature_surface(
        self,
        context: RepoContext,
        path,
        text: str,
        surface: str | None,
    ) -> list[GraphFact]:
        facts: list[GraphFact] = []
        relative = context.relative(path)
        feature = feature_for_path(relative)
        if feature is not None:
            evidence = make_evidence(context, path, text, 0)
            facts.append(
                fact(
                    context,
                    f"repo:{context.name}",
                    "defines_module",
                    f"module:{context.name}:{feature}",
                    evidence,
                    0.72,
                    self.name,
                    {"module_kind": "feature"},
                    self.version,
                )
            )
            facts.append(
                fact(
                    context,
                    f"repo:{context.name}:file:{relative}",
                    "belongs_to_module",
                    f"module:{context.name}:{feature}",
                    evidence,
                    0.76,
                    self.name,
                    {"module_kind": "feature"},
                    self.version,
                )
            )
        if surface is not None:
            evidence = make_evidence(context, path, text, 0)
            facts.append(
                fact(
                    context,
                    f"repo:{context.name}:file:{relative}",
                    "defines_screen",
                    surface,
                    evidence,
                    0.7,
                    self.name,
                    {"surface_kind": "react-component", "feature": feature},
                    self.version,
                )
            )
            if feature is not None:
                facts.append(
                    fact(
                        context,
                        surface,
                        "belongs_to_module",
                        f"module:{context.name}:{feature}",
                        evidence,
                        0.7,
                        self.name,
                        {"module_kind": "feature"},
                        self.version,
                    )
                )
        return facts

    def _collect_router_aliases(self, context: RepoContext) -> dict[str, str]:
        aliases: dict[str, str] = {}
        flattened_children: dict[str, set[str]] = {}
        for path in iter_source_files(context.root):
            if path.suffix not in TS_SUFFIXES:
                continue
            text = read_text(path)
            if text is None or "router({" not in text:
                continue
            factory_match = ROUTER_FACTORY_RE.search(text)
            if factory_match is not None:
                parent = factory_match.group("name")
                flattened_children[parent] = {
                    match.group("target") for match in ROUTER_SPREAD_RE.finditer(text)
                }
            for match in ROUTER_ALIAS_RE.finditer(text):
                aliases[match.group("target")] = match.group("alias")
        changed = True
        while changed:
            changed = False
            for parent, children in flattened_children.items():
                parent_alias = aliases.get(parent)
                if parent_alias is None:
                    continue
                for child in children:
                    if aliases.get(child) != parent_alias:
                        aliases[child] = parent_alias
                        changed = True
        return aliases


def strip_router_suffix(value: str) -> str:
    value = value.removeprefix("create").removesuffix("Router")
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value:
        return value[:1].lower() + value[1:]
    return value


def feature_for_path(relative: str) -> str | None:
    marker = "src/renderer/features/"
    if not relative.startswith(marker):
        return None
    rest = relative.removeprefix(marker)
    parts = rest.split("/")
    if not parts:
        return None
    return parts[0]


def surface_for_path(context: RepoContext, path, text: str) -> str | None:
    relative = context.relative(path)
    if path.suffix not in {".tsx", ".jsx"}:
        return None
    feature = feature_for_path(relative)
    name = None
    for component_match in COMPONENT_RE.finditer(text):
        candidate = component_match.group("name")
        if is_likely_component_name(candidate):
            name = candidate
            break
    if name is None:
        stem = path.stem
        fallback = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", stem) if part)
        name = fallback if is_likely_component_name(fallback) else None
    if not name:
        return None
    if feature is not None:
        return f"screen:{context.name}:{feature}.{name}"
    return f"screen:{context.name}:{name}"


def is_likely_component_name(name: str) -> bool:
    if "_" in name:
        return False
    if name.isupper():
        return False
    if not re.search(r"[a-z]", name):
        return False
    ignored_suffixes = ("Props", "State", "Config", "Options", "Params", "Result")
    return not name.endswith(ignored_suffixes)
