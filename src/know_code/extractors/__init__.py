from .base import Extractor
from .cpp import CppExtractor
from .custom_framework import CustomFrameworkExtractor, load_custom_extractors
from .electron_trpc import ElectronTrpcExtractor
from .generic import GenericRepoExtractor
from .ios import IOSExtractor
from .java import JavaKotlinExtractor
from .protobuf import ProtobufExtractor
from .web import WebExtractor


def default_extractors() -> list[Extractor]:
    return [
        GenericRepoExtractor(),
        CppExtractor(),
        ElectronTrpcExtractor(),
        JavaKotlinExtractor(),
        ProtobufExtractor(),
        WebExtractor(),
        IOSExtractor(),
    ]


__all__ = [
    "CustomFrameworkExtractor",
    "CppExtractor",
    "ElectronTrpcExtractor",
    "Extractor",
    "GenericRepoExtractor",
    "IOSExtractor",
    "JavaKotlinExtractor",
    "ProtobufExtractor",
    "WebExtractor",
    "default_extractors",
    "load_custom_extractors",
]
