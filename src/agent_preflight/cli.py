from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__
from .models import Report
from .probes import run_checks
from .report import render_json, render_text


DEFAULT_URL = "http://127.0.0.1:11434"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-preflight",
        description="Explain whether a local AI-agent setup is ready to use.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser(
        "check",
        help="run host, runtime, GPU, and local API checks",
        description="Run diagnostics for a local AI-agent development setup.",
    )
    check.add_argument(
        "--url",
        action="append",
        dest="urls",
        metavar="URL",
        help=f"local API base URL; repeat for multiple endpoints (default: {DEFAULT_URL})",
    )
    check.add_argument(
        "--model",
        help="model name to verify at each endpoint",
    )
    check.add_argument(
        "--path",
        default=".",
        help="path whose disk has to hold the project/model cache (default: current directory)",
    )
    check.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="timeout in seconds for each command and HTTP request (default: 3)",
    )
    check.add_argument(
        "--smoke-test",
        action="store_true",
        help="send a tiny inference request after verifying the endpoint and model",
    )
    check.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON instead of the terminal report",
    )
    check.add_argument(
        "--strict",
        action="store_true",
        help="return exit code 1 for warnings as well as blocked checks",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "check":
        parser.print_help()
        return 2
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    urls = args.urls or [DEFAULT_URL]
    report = Report(
        run_checks(
            urls=urls,
            model=args.model,
            path=args.path,
            timeout=args.timeout,
            smoke_test=args.smoke_test,
        )
    )
    print(render_json(report) if args.as_json else render_text(report))
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
