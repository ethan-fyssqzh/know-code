from __future__ import annotations

import re

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence, normalize_api


VIEW_RE = re.compile(
    r"(?:class|struct)\s+(?P<name>[A-Za-z0-9_]*(?:ViewController|View|Screen))\b",
    re.MULTILINE,
)
URLSESSION_RE = re.compile(
    r"URL\s*\(\s*string\s*:\s*[\"'](?P<path>/[^\"']+|https?://[^\"']+)[\"']",
    re.MULTILINE,
)
ALAMOFIRE_RE = re.compile(
    r"(?:AF|Alamofire)\.request\s*\(\s*[\"'](?P<path>/[^\"']+|https?://[^\"']+)[\"']"
    r"(?P<options>[^)]*)\)",
    re.MULTILINE | re.DOTALL,
)


class IOSExtractor(Extractor):
    name = "ios"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for path in iter_source_files(context.root):
            if path.suffix != ".swift":
                continue
            text = read_text(path)
            if text is None:
                continue
            facts.extend(self._extract_views(context, path, text))
            facts.extend(self._extract_http(context, path, text))
        return facts

    def _extract_views(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in VIEW_RE.finditer(text):
            name = match.group("name")
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "defines_screen",
                    f"screen:{context.name}:{name}",
                    evidence,
                    0.76,
                    self.name,
                    {"platform": "ios"},
                    self.version,
                )
            )
        return facts

    def _extract_http(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in URLSESSION_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "calls_api",
                    normalize_api("GET", path_only(match.group("path"))),
                    evidence,
                    0.62,
                    self.name,
                    {"framework": "urlsession"},
                    self.version,
                )
            )
        for match in ALAMOFIRE_RE.finditer(text):
            method_match = re.search(r"method\s*:\s*\.(?P<method>[A-Za-z]+)", match.group("options"))
            method = method_match.group("method") if method_match else "GET"
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "calls_api",
                    normalize_api(method, path_only(match.group("path"))),
                    evidence,
                    0.74,
                    self.name,
                    {"framework": "alamofire"},
                    self.version,
                )
            )
        return facts


def path_only(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        without_scheme = value.split("://", 1)[1]
        slash = without_scheme.find("/")
        return without_scheme[slash:] if slash >= 0 else "/"
    return value

