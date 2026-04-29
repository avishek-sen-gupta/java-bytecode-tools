"""Shared types and plugin protocols for jspmap."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BeanInfo:
    name: str  # logical bean name (e.g. "orderAction")
    fqcn: str  # fully qualified class name
    scope: str  # scope string (request / session / application / none)


class BeanResolver(Protocol):
    def resolve(self, config_path: Path) -> dict[str, BeanInfo]: ...
