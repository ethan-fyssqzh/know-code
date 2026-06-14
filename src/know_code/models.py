from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


SOURCE_VERSION = "0.1.0"


@dataclass(frozen=True)
class Evidence:
    repo: str
    commit: str
    file: str
    line: int
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "commit": self.commit,
            "file": self.file,
            "line": self.line,
            "snippet": self.snippet,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        return cls(
            repo=str(data.get("repo", "")),
            commit=str(data.get("commit", "")),
            file=str(data.get("file", "")),
            line=int(data.get("line", 0)),
            snippet=str(data.get("snippet", "")),
        )


@dataclass
class GraphFact:
    subject: str
    predicate: str
    object: str
    evidence: list[Evidence]
    confidence: float
    source: str
    repo: str
    commit: str
    attributes: dict[str, Any] = field(default_factory=dict)
    source_version: str = SOURCE_VERSION
    valid_from: str | None = None
    valid_until: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if self.valid_from is None:
            self.valid_from = self.commit
        if self.id is None:
            self.id = make_fact_id(
                self.subject,
                self.predicate,
                self.object,
                self.source,
                self.source_version,
                self.attributes,
                self.evidence,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "attributes": self.attributes,
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "source": self.source,
            "source_version": self.source_version,
            "repo": self.repo,
            "commit": self.commit,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
        }

    def content_fingerprint(self) -> str:
        payload = self.to_dict()
        payload.pop("valid_from", None)
        payload.pop("valid_until", None)
        payload.pop("commit", None)
        for item in payload.get("evidence", []):
            item.pop("commit", None)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphFact":
        return cls(
            id=str(data["id"]),
            subject=str(data["subject"]),
            predicate=str(data["predicate"]),
            object=str(data["object"]),
            attributes=dict(data.get("attributes", {})),
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
            confidence=float(data.get("confidence", 0.0)),
            source=str(data.get("source", "")),
            source_version=str(data.get("source_version", SOURCE_VERSION)),
            repo=str(data.get("repo", "")),
            commit=str(data.get("commit", "")),
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
        )


def make_fact_id(
    subject: str,
    predicate: str,
    object_: str,
    source: str,
    source_version: str,
    attributes: dict[str, Any],
    evidence: list[Evidence],
) -> str:
    stable_evidence = [
        {
            "repo": item.repo,
            "file": item.file,
            "line": item.line,
            "snippet": item.snippet.strip(),
        }
        for item in evidence
    ]
    payload = {
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "source": source,
        "source_version": source_version,
        "attributes": attributes,
        "evidence": stable_evidence,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return "fact_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]

