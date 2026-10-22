from dataclasses import dataclass
from typing import Protocol, Sequence

from test_cases.indexers.kotlin_restassured import KotlinRestAssuredIndexer


@dataclass(frozen=True)
class SourceFile:
    path: str
    text: str


@dataclass(frozen=True)
class IndexContext:
    spec_ops: tuple[tuple[str, str], ...]
    server_path: str | None
    exclude_classes: tuple[str, ...]


class Indexer(Protocol):
    name: str

    def detect(self, rel_paths: Sequence[str]) -> bool: ...

    def index(self, sources: Sequence[SourceFile], ctx: IndexContext) -> dict: ...


INDEXERS: dict[str, Indexer] = {"kotlin-restassured": KotlinRestAssuredIndexer()}


def select(name, rel_paths, registry=None):
    reg = INDEXERS if registry is None else registry
    if name is not None:
        if name not in reg:
            raise LookupError(f"unknown indexer {name!r}; available: {', '.join(sorted(reg))}")
        return reg[name]
    for indexer in reg.values():
        if indexer.detect(rel_paths):
            return indexer
    raise LookupError(f"no indexer matched; available: {', '.join(sorted(reg))}")
