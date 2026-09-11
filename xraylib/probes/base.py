from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import Target
from ..runner import Runner


class Probe(ABC):
    target_types: tuple[str, ...] = ()

    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or Runner()

    def supports(self, target: Target) -> bool:
        return target.type in self.target_types

    def capabilities(self) -> list[str]:
        return ["inspect", "raw"]

    def actions(self) -> list[dict[str, Any]]:
        return []

    @abstractmethod
    def collect(self, target: Target) -> dict[str, Any]:
        raise NotImplementedError
