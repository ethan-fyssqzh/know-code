from __future__ import annotations

from collections import Counter
from pathlib import Path

from know_code.models import Evidence, GraphFact
from know_code.repo import RepoContext, iter_source_files

from .base import Extractor


LANGUAGE_BY_SUFFIX = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".h": "cpp",
    ".mm": "objcxx",
    ".m": "objc",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".proto": "protobuf",
}


BUILD_FILES = {
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "CMakeLists.txt": "cmake",
    "WORKSPACE": "bazel",
    "BUILD": "bazel",
    "package.json": "npm",
    "Podfile": "cocoapods",
    "Package.swift": "swiftpm",
    "project.pbxproj": "xcode",
}


class GenericRepoExtractor(Extractor):
    name = "generic-repo"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        files = iter_source_files(context.root)
        counts = Counter(
            LANGUAGE_BY_SUFFIX[path.suffix]
            for path in files
            if path.suffix in LANGUAGE_BY_SUFFIX
        )
        facts: list[GraphFact] = []
        repo_entity = f"repo:{context.name}"
        evidence = Evidence(
            repo=context.name,
            commit=context.commit,
            file=".",
            line=1,
            snippet=f"Repository root: {context.root}",
        )
        facts.append(
            GraphFact(
                subject=repo_entity,
                predicate="is_repository",
                object=repo_entity,
                evidence=[evidence],
                confidence=1.0,
                source=self.name,
                source_version=self.version,
                repo=context.name,
                commit=context.commit,
                attributes={"path": str(context.root)},
            )
        )
        for language, count in sorted(counts.items()):
            facts.append(
                GraphFact(
                    subject=repo_entity,
                    predicate="has_language",
                    object=f"language:{language}",
                    evidence=[evidence],
                    confidence=0.98,
                    source=self.name,
                    source_version=self.version,
                    repo=context.name,
                    commit=context.commit,
                    attributes={"file_count": count},
                )
            )
        for path in files:
            build_system = BUILD_FILES.get(path.name)
            if build_system is None:
                continue
            facts.append(self._build_fact(context, path, build_system))
        return facts

    def _build_fact(self, context: RepoContext, path: Path, build_system: str) -> GraphFact:
        evidence = Evidence(
            repo=context.name,
            commit=context.commit,
            file=context.relative(path),
            line=1,
            snippet=f"Build file: {path.name}",
        )
        return GraphFact(
            subject=f"repo:{context.name}",
            predicate="uses_build_system",
            object=f"build:{build_system}",
            evidence=[evidence],
            confidence=0.98,
            source=self.name,
            source_version=self.version,
            repo=context.name,
            commit=context.commit,
        )

