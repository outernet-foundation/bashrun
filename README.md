# bashrun

Guardrailed shell-exec helpers for Python. A thin, zero-dependency layer over `subprocess` that closes the sharp edges: quoted arguments are parsed with `shlex`, shell operators like `|` are rejected in single-command helpers (a separate `bash_pipe()` handles real pipelines), `KeyboardInterrupt` waits for the child to exit cleanly instead of leaving it orphaned, and failure paths raise `CalledProcessError` with `stdout` and `stderr` attached rather than a bare non-zero return code. On Windows, executables are resolved against `PATH` up front so a missing binary fails with a clear `FileNotFoundError`, not `WinError 2`.

The helpers form one small vocabulary — `bash`, `bash_output`, `bash_check`, `bash_check_stream`, `bash_no_raise`, `bash_pipe`, `bash_handoff` — each covering a specific failure-and-output shape. See the module docstring conventions in [`AGENTS.md`](./AGENTS.md) for which helper to reach for.

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```python
from bashrun import bash, bash_check, bash_output

bash("docker compose up -d")  # streams to stdout/stderr; raises on failure
text = bash_output("git rev-parse HEAD")  # captures stdout; raises on failure
if bash_check("test -f .env"):  # silent boolean; never raises
    ...
```

## Consuming from another repo

git-reference the package from your own `pyproject.toml`:

```toml
[project]
dependencies = ["bashrun"]

[tool.uv.sources]
bashrun = { git = "https://github.com/outernet-foundation/bashrun.git", rev = "<pin-a-commit-sha>" }
```

Then `from bashrun import ...` works from that repo.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest
```
