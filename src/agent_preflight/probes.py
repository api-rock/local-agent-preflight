from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .models import CheckResult, Status


GIB = 1024**3
MIN_PYTHON = (3, 10)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_bounded(command: Sequence[str], timeout: float = 3.0) -> CommandResult:
    """Run a local diagnostic command without invoking a shell or hanging."""

    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return CommandResult(-1, stdout, stderr, timed_out=True)
    except OSError as exc:
        return CommandResult(-1, "", str(exc))
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _available_memory_bytes() -> int | None:
    """Return available memory where the operating system exposes it."""

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        if page_size > 0 and available_pages > 0:
            return page_size * available_pages
    except (AttributeError, OSError, ValueError):
        pass
    return None


def _format_gib(value: int | float) -> str:
    return f"{value / GIB:.1f} GiB"


def probe_host(path: str | Path = ".") -> list[CheckResult]:
    """Check the basic resources needed by a local model runtime."""

    results: list[CheckResult] = []
    version = sys.version_info[:2]
    if version >= MIN_PYTHON:
        python_status = Status.READY
        python_summary = f"Python {version[0]}.{version[1]} is supported"
        python_remediation = None
    else:
        python_status = Status.BLOCKED
        python_summary = f"Python {version[0]}.{version[1]} is too old"
        python_remediation = "Install Python 3.10 or newer and rerun the check."
    results.append(
        CheckResult(
            "host.python",
            "host",
            python_status,
            python_summary,
            data={"version": f"{version[0]}.{version[1]}"},
            remediation=python_remediation,
        )
    )

    results.append(
        CheckResult(
            "host.platform",
            "host",
            Status.READY,
            f"{platform.system()} on {platform.machine() or 'unknown architecture'}",
            details=[platform.platform()],
            data={"system": platform.system(), "machine": platform.machine()},
        )
    )

    memory = _available_memory_bytes()
    if memory is None:
        results.append(
            CheckResult(
                "host.memory",
                "host",
                Status.WARNING,
                "Available memory could not be measured",
                remediation="Check system memory manually before downloading a large model.",
            )
        )
    else:
        memory_status = Status.WARNING if memory < 4 * GIB else Status.READY
        memory_summary = f"{_format_gib(memory)} available memory"
        results.append(
            CheckResult(
                "host.memory",
                "host",
                memory_status,
                memory_summary,
                details=["Small quantized models may still work with less memory."],
                remediation=(
                    "Choose a smaller quantized model and close other applications."
                    if memory_status == Status.WARNING
                    else None
                ),
                data={"available_bytes": memory},
            )
        )

    try:
        disk = shutil.disk_usage(Path(path).expanduser().resolve())
    except OSError as exc:
        results.append(
            CheckResult(
                "host.disk",
                "host",
                Status.WARNING,
                "Disk space could not be measured",
                details=[str(exc)],
                remediation="Check the disk containing the project and model cache.",
            )
        )
    else:
        disk_status = Status.WARNING if disk.free < 5 * GIB else Status.READY
        results.append(
            CheckResult(
                "host.disk",
                "host",
                disk_status,
                f"{_format_gib(disk.free)} free on the project disk",
                details=[f"Total capacity: {_format_gib(disk.total)}"],
                remediation=(
                    "Free disk space before downloading a model."
                    if disk_status == Status.WARNING
                    else None
                ),
                data={"free_bytes": disk.free, "total_bytes": disk.total},
            )
        )
    return results


def probe_gpu(timeout: float = 3.0) -> CheckResult:
    """Make a best-effort GPU check without requiring vendor SDKs."""

    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        result = run_bounded(
            [
                nvidia,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpus = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return CheckResult(
                "gpu.nvidia",
                "gpu",
                Status.READY,
                f"NVIDIA GPU detected ({len(gpus)} device(s))",
                details=gpus,
                data={"devices": gpus},
            )
        if result.timed_out:
            return CheckResult(
                "gpu.nvidia",
                "gpu",
                Status.WARNING,
                "nvidia-smi timed out while checking the GPU",
                remediation="Check the NVIDIA driver and retry after a reboot.",
            )
        return CheckResult(
            "gpu.nvidia",
            "gpu",
            Status.WARNING,
            "nvidia-smi is installed but could not query a GPU",
            details=[result.stderr.strip() or "No diagnostic output was returned."],
            remediation="Update the NVIDIA driver or use CPU inference.",
        )

    rocminfo = shutil.which("rocminfo")
    if rocminfo:
        result = run_bounded([rocminfo], timeout)
        if result.returncode == 0:
            first_line = next(
                (line.strip() for line in result.stdout.splitlines() if line.strip()),
                "ROCm device information returned",
            )
            return CheckResult(
                "gpu.amd",
                "gpu",
                Status.READY,
                "AMD ROCm device query succeeded",
                details=[first_line],
            )
        return CheckResult(
            "gpu.amd",
            "gpu",
            Status.WARNING,
            "rocminfo is installed but could not query a device",
            details=[result.stderr.strip() or "No diagnostic output was returned."],
            remediation="Check ROCm drivers and device permissions, or use CPU inference.",
        )

    if platform.system() == "Darwin":
        return CheckResult(
            "gpu.apple",
            "gpu",
            Status.WARNING,
            "Apple GPU may be available through Metal, but it was not verified",
            remediation="Confirm that your chosen runtime reports Metal acceleration.",
        )

    return CheckResult(
        "gpu.available",
        "gpu",
        Status.WARNING,
        "No NVIDIA or AMD GPU probe was found; CPU inference may still work",
        remediation="Install the correct vendor driver if you expect GPU acceleration.",
    )


KNOWN_RUNTIMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ollama", ("ollama", "--version")),
    ("llama-server", ("llama-server", "--version")),
    ("llama-cli", ("llama-cli", "--version")),
    ("lm-studio", ("lms", "--version")),
)


def probe_runtimes(timeout: float = 3.0) -> CheckResult:
    """Find common local runtimes and report their versions when possible."""

    found: list[str] = []
    details: list[str] = []
    for name, command in KNOWN_RUNTIMES:
        executable = shutil.which(command[0])
        if not executable:
            continue
        result = run_bounded([executable, *command[1:]], timeout)
        version = (result.stdout or result.stderr).strip().splitlines()
        version_text = version[0] if version else "version unavailable"
        found.append(name)
        details.append(f"{name}: {version_text[:160]}")

    if found:
        return CheckResult(
            "runtime.detected",
            "runtime",
            Status.READY,
            f"Detected {len(found)} local runtime(s)",
            details=details,
            data={"runtimes": found},
        )
    return CheckResult(
        "runtime.detected",
        "runtime",
        Status.BLOCKED,
        "No supported local model runtime was found on PATH",
        remediation="Install Ollama, llama.cpp, or another supported local runtime, then rerun.",
    )


def _json_request(
    url: str,
    timeout: float,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | None, str | None]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(decoded, dict):
                return response.status, None, "Endpoint returned JSON that was not an object."
            return response.status, decoded, None
    except urllib.error.HTTPError as exc:
        try:
            message = exc.read().decode("utf-8", errors="replace")
        except OSError:
            message = str(exc)
        return exc.code, None, message[:300]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return 0, None, str(exc)


def _model_names(payload: dict[str, Any]) -> list[str]:
    values = payload.get("models", payload.get("data", []))
    if not isinstance(values, list):
        return []
    names: list[str] = []
    for value in values:
        if isinstance(value, dict):
            name = value.get("name") or value.get("id")
            if isinstance(name, str):
                names.append(name)
    return names


def _endpoint_variants(base_url: str) -> list[tuple[str, str]]:
    normalized = base_url.rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.path.rstrip("/").endswith("/v1"):
        return [("openai", f"{normalized}/models")]
    return [
        ("ollama", f"{normalized}/api/tags"),
        ("openai", f"{normalized}/v1/models"),
    ]


def _smoke_test(
    base_url: str,
    endpoint_kind: str,
    model: str,
    timeout: float,
) -> tuple[bool, str]:
    normalized = base_url.rstrip("/")
    if endpoint_kind == "ollama":
        url = f"{normalized}/api/generate"
        payload = {"model": model, "prompt": "Reply with OK.", "stream": False}
    else:
        url = f"{normalized}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "stream": False,
            "max_tokens": 8,
        }
    status, response, error = _json_request(url, timeout, method="POST", payload=payload)
    if error:
        return False, f"Smoke test failed ({status or 'connection'}): {error}"
    return True, f"Smoke test returned HTTP {status}"


def probe_endpoint(
    base_url: str,
    model: str | None = None,
    timeout: float = 3.0,
    smoke_test: bool = False,
) -> CheckResult:
    """Probe an Ollama or OpenAI-compatible local endpoint."""

    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return CheckResult(
            "api.endpoint",
            "api",
            Status.BLOCKED,
            f"Invalid endpoint URL: {base_url}",
            remediation="Use a URL such as http://127.0.0.1:11434.",
        )

    errors: list[str] = []
    for endpoint_kind, url in _endpoint_variants(base_url):
        status, payload, error = _json_request(url, timeout)
        if error:
            errors.append(f"{url}: HTTP {status or 'connection'} — {error}")
            continue
        names = _model_names(payload or {})
        details = [f"Protocol: {endpoint_kind}", f"Models visible: {len(names)}"]
        if names:
            details.append("Model names: " + ", ".join(names[:10]))
        if model and model not in names:
            return CheckResult(
                "api.model",
                "api",
                Status.BLOCKED,
                f"Endpoint is reachable, but model '{model}' was not found",
                details=details,
                remediation="Pull or load the model, or rerun with the exact installed model name.",
                data={"url": base_url, "protocol": endpoint_kind, "models": names},
            )
        if smoke_test:
            if not model:
                return CheckResult(
                    "api.smoke_test",
                    "api",
                    Status.BLOCKED,
                    "A model is required for --smoke-test",
                    details=details,
                    remediation="Pass --model with the model name shown by the endpoint.",
                )
            passed, message = _smoke_test(base_url, endpoint_kind, model, timeout)
            details.append(message)
            if not passed:
                return CheckResult(
                    "api.smoke_test",
                    "api",
                    Status.BLOCKED,
                    "Endpoint responded, but the inference smoke test failed",
                    details=details,
                    remediation="Check the model, runtime logs, and available memory.",
                    data={"url": base_url, "protocol": endpoint_kind, "models": names},
                )
        return CheckResult(
            "api.endpoint",
            "api",
            Status.READY,
            f"{endpoint_kind.title()} endpoint is reachable",
            details=details,
            data={"url": base_url, "protocol": endpoint_kind, "models": names},
        )

    return CheckResult(
        "api.endpoint",
        "api",
        Status.BLOCKED,
        f"Could not reach a supported API at {base_url}",
        details=errors,
        remediation="Start the local server, check the port, and rerun with --url if needed.",
        data={"url": base_url},
    )


def run_checks(
    urls: list[str],
    model: str | None = None,
    path: str | Path = ".",
    timeout: float = 3.0,
    smoke_test: bool = False,
) -> list[CheckResult]:
    """Run all checks in a deterministic order."""

    results = probe_host(path)
    results.append(probe_runtimes(timeout))
    results.append(probe_gpu(timeout))
    results.extend(
        probe_endpoint(url, model=model, timeout=timeout, smoke_test=smoke_test)
        for url in urls
    )
    return results
