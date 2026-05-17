from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FactorFieldRequest:
    logical_name: str
    source_schema: str
    source_table: str
    source_column: str

    _QUALIFIED_FACTOR = re.compile(
        r"^(?:(?P<schema>[A-Za-z_][A-Za-z0-9_]*)\.)?"
        r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\."
        r"(?P<column>[A-Za-z_][A-Za-z0-9_]*)$"
    )

    @classmethod
    def from_target(cls, logical_name: str, target: str) -> "FactorFieldRequest":
        parts = target.split(".")
        if len(parts) == 2 and parts[0] == "factors":
            raise ValueError(f"Invalid factor target: {target}")
        match = cls._QUALIFIED_FACTOR.match(target)
        if not match:
            raise ValueError(f"Invalid factor target: {target}")
        return cls(
            logical_name=logical_name,
            source_schema=match.group("schema") or "factors",
            source_table=match.group("table"),
            source_column=match.group("column"),
        )

    @property
    def qualified_table(self) -> str:
        return f"{self.source_schema}.{self.source_table}"
