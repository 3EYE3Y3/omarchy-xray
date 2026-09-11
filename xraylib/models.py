from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Target:
    type: str
    identifier: str
    display_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def result(
    target: Target, sections: dict[str, Any], *, warnings: list[str] | None = None
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "target": target.as_dict(),
        "sections": sections,
        "warnings": warnings or [],
    }
