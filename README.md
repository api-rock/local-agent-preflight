# Local Agent Preflight

> A small, dependency-free CLI that explains why a local AI-agent setup is or is not ready.

## Why this project?

Two beginner problems were shortlisted as realistic open-source projects:

1. **Local setup diagnosis — recommended.** Beginners do not know whether a failure comes from hardware, a missing runtime, a driver, an API port, or a missing model. A preflight checker can give them a useful answer before they start debugging an agent.
2. **Visible agent-loop debugger.** Beginners cannot see the model's proposed tool call, the arguments, the tool result, or the reason an agent loop stopped. This is valuable, but a safe execution model is a larger second project because it needs permissions, replay, timeouts, and process isolation.

This repository implements the first problem. It is deliberately small enough to try today, useful without an account or API key, and designed to become the diagnostic foundation for a future agent-loop debugger.

## What it checks

- Python version and operating system.
- Available memory and free disk space.
- Common local runtimes on `PATH`: Ollama, llama.cpp, and LM Studio's `lms` command.
- NVIDIA or AMD GPU visibility when vendor tools are available.
- Ollama and OpenAI-compatible local API endpoints.
- Installed model names, when `--model` is provided.
- A tiny optional inference smoke test.
- Human-readable terminal output or stable JSON for scripts and CI.

The checker never invokes a shell, never sends requests to a remote service unless you explicitly pass a remote URL, and applies timeouts to local commands and HTTP requests.

## Quick start

The project has no runtime dependencies. Python 3.10 or newer is required.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install -e .
agent-preflight check
```

The default check looks for an Ollama server at `http://127.0.0.1:11434`. Use a different local endpoint when needed:

```bash
agent-preflight check --url http://127.0.0.1:1234/v1
agent-preflight check --url http://127.0.0.1:11434 --model llama3.2
agent-preflight check --url http://127.0.0.1:11434 --model llama3.2 --smoke-test
```

For scripts and CI:

```bash
agent-preflight check --json > preflight.json
echo $?
```

Exit codes:

- `0`: no blocked checks. Warnings may still be present.
- `1`: at least one check is blocked, or `--strict` was used and a warning exists.
- `2`: invalid CLI usage or no command was supplied.

## Example output

```text
Local AI-agent preflight
=======================

[READY  ] host.python: Python 3.12 is supported
[READY  ] host.platform: Linux on x86_64
[READY  ] host.memory: 12.4 GiB available memory
[READY  ] host.disk: 83.1 GiB free on the project disk
[READY  ] runtime.detected: Detected 1 local runtime(s)
          - ollama: ollama version is 0.6.x
[WARN   ] gpu.available: No NVIDIA or AMD GPU probe was found; CPU inference may still work
          Fix: Install the correct vendor driver if you expect GPU acceleration.
[READY  ] api.endpoint: Ollama endpoint is reachable
          - Protocol: ollama
          - Models visible: 1

Summary: 7 ready, 1 warning(s), 0 blocked
```

## Development

Run the standard-library test suite without installing test dependencies:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

If `pytest` is installed, this also works:

```bash
PYTHONPATH=src python -m pytest
```

The repository includes a GitHub Actions workflow for Linux, macOS, and Windows. GPU and local-server behavior is tested through graceful fallbacks and a local mock HTTP server, so CI does not need a GPU or an external model.

## Design boundaries for the MVP

This is a diagnostic tool, not an agent framework. It intentionally does **not**:

- Download or install a model.
- Change GPU drivers or system settings.
- Execute model-generated shell commands.
- Send data to a hosted model provider.
- Claim that the presence of a GPU proves that a chosen runtime can use it.

Those boundaries keep the first version safe and portable. A future agent-loop debugger can consume the JSON output from this tool and add dry-run tool calls, approval gates, replay, and event tracing.

## Suggested first GitHub issue

Add a runtime plugin interface so LM Studio, vLLM, and additional OpenAI-compatible servers can provide richer model and health checks without changing the report format.

## Upload the full repository to GitHub

The complete repository is this folder:

```text
/home/king/o rush/local-agent-preflight
```

The generated files under `__pycache__/`, `*.egg-info/`, `.venv/`, and build folders are excluded by `.gitignore`.

### Method A: GitHub website

1. Sign in at <https://github.com>.
2. Select **New repository**.
3. Enter the repository name `local-agent-preflight`.
4. Choose **Public** or **Private**.
5. Leave **Add a README file**, **Add .gitignore**, and **Choose a license** unchecked because this repository already contains those files.
6. Create the repository.
7. On the new repository page, choose **Add file → Upload files**.
8. Open `/home/king/o rush/local-agent-preflight` on your computer and select all repository contents, including `.github`, `src`, `tests`, `README.md`, `LICENSE`, `pyproject.toml`, and `.gitignore`.
9. Commit the upload to the `main` branch.

Make sure the `.github/workflows/ci.yml` file is included. GitHub Actions will then run the tests automatically.

### Method B: Git command line (recommended)

First create an empty repository at <https://github.com/new> named `local-agent-preflight`. Then run these commands:

```bash
cd "/home/king/o rush/local-agent-preflight"

git add .
git diff --cached --check
git commit -m "feat: add local agent preflight checker"

git remote add origin https://github.com/YOUR_USERNAME/local-agent-preflight.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. If Git asks for a password, use a GitHub personal access token instead of your GitHub account password.

If a remote named `origin` already exists, use this instead of `git remote add origin`:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/local-agent-preflight.git
```

After uploading, verify the result:

```bash
git status
git remote -v
```

The `git status` output should say the working tree is clean, and the repository should be visible at:

```text
https://github.com/YOUR_USERNAME/local-agent-preflight
```

### Method C: GitHub CLI

If GitHub CLI is installed and authenticated:

```bash
cd "/home/king/o rush/local-agent-preflight"
gh auth login
git add .
git commit -m "feat: add local agent preflight checker"
gh repo create local-agent-preflight --public --source=. --remote=origin --push
```

Use `--private` instead of `--public` if the repository should not be public.
