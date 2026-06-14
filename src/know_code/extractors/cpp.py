from __future__ import annotations

import re
from pathlib import Path

from know_code.models import GraphFact
from know_code.repo import RepoContext, iter_source_files, read_text

from .base import Extractor
from .util import fact, make_evidence, normalize_operation


CMAKE_TARGET_RE = re.compile(
    r"\badd_(?P<kind>library|executable)\s*\(\s*(?P<body>[^)]*)\)",
    re.MULTILINE | re.DOTALL,
)
BAZEL_TARGET_RE = re.compile(
    r"\b(?P<kind>cc_library|cc_binary|cc_test)\s*\([^)]*?name\s*=\s*[\"'](?P<name>[A-Za-z0-9_.:-]+)[\"']",
    re.MULTILINE | re.DOTALL,
)
PUBLIC_CLASS_RE = re.compile(r"^\s*(?:class|struct)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
FUNCTION_DEF_RE = re.compile(
    r"^\s*"
    r"(?:(?:template\s*<[^;{}]+>\s*)|(?:extern\s+\"C\"\s+))?"
    r"(?:(?:static|inline|constexpr|virtual|extern|friend|explicit|LLAMA_API|GGML_API)\s+)*"
    r"(?:(?:[A-Za-z_][\w:<>,~*&\[\]\s]+?)\s+)?"
    r"(?P<name>(?:[A-Za-z_][A-Za-z0-9_]*::)*~?[A-Za-z_][A-Za-z0-9_]*)\s*"
    r"\([^;{}()]*\)\s*"
    r"(?:(?:const|noexcept|override|final)\s*)*"
    r"(?:\{|;)",
    re.MULTILINE,
)
CALL_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
CPP_KEYWORDS = {
    "alignas",
    "alignof",
    "catch",
    "delete",
    "for",
    "if",
    "new",
    "return",
    "sizeof",
    "static_assert",
    "switch",
    "throw",
    "while",
}
NOISY_FUNCTION_NAMES = {
    "append",
    "assert",
    "begin",
    "c_str",
    "clear",
    "data",
    "emplace",
    "emplace_back",
    "empty",
    "end",
    "erase",
    "find",
    "fprintf",
    "free",
    "insert",
    "malloc",
    "memcpy",
    "memset",
    "printf",
    "push_back",
    "reserve",
    "resize",
    "size",
    "snprintf",
    "std.runtime_error",
}
SYSTEM_FUNCTION_PREFIXES = (
    "CF",
    "Create",
    "Close",
    "Delete",
    "Dispatch",
    "Find",
    "Free",
    "Get",
    "Global",
    "Load",
    "Local",
    "Open",
    "Read",
    "Release",
    "Set",
    "Wait",
    "Write",
    "WSA",
)
SYSTEM_FUNCTION_NAMES = {
    "CloseHandle",
    "CloseServiceHandle",
    "CreateFileA",
    "CreateFileW",
    "DeleteFileA",
    "DeleteFileW",
    "DispatchMessage",
    "FindClose",
    "FreeEnvironmentStringsW",
    "FreeLibrary",
    "GetConsoleScreenBufferInfo",
    "GetCurrentThreadId",
    "GetErrorMessageWin32",
    "GetLastError",
    "GetModuleFileNameA",
    "GetModuleFileNameW",
    "GetProcAddress",
    "GetSystemInfo",
    "GlobalMemoryStatusEx",
    "LoadLibraryA",
    "LoadLibraryW",
    "LocalFree",
    "OpenServiceA",
    "OpenServiceW",
    "ReadFile",
    "ReleaseDC",
    "SetConsoleCtrlHandler",
    "SetConsoleOutputCP",
    "WaitForSingleObject",
    "WriteFile",
    "WSACleanup",
}
CMAKE_IGNORED_ARGS = {
    "ALIAS",
    "EXCLUDE_FROM_ALL",
    "IMPORTED",
    "INTERFACE",
    "OBJECT",
    "SHARED",
    "STATIC",
    "UNKNOWN",
    "WIN32",
    "MACOSX_BUNDLE",
}


class CppExtractor(Extractor):
    name = "cpp"

    def extract(self, context: RepoContext) -> list[GraphFact]:
        facts: list[GraphFact] = []
        files = iter_source_files(context.root)
        function_index = self._function_index(context, files)
        for path in files:
            text = read_text(path)
            if text is None:
                continue
            if path.name == "CMakeLists.txt":
                facts.extend(self._extract_cmake(context, path, text))
            elif path.name in {"BUILD", "BUILD.bazel"}:
                facts.extend(self._extract_bazel(context, path, text))
            elif path.suffix in CPP_SUFFIXES:
                facts.extend(self._extract_path_module(context, path, text))
                facts.extend(self._extract_functions(context, path, text))
                facts.extend(self._extract_function_calls(context, path, text, function_index))
            if path.suffix in {".h", ".hpp", ".hh", ".hxx"}:
                facts.extend(self._extract_public_headers(context, path, text))
        return facts

    def _extract_path_module(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        module_name = cpp_path_module_name(context, path)
        if module_name is None:
            return []
        evidence = make_evidence(context, path, text, 0)
        return [
            fact(
                context,
                f"repo:{context.name}:file:{context.relative(path)}",
                "belongs_to_module",
                f"module:{context.name}:{module_name}",
                evidence,
                0.62,
                self.name,
                {"module_kind": "path", "language": "cpp"},
                self.version,
            )
        ]

    def _extract_cmake(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in CMAKE_TARGET_RE.finditer(text):
            name, source_files = parse_cmake_target(match.group("body"))
            if name is None:
                continue
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            module = f"module:{context.name}:{name}"
            facts.append(
                fact(
                    context,
                    subject,
                    "defines_module",
                    module,
                    evidence,
                    0.84,
                    self.name,
                    {"build_system": "cmake", "target_kind": match.group("kind")},
                    self.version,
                )
            )
            for source_file in source_files:
                resolved = resolve_cmake_source(context, path, source_file)
                if resolved is None:
                    continue
                facts.append(
                    fact(
                        context,
                        f"repo:{context.name}:file:{resolved}",
                        "belongs_to_module",
                        module,
                        evidence,
                        0.74,
                        self.name,
                        {"build_system": "cmake", "target_kind": match.group("kind"), "declared_in": context.relative(path)},
                        self.version,
                    )
                )
        return facts

    def _extract_bazel(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in BAZEL_TARGET_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "defines_module",
                    f"module:{context.name}:{match.group('name')}",
                    evidence,
                    0.84,
                    self.name,
                    {"build_system": "bazel", "target_kind": match.group("kind")},
                    self.version,
                )
            )
        return facts

    def _extract_public_headers(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        for match in PUBLIC_CLASS_RE.finditer(text):
            evidence = make_evidence(context, path, text, match.start())
            subject = f"repo:{context.name}:file:{context.relative(path)}"
            facts.append(
                fact(
                    context,
                    subject,
                    "defines_interface",
                    f"interface:{context.name}:{match.group('name')}",
                    evidence,
                    0.72,
                    self.name,
                    {"language": "cpp"},
                    self.version,
                )
            )
        return facts

    def _function_index(self, context: RepoContext, files: list[Path]) -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}
        for path in files:
            if path.suffix not in CPP_SUFFIXES:
                continue
            text = read_text(path)
            if text is None:
                continue
            for match in FUNCTION_DEF_RE.finditer(strip_cpp_comments(text)):
                name = normalize_cpp_function_name(match.group("name"))
                if not should_keep_function(name):
                    continue
                short_name = name.rsplit(".", 1)[-1]
                index.setdefault(short_name, set()).add(name)
        return index

    def _extract_functions(self, context: RepoContext, path, text: str) -> list[GraphFact]:
        facts: list[GraphFact] = []
        stripped = strip_cpp_comments(text)
        seen: set[str] = set()
        for match in FUNCTION_DEF_RE.finditer(stripped):
            name = normalize_cpp_function_name(match.group("name"))
            if not should_keep_function(name) or name in seen:
                continue
            seen.add(name)
            evidence = make_evidence(context, path, text, match.start())
            facts.append(
                fact(
                    context,
                    f"repo:{context.name}:file:{context.relative(path)}",
                    "provides_operation",
                    normalize_operation(f"cpp.{name}"),
                    evidence,
                    0.68,
                    self.name,
                    {"language": "cpp", "operation_kind": "function"},
                    self.version,
                )
            )
        return facts

    def _extract_function_calls(
        self,
        context: RepoContext,
        path,
        text: str,
        function_index: dict[str, set[str]],
    ) -> list[GraphFact]:
        facts: list[GraphFact] = []
        stripped = strip_cpp_comments(text)
        seen: set[str] = set()
        for match in CALL_RE.finditer(stripped):
            short_name = match.group("name")
            if short_name in CPP_KEYWORDS or short_name not in function_index:
                continue
            target_names = sorted(function_index[short_name])
            if len(target_names) > 3:
                continue
            for name in target_names:
                if name in seen:
                    continue
                seen.add(name)
                evidence = make_evidence(context, path, text, match.start())
                facts.append(
                    fact(
                        context,
                        f"repo:{context.name}:file:{context.relative(path)}",
                        "calls_operation",
                        normalize_operation(f"cpp.{name}"),
                        evidence,
                        0.52,
                        self.name,
                        {"language": "cpp", "operation_kind": "function_call"},
                        self.version,
                    )
                )
            if len(seen) >= 120:
                break
        return facts


def parse_cmake_target(body: str) -> tuple[str | None, list[str]]:
    tokens = re.findall(r'"([^"]+)"|([A-Za-z0-9_./${}:+-]+)', body)
    values = [quoted or plain for quoted, plain in tokens]
    if not values:
        return None, []
    name = values[0]
    if "$" in name:
        return None, []
    sources = [
        value
        for value in values[1:]
        if value not in CMAKE_IGNORED_ARGS and Path(value).suffix.lower() in CPP_SUFFIXES
    ]
    return name, sources


def resolve_cmake_source(context: RepoContext, cmake_path: Path, source_file: str) -> str | None:
    if "$" in source_file:
        return None
    resolved = (cmake_path.parent / source_file).resolve()
    try:
        return str(resolved.relative_to(context.root))
    except ValueError:
        return None


def strip_cpp_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.DOTALL)
    return re.sub(r"//.*", "", text)


def normalize_cpp_function_name(name: str) -> str:
    return name.replace("::", ".").strip(".")


def should_keep_function(name: str) -> bool:
    short_name = name.rsplit(".", 1)[-1]
    if short_name in CPP_KEYWORDS or short_name in NOISY_FUNCTION_NAMES or name in NOISY_FUNCTION_NAMES:
        return False
    if is_system_function(short_name):
        return False
    if short_name.startswith("operator") or short_name.isupper():
        return False
    if len(short_name) < 3 and short_name != "run":
        return False
    return True


def is_system_function(short_name: str) -> bool:
    if short_name in SYSTEM_FUNCTION_NAMES:
        return True
    if short_name.startswith(("__builtin_", "_mm_", "_aligned_", "cl", "vk")):
        return True
    return any(short_name.startswith(prefix) and len(short_name) > len(prefix) + 2 for prefix in SYSTEM_FUNCTION_PREFIXES)


def cpp_path_module_name(context: RepoContext, path: Path) -> str | None:
    relative = Path(context.relative(path))
    parts = relative.parts
    if not parts:
        return None
    first = parts[0]
    if first in {"examples", "pocs", "tools"} and len(parts) >= 2:
        return f"{first}/{parts[1]}"
    if first == "ggml" and len(parts) >= 3:
        return f"ggml/{parts[1]}"
    if first in {"app", "common", "include", "src", "tests"}:
        return first
    return first if len(parts) > 1 else None
