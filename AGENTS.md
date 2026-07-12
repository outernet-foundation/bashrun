# bashrun

## What this is

`bashrun` is a zero-dependency Python wrapper around `subprocess` that closes the sharp edges a plain `subprocess.run` leaves open: quoted arguments are `shlex`-parsed so `bash_output("echo 'hello world'")` behaves the way it reads; shell operators (`|`, `||`) are rejected in single-command helpers so a caller can't silently rely on shell expansion that isn't happening; `KeyboardInterrupt` waits up to five seconds for the child to exit before killing it, so Ctrl+C isn't swallowed and children aren't orphaned; failure paths raise `CalledProcessError` with `stdout` and `stderr` attached rather than a bare non-zero return code; and on Windows, `PATH` resolution happens up front so a missing executable fails with `FileNotFoundError` instead of the platform's `WinError 2`.

The package is `bashrun` (src-layout under `src/bashrun/`); consumer repos declare a git source in `[tool.uv.sources]` and import from it directly.

## Shape

- `bash.py` — all seven helpers, one file. Each is one shape of "run a command":
  - `bash(command)` — streams stdout/stderr live; raises on non-zero. The default when the caller doesn't need the output. Accepts `log_path=` to tee both streams to a file instead of the terminal.
  - `bash_output(command)` — captures stdout as a `str` and returns it; stderr is buffered and, on failure, printed to the parent's stderr and attached to the raised `CalledProcessError` alongside the partial stdout.
  - `bash_check(command)` — runs silently; returns `True`/`False`. For idempotency probes ("is this already done?") where the failure mode is expected and no output should surface.
  - `bash_check_stream(command)` — like `bash_check`, but streams output. For probes whose progress the caller *does* want to see.
  - `bash_no_raise(command)` — streams output; never raises regardless of exit code. The rare shape for fire-and-continue.
  - `bash_pipe(cmd1, cmd2, ...)` — runs a real shell pipeline by chaining child processes' stdio in Python; each intermediate's stderr is discarded, the final's is preserved. This is why `bash`/`bash_output` reject `|`: pipelines have their own helper.
  - `bash_handoff(command)` — `os.execvpe`s into the child (Windows falls back to `subprocess.run` + `sys.exit`). The current process is replaced; no return.
- `__init__.py` — re-exports the seven names.

## Constraints

**Zero runtime dependencies.** The whole point is that consumers can git-reference `bashrun` from any repo, sandbox, or CI job without dragging a dependency graph in behind it. Adding a runtime dependency negates the reason this package exists as its own repo. Standard-library-only is a hard rule.

**Every command goes through `_check_no_pipe` and `_resolve_args` (except `bash_pipe`).** `_check_no_pipe` strips quoted segments and rejects any remaining `|` — this catches both the pipe operator and the logical-OR `||`. Shell fallback patterns like `cmd || echo default` are refused by design: the caller should probe with `bash_check` and branch in Python, not lean on shell short-circuit. `_resolve_args` uses `shlex.split` with `posix=(os.name != "nt")` so quoted arguments parse the way they read, and on Windows also resolves `argv[0]` against `PATH` via `shutil.which` up front — `subprocess.Popen` on Windows won't do that for you and returns `WinError 2` when it can't find the binary. Skipping either guard defeats the reason a caller reached for this package instead of raw `subprocess`.

**`env=` overlays the inherited environment; it does not replace it.** Every helper takes an optional `env=` mapping. It is merged *onto* the process environment (`{**os.environ, **env}`) into a fresh dict, so the child sees the extra or overridden vars while everything else (`PATH`, `HOME`, …) is still inherited, and this process's `os.environ` is never mutated. This is deliberately unlike `subprocess`'s own `env=`, which replaces the environment wholesale: callers here almost always want "add a couple of vars for this one child," and the pattern this replaces — mutating the global `os.environ` so a child inherits a var — leaks that var into every later subprocess in the process. Passing `env=None` (the default) inherits unchanged.

**`KeyboardInterrupt` handling is load-bearing, not incidental.** Each helper's `except KeyboardInterrupt` waits up to five seconds for the child to exit cleanly, then kills, then re-raises. Naive `subprocess.run` doesn't propagate Ctrl+C to a long-running child in a way that lets the child clean up; the wait-then-kill dance is why callers can trust that Ctrl+C in the parent actually reaches (and eventually terminates) the child.

**Wheel must ship `py.typed`.** The package is typed and consumers expect strict-mode-friendly imports. A real hatch-built wheel omits non-Python files unless `[tool.hatch.build.targets.wheel] include` names them; drop the `py.typed` entry from `pyproject.toml` and downstream basedpyright/mypy silently treat the package as untyped.

**The module-level `# ruff: noqa: S404, S603` in `bash.py` stays.** This package *is* the subprocess wrapper — importing and calling `subprocess` unsafely is its whole job. The suppression is the wrapper boundary (case 1 in the shared "fix warnings; suppress only under a wrapped or tracked exception" rule): every `subprocess` usage lives inside this one file, and the header declares it as the sanctioned suppression site so audits don't have to reason about each call individually.

## See also

- `README.md` — human-facing setup and usage.
