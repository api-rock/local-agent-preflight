from __future__ import annotations

import json

from .models import Report, Status


STATUS_LABELS = {
    Status.READY: "READY",
    Status.WARNING: "WARN",
    Status.BLOCKED: "BLOCKED",
    Status.NOT_APPLICABLE: "N/A",
}


def render_text(report: Report) -> str:
    lines = ["Local AI-agent preflight", "=" * 23, ""]
    for result in report.results:
        label = STATUS_LABELS[result.status]
        lines.append(f"[{label:<7}] {result.check_id}: {result.summary}")
        for detail in result.details:
            lines.append(f"          - {detail}")
        if result.remediation:
            lines.append(f"          Fix: {result.remediation}")
    lines.extend(
        [
            "",
            f"Summary: {report.ready} ready, {report.warnings} warning(s), "
            f"{report.blocked} blocked",
        ]
    )
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)
