# ruff: noqa: S404, S603, S606, T201, PLW0717, PLW1510 — this module is the project's subprocess wrapper
import os
import re
import shlex
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from subprocess import CalledProcessError, Popen, TimeoutExpired
from typing import NoReturn


_SHELL_OPERATOR_PATTERN = re.compile(r"[|;&<>`]")


def _check_no_shell_operator(command: str) -> None:
    stripped = re.sub(r'"[^"]*"', "", re.sub(r"'[^']*'", "", command))
    match = _SHELL_OPERATOR_PATTERN.search(stripped)
    if match is not None:
        msg = (
            f"Command contains shell operator {match.group()!r}: {command!r}. "
            "bash() runs without a shell, so the operator would be passed as a literal argument. "
            "Split into separate bash() calls, or use bash_pipe() for pipelines."
        )
        raise ValueError(msg)


def _resolve_args(command: str) -> list[str]:
    args = shlex.split(command, posix=(os.name != "nt"))
    if os.name == "nt" and args:
        resolved = shutil.which(args[0])
        if resolved is None:
            msg = f"Executable not found on PATH: {args[0]!r}"
            raise FileNotFoundError(msg)
        args[0] = resolved
    return args


def _merge_env(env: dict[str, str] | None) -> dict[str, str] | None:
    # env overlays the inherited process environment rather than replacing it, and is built into a
    # fresh dict so the child sees the extra vars without mutating this process's os.environ.
    return {**os.environ, **env} if env else None


def bash_output(
    command: str, *, cwd: Path | None = None, stdin_text: str | None = None, env: dict[str, str] | None = None
) -> str:
    _check_no_shell_operator(command)
    args = _resolve_args(command)

    with Popen(
        args,
        cwd=str(cwd) if cwd else None,
        env=_merge_env(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if stdin_text else None,
        text=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(input=stdin_text)
        except KeyboardInterrupt:
            try:
                process.wait(timeout=5)
            except TimeoutExpired:
                process.kill()
            raise

        if process.returncode != 0:
            if stderr:
                print(stderr, file=sys.stderr, end="")
            raise CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)

        return stdout or ""


def bash(
    command: str,
    *,
    cwd: Path | None = None,
    stdin_text: str | None = None,
    log_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    _check_no_shell_operator(command)
    args = _resolve_args(command)

    with ExitStack() as stack:
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log = stack.enter_context(log_path.open("a"))
            stdout, stderr = log, log
        else:
            stdout, stderr = sys.stdout, sys.stderr

        process = stack.enter_context(
            Popen(
                args,
                cwd=str(cwd) if cwd else None,
                env=_merge_env(env),
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.PIPE if stdin_text else None,
                text=True,
            )
        )

        try:
            process.communicate(input=stdin_text)
        except KeyboardInterrupt:
            try:
                process.wait(timeout=5)
            except TimeoutExpired:
                process.kill()
            raise

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, command)


def bash_pipe(*commands: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    if len(commands) < 2:
        msg = "bash_pipe requires at least 2 commands"
        raise ValueError(msg)

    merged_env = _merge_env(env)
    processes: list[Popen[bytes]] = []
    try:
        for i, command in enumerate(commands):
            args = _resolve_args(command)
            stdin = processes[-1].stdout if i > 0 else None
            stdout = subprocess.PIPE if i < len(commands) - 1 else sys.stdout
            stderr = sys.stderr if i == len(commands) - 1 else subprocess.DEVNULL
            processes.append(
                Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, cwd=str(cwd) if cwd else None, env=merged_env)
            )
            if i > 0 and processes[-2].stdout:
                processes[-2].stdout.close()

        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        for process in processes:
            try:
                process.wait(timeout=5)
            except TimeoutExpired:
                process.kill()
        raise

    for process in processes:
        if process.returncode != 0:
            raise CalledProcessError(process.returncode, process.args)


def bash_check(command: str, *, cwd: Path | None = None, env: dict[str, str] | None = None) -> bool:
    _check_no_shell_operator(command)
    args = _resolve_args(command)
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, env=_merge_env(env), capture_output=True)
    return result.returncode == 0


def bash_check_stream(command: str, *, cwd: Path | None = None, env: dict[str, str] | None = None) -> bool:
    _check_no_shell_operator(command)
    args = _resolve_args(command)
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, env=_merge_env(env))
    return result.returncode == 0


def bash_no_raise(command: str, *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    _check_no_shell_operator(command)
    args = _resolve_args(command)
    subprocess.run(args, cwd=str(cwd) if cwd else None, env=_merge_env(env))


def bash_handoff(command: str, *, cwd: Path | None = None, env: dict[str, str] | None = None) -> NoReturn:
    _check_no_shell_operator(command)
    args = _resolve_args(command)

    if cwd:
        os.chdir(cwd)

    merged_env = _merge_env(env)

    if sys.platform != "win32":
        os.execvpe(args[0], args, merged_env if merged_env is not None else os.environ)
    else:
        try:
            subprocess.run(args, check=True, env=merged_env)
        except subprocess.CalledProcessError as error:
            sys.exit(error.returncode)
        sys.exit(0)
