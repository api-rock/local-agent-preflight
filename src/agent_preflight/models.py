from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class CheckResult:
    """One user-facing diagnostic result."""

    check_id: str
    category: str
    status: Status
    summary: str
    details: list[str] = field(default_factory=list)
    remediation: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "category": self.category,
            "status": self.status.value,
            "summary": self.summary,
            "details": self.details,
            "remediation": self.remediation,
            "data": self.data,
        }


@dataclass
class Report:
    """A complete run of the preflight checker."""

    results: list[CheckResult]

    @property
    def blocked(self) -> int:
        return sum(result.status == Status.BLOCKED for result in self.results)

    @property
    def warnings(self) -> int:
        return sum(result.status == Status.WARNING for result in self.results)

    @property
    def ready(self) -> int:
        return sum(result.status == Status.READY for result in self.results)

    def exit_code(self, strict: bool = False) -> int:
        if self.blocked or (strict and self.warnings):
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "summary": {
                "ready": self.ready,
                "warnings": self.warnings,
                "blocked": self.blocked,
                "total": len(self.results),
            },
            "results": [result.to_dict() for result in self.results],
        }
