from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class QueryCounter:
    engine: Engine
    count: int = 0
    statements: list[str] | None = None

    def __post_init__(self) -> None:
        if self.statements is None:
            self.statements = []

    def _before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany) -> None:
        self.count += 1
        assert self.statements is not None
        self.statements.append(str(statement))

    def __enter__(self) -> "QueryCounter":
        event.listen(self.engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        event.remove(self.engine, "before_cursor_execute", self._before_cursor_execute)

    def matching(self, needle: str) -> list[str]:
        assert self.statements is not None
        return [s for s in self.statements if needle in s]


@pytest.fixture
def query_counter(engine) -> Iterator[type[QueryCounter]]:
    def factory() -> QueryCounter:
        return QueryCounter(engine)

    yield factory
