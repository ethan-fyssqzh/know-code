from __future__ import annotations

import re

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence


PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;", re.MULTILINE)
SERVICE_RE = re.compile(r"service\s+(?P<service>[A-Za-z0-9_]+)\s*\{(?P<body>.*?)\}", re.DOTALL)
RPC_RE = re.compile(
    r"rpc\s+(?P<method>[A-Za-z0-9_]+)\s*"
    r"\(\s*(?P<request>[A-Za-z0-9_.]+)\s*\)\s*"
    r"returns\s*\(\s*(?P<response>[A-Za-z0-9_.]+)\s*\)",
    re.MULTILINE,
)
MESSAGE_RE = re.compile(r"^\s*message\s+(?P<message>[A-Za-z0-9_]+)\s*\{", re.MULTILINE)


class ProtobufExtractor(Extractor):
    name = "protobuf"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for path in iter_source_files(context.root):
            if path.suffix != ".proto":
                continue
            text = read_text(path)
            if text is None:
                continue
            facts.extend(self._extract_proto(context, path, text))
        return facts

    def _extract_proto(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        package_match = PACKAGE_RE.search(text)
        package = package_match.group(1) if package_match else ""
        for match in MESSAGE_RE.finditer(text):
            name = qualified(package, match.group("message"))
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "defines_schema",
                    f"schema:{name}",
                    evidence,
                    0.95,
                    self.name,
                    {"format": "protobuf"},
                    self.version,
                )
            )
        for service_match in SERVICE_RE.finditer(text):
            service = qualified(package, service_match.group("service"))
            body = service_match.group("body")
            body_offset = service_match.start("body")
            for rpc_match in RPC_RE.finditer(body):
                method = rpc_match.group("method")
                rpc = f"rpc:{service}.{method}"
                evidence = make_evidence(context, path, text, body_offset + rpc_match.start())
                subject = f"repo:{context.name}:proto-service:{service}"
                facts.append(
                    fact(
                        context,
                        subject,
                        "provides_rpc",
                        rpc,
                        evidence,
                        0.96,
                        self.name,
                        {
                            "request": qualified(package, rpc_match.group("request")),
                            "response": qualified(package, rpc_match.group("response")),
                        },
                        self.version,
                    )
                )
        return facts


def qualified(package: str, name: str) -> str:
    if "." in name or not package:
        return name
    return f"{package}.{name}"

