from __future__ import annotations

import re

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence, normalize_api


AXIOS_RE = re.compile(
    r"\b(?:axios|request|http|client)\.(?P<method>get|post|put|patch|delete)"
    r"\s*\(\s*[`\"'](?P<path>/[^`\"']+)[`\"']",
    re.MULTILINE,
)
FETCH_RE = re.compile(
    r"\bfetch\s*\(\s*[`\"'](?P<path>/[^`\"']+)[`\"']"
    r"(?P<options>[^)]*)\)",
    re.MULTILINE | re.DOTALL,
)
ROUTE_RE = re.compile(
    r"(?:path\s*[:=]\s*|<Route[^>]*\spath=)[`\"'](?P<path>/[^`\"']*)[`\"']",
    re.MULTILINE,
)


class WebExtractor(Extractor):
    name = "web"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for path in iter_source_files(context.root):
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".vue"}:
                continue
            text = read_text(path)
            if text is None:
                continue
            facts.extend(self._extract_api_calls(context, path, text))
            facts.extend(self._extract_routes(context, path, text))
        return facts

    def _extract_api_calls(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in AXIOS_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "calls_api",
                    normalize_api(match.group("method"), match.group("path")),
                    evidence,
                    0.84,
                    self.name,
                    {"framework": "web-http-client"},
                    self.version,
                )
            )
        for match in FETCH_RE.finditer(text):
            options = match.group("options")
            method_match = re.search(r"method\s*:\s*[`\"'](?P<method>[A-Za-z]+)[`\"']", options)
            method = method_match.group("method") if method_match else "GET"
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "calls_api",
                    normalize_api(method, match.group("path")),
                    evidence,
                    0.78,
                    self.name,
                    {"framework": "fetch"},
                    self.version,
                )
            )
        return facts

    def _extract_routes(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in ROUTE_RE.finditer(text):
            route = match.group("path")
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "defines_route",
                    f"route:{context.name}:{route}",
                    evidence,
                    0.78,
                    self.name,
                    {"platform": "h5"},
                    self.version,
                )
            )
        return facts

