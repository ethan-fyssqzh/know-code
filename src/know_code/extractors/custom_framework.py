from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence, normalize_api, normalize_operation


SUPPORTED_SUFFIXES = {
    ".java",
    ".kt",
    ".kts",
    ".swift",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
}


@dataclass(frozen=True)
class CustomFrameworkConfig:
    name: str
    provider_annotations: dict[str, str]
    client_call_regexes: list[str]
    provider_call_regexes: list[str]
    endpoint_mapping_regexes: list[str]


class CustomFrameworkExtractor(Extractor):
    version = "0.1.0"

    def __init__(self, config: CustomFrameworkConfig) -> None:
        self.config = config
        self.name = config.name
        self._client_patterns = [re.compile(item) for item in config.client_call_regexes]
        self._provider_patterns = [re.compile(item) for item in config.provider_call_regexes]
        self._endpoint_patterns = [re.compile(item) for item in config.endpoint_mapping_regexes]

    def extract(self, context: RepoContext) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for path in iter_source_files(context.root):
            if path.suffix not in SUPPORTED_SUFFIXES:
                continue
            text = read_text(path)
            if text is None:
                continue
            facts.extend(self._extract_annotation_provider(context, path, text))
            facts.extend(self._extract_regex_facts(context, path, text))
        return facts

    def _extract_annotation_provider(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        annotations = self.config.provider_annotations
        service_annotation = annotations.get("service")
        action_annotation = annotations.get("action")
        if not service_annotation or not action_annotation:
            return []

        service_re = re.compile(rf"@{re.escape(service_annotation)}\s*\(\s*[\"'](?P<name>[^\"']+)[\"']")
        action_re = re.compile(rf"@{re.escape(action_annotation)}\s*\(\s*[\"'](?P<name>[^\"']+)[\"']")
        service_match = service_re.search(text)
        if service_match is None:
            return []

        service = service_match.group("name")
        facts: list[GraphFact] = []
        for action_match in action_re.finditer(text):
            operation = normalize_operation(f"{service}.{action_match.group('name')}")
            evidence = make_evidence(context, path, text, action_match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "provides_operation",
                    operation,
                    evidence,
                    0.94,
                    self.name,
                    {
                        "service": service,
                        "action": action_match.group("name"),
                        "adapter": self.name,
                    },
                    self.version,
                )
            )
        return facts

    def _extract_regex_facts(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for pattern in self._client_patterns:
            for match in pattern.finditer(text):
                operation = normalize_operation(match.group("operation"))
                evidence = make_evidence(context, path, text, match.start())
                subject = f"repo:{context.name}:file:{context.relative(path)}"
                facts.append(
                    fact(
                        context,
                        subject,
                        "calls_operation",
                        operation,
                        evidence,
                        0.88,
                        self.name,
                        {"adapter": self.name},
                        self.version,
                    )
                )
        for pattern in self._provider_patterns:
            for match in pattern.finditer(text):
                operation = normalize_operation(match.group("operation"))
                evidence = make_evidence(context, path, text, match.start())
                subject = f"repo:{context.name}:file:{context.relative(path)}"
                facts.append(
                    fact(
                        context,
                        subject,
                        "provides_operation",
                        operation,
                        evidence,
                        0.88,
                        self.name,
                        {"adapter": self.name},
                        self.version,
                    )
                )
        for pattern in self._endpoint_patterns:
            for match in pattern.finditer(text):
                operation = normalize_operation(match.group("operation"))
                api = normalize_api(match.group("method"), match.group("path"))
                evidence = make_evidence(context, path, text, match.start())
                facts.append(
                    fact(
                        context,
                        operation,
                        "maps_operation_to_api",
                        api,
                        evidence,
                        0.86,
                        self.name,
                        {"adapter": self.name},
                        self.version,
                    )
                )
        return facts


def load_custom_extractors(path: Path | None) -> list[CustomFrameworkExtractor]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    extractors: list[CustomFrameworkExtractor] = []
    for item in payload.get("adapters", []):
        config = CustomFrameworkConfig(
            name=str(item["name"]),
            provider_annotations=dict(item.get("provider_annotations", {})),
            client_call_regexes=list(item.get("client_call_regexes", [])),
            provider_call_regexes=list(item.get("provider_call_regexes", [])),
            endpoint_mapping_regexes=list(item.get("endpoint_mapping_regexes", [])),
        )
        extractors.append(CustomFrameworkExtractor(config))
    return extractors

