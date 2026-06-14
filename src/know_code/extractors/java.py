from __future__ import annotations

import re

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence, normalize_api


SPRING_MAPPING_RE = re.compile(
    r"@(?P<kind>Get|Post|Put|Delete|Patch|Request)Mapping"
    r"\s*(?:\(\s*(?:value\s*=\s*)?(?P<quote>[\"'])?(?P<path>/[^\"'){},\s]+))?",
    re.MULTILINE,
)
RETROFIT_RE = re.compile(
    r"@(?P<method>GET|POST|PUT|DELETE|PATCH)\s*\(\s*[\"'](?P<path>/[^\"']*)[\"']",
    re.MULTILINE,
)
KAFKA_CONSUME_RE = re.compile(
    r"@KafkaListener\s*\([^)]*topics\s*=\s*(?:\{)?\s*[\"'](?P<topic>[^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)
KAFKA_EMIT_RE = re.compile(
    r"\.send\s*\(\s*[\"'](?P<topic>[A-Za-z0-9_.:-]+)[\"']",
    re.MULTILINE,
)


class JavaKotlinExtractor(Extractor):
    name = "java-kotlin"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for path in iter_source_files(context.root):
            if path.suffix not in {".java", ".kt", ".kts"}:
                continue
            text = read_text(path)
            if text is None:
                continue
            facts.extend(self._extract_spring(context, path, text))
            facts.extend(self._extract_retrofit(context, path, text))
            facts.extend(self._extract_kafka(context, path, text))
        return facts

    def _extract_spring(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in SPRING_MAPPING_RE.finditer(text):
            path_value = match.group("path")
            if not path_value:
                continue
            kind = match.group("kind")
            method = "ANY" if kind == "Request" else kind.upper()
            if method == "GET":
                method = "GET"
            elif method == "POST":
                method = "POST"
            elif method == "PUT":
                method = "PUT"
            elif method == "DELETE":
                method = "DELETE"
            elif method == "PATCH":
                method = "PATCH"
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "provides_api",
                    normalize_api(method, path_value),
                    evidence,
                    0.9,
                    self.name,
                    {"framework": "spring"},
                    self.version,
                )
            )
        return facts

    def _extract_retrofit(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in RETROFIT_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "calls_api",
                    normalize_api(match.group("method"), match.group("path")),
                    evidence,
                    0.88,
                    self.name,
                    {"framework": "retrofit"},
                    self.version,
                )
            )
        return facts

    def _extract_kafka(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in KAFKA_CONSUME_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "consumes_event",
                    f"event:{match.group('topic')}",
                    evidence,
                    0.88,
                    self.name,
                    {"framework": "kafka"},
                    self.version,
                )
            )
        for match in KAFKA_EMIT_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "emits_event",
                    f"event:{match.group('topic')}",
                    evidence,
                    0.62,
                    self.name,
                    {"framework": "kafka"},
                    self.version,
                )
            )
        return facts

