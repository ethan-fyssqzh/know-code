from __future__ import annotations

from abc import ABC, abstractmethod

from know_code.models import GraphFact
from know_code.repo import RepoContext


class Extractor(ABC):
    name = "extractor"
    version = "0.1.0"

    @abstractmethod
    def extract(self, context: RepoContext) -> list[GraphFact]:
        raise NotImplementedError

